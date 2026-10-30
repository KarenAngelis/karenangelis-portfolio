import asyncio
import contextlib
import json
import logging
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from config import Settings
from models import Credentials, EmailInput, TokenInput, ResetInput, GoogleInput, CheckoutInput, split_domain
from providers import Registrar, Payments, ProviderError
from security import digest, password_hash, password_matches, issue_token, consume_token, send_account_mail
from service import accept_payment, tick
from storage import Store

COOKIE = 'ka_domain_session'
PREFIX = '/api/domains'


def create_app(settings=None, store=None, registrar=None, payments=None, worker=True):
    settings = settings or Settings()
    store = store or Store(settings.db)
    registrar = registrar or Registrar(settings)
    payments = payments or Payments(settings)

    async def work():
        while True:
            try:
                if settings.processing_ready:
                    await run_in_threadpool(tick, store, registrar, payments)
            except Exception:
                # Never log provider requests, passwords, personal data or raw exception text.
                logging.error('Domain worker failed; inspect durable order states and alerts.')
            await asyncio.sleep(20)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(work()) if worker else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title='Karen Angelis — Domínios', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store, app.state.settings = store, settings

    @app.middleware('http')
    async def protect(request, call_next):
        # Same-origin JSON mutations + SameSite cookies prevent CSRF, including login CSRF.
        if request.method == 'POST':
            if request.url.path != PREFIX + '/webhooks/mercadopago':
                if request.headers.get('origin') != settings.origin:
                    return JSONResponse({'detail': 'Origem da solicitação inválida.'}, status_code=403)
                if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                    return JSONResponse({'detail': 'Envie JSON.'}, status_code=415)
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16384:
                    return JSONResponse({'detail': 'Solicitação muito grande.'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default response echoes input (including password/document).
        return JSONResponse({'detail': 'Confira os campos. A senha precisa ter pelo menos 12 caracteres; CPF/CNPJ, CEP e telefone devem ser válidos.'}, status_code=422)

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=503)

    def limit(request, bucket, maximum=10, seconds=60):
        ip = request.client.host if request.client else 'unknown'
        if not store.allow(bucket + ':' + ip, maximum, seconds):
            raise HTTPException(429, 'Muitas tentativas. Aguarde um pouco e tente novamente.')

    def current_user(request):
        token = request.cookies.get(COOKIE, '')
        user = store.one('SELECT users.* FROM users JOIN sessions ON sessions.user_id=users.id WHERE sessions.token=? AND sessions.expires>?',
                         (digest(token), int(time.time())))
        if not user:
            raise HTTPException(401, 'Entre na sua conta para continuar.')
        return user

    def session(response, request, user_id):
        store.execute('DELETE FROM sessions WHERE token=?', (digest(request.cookies.get(COOKIE, '')),))
        token = secrets.token_urlsafe(32)
        store.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token), user_id, int(time.time()) + 86400))
        response.set_cookie(COOKIE, token, max_age=86400, httponly=True, secure=settings.origin.startswith('https://'), samesite='lax', path=PREFIX)

    def mail(user, kind):
        if not settings.mail_ready:
            raise HTTPException(503, 'O acesso por e-mail está temporariamente indisponível.')
        token = issue_token(store, user['id'], kind)
        try:
            send_account_mail(settings, user['email'], token, kind)
        except Exception:
            store.execute('DELETE FROM tokens WHERE token=?', (digest(token),))
            raise HTTPException(503, 'Não foi possível enviar o e-mail. Tente novamente mais tarde.') from None

    @app.get(PREFIX + '/health')
    def health():
        return {'status': 'ok'}

    @app.get(PREFIX + '/config')
    def configuration():
        return {'search_ready': settings.search_ready, 'sales_ready': settings.sales_ready,
                'email_ready': settings.mail_ready, 'google_client_id': settings.google_id,
                'test_mode': not settings.live, 'tlds': list(settings.prices), 'max_installments': 5}

    @app.post(PREFIX + '/auth/register')
    def register(data: Credentials, request: Request):
        limit(request, 'mail', 5, 900)
        if not settings.mail_ready:
            raise HTTPException(503, 'O cadastro está temporariamente indisponível.')
        user = store.one('SELECT * FROM users WHERE email=?', (data.email,))
        encoded = password_hash(data.password)
        if not user:
            user = {'id': secrets.token_urlsafe(24), 'email': data.email}
            try:
                store.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)', (user['id'], data.email, encoded))
            except sqlite3.IntegrityError:
                return {'message': 'Se o cadastro precisar de confirmação, enviaremos um e-mail. Se já tem conta, entre ou redefina sua senha.'}
            mail(user, 'verify')
        elif not user['verified']:
            # Do not overwrite the password of an existing account.
            mail(user, 'verify')
        return {'message': 'Se o cadastro precisar de confirmação, enviaremos um e-mail. Se já tem conta, entre ou redefina sua senha.'}

    @app.post(PREFIX + '/auth/verify')
    def verify(data: TokenInput, request: Request):
        limit(request, 'tokens')
        token = consume_token(store, data.token, 'verify')
        if not token:
            raise HTTPException(400, 'Link inválido ou expirado. Solicite outro e-mail.')
        store.execute('UPDATE users SET verified=1 WHERE id=?', (token['user_id'],))
        return {'message': 'E-mail confirmado. Entre na sua conta.'}

    @app.post(PREFIX + '/auth/login')
    def login(data: Credentials, request: Request, response: Response):
        limit(request, 'login', 10, 900)
        user = store.one('SELECT * FROM users WHERE email=?', (data.email,))
        if not password_matches(data.password, user['password'] if user else None):
            raise HTTPException(401, 'E-mail ou senha incorretos.')
        if not user['verified']:
            raise HTTPException(403, 'Confirme seu e-mail antes de entrar. Use “Reenviar confirmação” se precisar.')
        session(response, request, user['id'])
        return {'email': user['email']}

    @app.post(PREFIX + '/auth/email')
    def account_email(data: EmailInput, request: Request, kind: str = 'reset'):
        limit(request, 'mail', 5, 900)
        if kind not in {'reset', 'verify'}:
            raise HTTPException(400, 'Solicitação inválida.')
        user = store.one('SELECT * FROM users WHERE email=?', (data.email,))
        if user and ((kind == 'reset' and user['password']) or (kind == 'verify' and not user['verified'])):
            mail(user, kind)
        return {'message': 'Se houver uma conta elegível, enviaremos o link para seu e-mail.'}

    @app.post(PREFIX + '/auth/reset')
    def reset(data: ResetInput, request: Request):
        limit(request, 'tokens')
        token = consume_token(store, data.token, 'reset')
        if not token:
            raise HTTPException(400, 'Link inválido ou expirado.')
        with store.connection() as db:
            db.execute('UPDATE users SET password=?,verified=1 WHERE id=?', (password_hash(data.password), token['user_id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (token['user_id'],))
            db.execute('DELETE FROM tokens WHERE user_id=?', (token['user_id'],))
        return {'message': 'Senha atualizada. Entre novamente.'}

    @app.post(PREFIX + '/auth/google/nonce')
    def google_nonce(request: Request, response: Response):
        limit(request, 'google')
        if not settings.google_id:
            raise HTTPException(503, 'Login Google indisponível.')
        nonce = issue_token(store, None, 'google', 300)
        response.set_cookie('ka_google_nonce', nonce, max_age=300, httponly=True,
                            secure=settings.origin.startswith('https://'), samesite='strict', path=PREFIX)
        return {'nonce': nonce}

    @app.post(PREFIX + '/auth/google')
    def google_login(data: GoogleInput, request: Request, response: Response):
        limit(request, 'google')
        if not settings.google_id:
            raise HTTPException(503, 'Login Google indisponível.')
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request as GoogleRequest
        try:
            payload = id_token.verify_oauth2_token(data.credential, GoogleRequest(), settings.google_id)
            nonce = request.cookies.get('ka_google_nonce', '')
            if not nonce or payload.get('nonce') != nonce or not payload.get('email_verified'):
                raise ValueError()
            if not consume_token(store, nonce, 'google'):
                raise ValueError()
        except Exception:
            raise HTTPException(401, 'Não foi possível validar seu acesso Google. Tente novamente.') from None
        email = EmailInput(email=payload['email']).email
        user = store.one('SELECT * FROM users WHERE google_sub=?', (payload['sub'],))
        if not user:
            if store.one('SELECT id FROM users WHERE email=?', (email,)):
                raise HTTPException(409, 'Este e-mail já tem uma conta. Entre com sua senha ou redefina-a.')
            authoritative = email.endswith('@gmail.com') or bool(payload.get('hd'))
            if not authoritative and not settings.mail_ready:
                raise HTTPException(503, 'Precisamos confirmar este e-mail. Tente mais tarde.')
            user = {'id': secrets.token_urlsafe(24), 'email': email, 'verified': int(authoritative)}
            try:
                store.execute('INSERT INTO users(id,email,verified,google_sub) VALUES(?,?,?,?)',
                              (user['id'], email, user['verified'], payload['sub']))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Conta já cadastrada. Entre novamente.') from None
        if not user['verified']:
            mail(user, 'verify')
            raise HTTPException(403, 'Enviamos um link para confirmar seu e-mail. Depois, entre novamente com Google.')
        session(response, request, user['id'])
        response.delete_cookie('ka_google_nonce', path=PREFIX)
        return {'email': user['email']}

    @app.post(PREFIX + '/auth/logout')
    def logout(request: Request, response: Response):
        store.execute('DELETE FROM sessions WHERE token=?', (digest(request.cookies.get(COOKIE, '')),))
        response.delete_cookie(COOKIE, path=PREFIX)
        return {'message': 'Você saiu da conta.'}

    @app.get(PREFIX + '/me')
    def me(request: Request):
        user = current_user(request)
        return {'email': user['email']}

    @app.get(PREFIX + '/search')
    def search(request: Request, q: str = ''):
        limit(request, 'search', 20)
        if not settings.search_ready:
            raise HTTPException(503, 'A busca de domínios está em preparação. Fale com Karen para escolher seu endereço.')
        try:
            label, tlds = split_domain(q, settings.prices)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        items = registrar.availability(label, tlds)
        expires = int(time.time()) + 600
        for item in items:
            tld = item['domain'].split('.', 1)[1]
            item.update({'annual_cents': settings.prices[tld]['register'], 'renewal_cents': settings.prices[tld]['renew'], 'currency': 'BRL'})
            if item['available']:
                item['quote_id'] = secrets.token_urlsafe(24)
                item['quote_expires'] = expires
                store.execute('INSERT INTO quotes VALUES(?,?,?,?,?)',
                              (item['quote_id'], item['domain'], item['annual_cents'], item['renewal_cents'], expires))
        return {'results': items, 'sales_ready': settings.sales_ready}

    @app.post(PREFIX + '/checkout')
    def checkout(data: CheckoutInput, request: Request):
        limit(request, 'checkout', 5, 300)
        user = current_user(request)
        if not user['verified']:
            raise HTTPException(403, 'Confirme seu e-mail antes de comprar.')
        if not settings.sales_ready:
            raise HTTPException(503, 'As compras ainda não estão disponíveis. Nenhuma cobrança foi realizada.')
        key = request.headers.get('idempotency-key', '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}', key):
            raise HTTPException(400, 'Identificador do pedido inválido. Atualize a página.')
        previous = store.one('SELECT * FROM orders WHERE user_id=? AND idempotency=?', (user['id'], key))
        if previous:
            if previous['checkout_url'] and previous['status'] == 'awaiting_payment':
                return {'order_id': previous['id'], 'checkout_url': previous['checkout_url']}
            raise HTTPException(409, 'Este pedido já foi iniciado. Consulte Meus domínios antes de tentar novamente.')
        if not data.accepted_terms:
            raise HTTPException(422, 'Confirme os dados e as condições antes de continuar.')
        if len(data.registrant.document) == 14 and not data.registrant.company:
            raise HTTPException(422, 'Informe a razão social para registrar em um CNPJ.')
        quote = store.one('SELECT * FROM quotes WHERE id=? AND expires>?', (data.quote_id, int(time.time())))
        if not quote:
            raise HTTPException(409, 'A consulta expirou. Busque novamente para atualizar o preço e a disponibilidade.')
        label, tld = quote['domain'].split('.', 1)
        current_price = settings.prices.get(tld)
        if not current_price or (quote['amount'], quote['renewal']) != (current_price['register'], current_price['renew']):
            raise HTTPException(409, 'O preço mudou. Consulte o domínio novamente.')
        if not registrar.availability(label, [tld])[0]['available']:
            raise HTTPException(409, 'Não foi possível confirmar a disponibilidade. Faça uma nova busca.')
        now, order_id = int(time.time()), secrets.token_urlsafe(24)
        try:
            store.execute('INSERT INTO orders(id,user_id,domain,amount,renewal,registrant,status,created,updated,idempotency,nameservers) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (order_id, user['id'], quote['domain'], quote['amount'], quote['renewal'], data.registrant.model_dump_json(), 'creating_checkout', now, now, key, json.dumps(settings.nameservers)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Já existe um pedido para este domínio. Consulte Meus domínios ou fale com o suporte.') from None
        order = store.one('SELECT * FROM orders WHERE id=?', (order_id,))
        try:
            result = payments.checkout(order, user['email'])
        except ProviderError:
            store.update_order(order_id, status='checkout_failed', note='O pagamento não foi iniciado. Faça uma nova busca.')
            raise
        store.execute("UPDATE orders SET status=CASE WHEN status='creating_checkout' THEN 'awaiting_payment' ELSE status END,checkout_url=?,preference_id=?,updated=? WHERE id=?",
                      (result['url'], result['id'], int(time.time()), order_id))
        return {'order_id': order_id, 'checkout_url': result['url']}

    @app.get(PREFIX + '/orders')
    def orders(request: Request):
        user = current_user(request)
        rows = store.all('SELECT id,domain,amount,renewal,status,created,expires,note,checkout_url,nameservers FROM orders WHERE user_id=? ORDER BY created DESC LIMIT 100', (user['id'],))
        for row in rows:
            if row['status'] != 'awaiting_payment':
                row.pop('checkout_url', None)
            row['nameservers'] = json.loads(row['nameservers']) if row['status'] == 'active' else []
        return {'orders': rows}

    @app.post(PREFIX + '/webhooks/mercadopago')
    def webhook(request: Request):
        payment_id = request.query_params.get('data.id', '')
        if not re.fullmatch(r'\d{1,30}', payment_id) or not payments.valid_signature(payment_id,
                request.headers.get('x-request-id', ''), request.headers.get('x-signature', '')):
            raise HTTPException(401, 'Notificação inválida.')
        try:
            accept_payment(store, payments, payment_id)
        except ValueError:
            raise HTTPException(400, 'Pagamento não corresponde ao pedido.') from None
        return {'received': True}

    return app


def app_factory():
    return create_app()
