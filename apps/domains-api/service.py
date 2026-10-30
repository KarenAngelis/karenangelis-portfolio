"""Durable order processing. Never repeat an ambiguous domain registration."""
import json
import time

from providers import ProviderError, Rejected


def accept_payment(store, payments, payment_id):
    payment = payments.payment(payment_id)  # always fetch authoritative data, never trust callback body
    if str(payment.get('id')) != payment_id:
        raise ValueError('Pagamento inválido.')
    order = store.one('SELECT * FROM orders WHERE id=?', (payment.get('external_reference', ''),))
    if not order:
        return
    if not payments.matches(payment, order):
        store.alert(order['id'], 'payment_mismatch')
        raise ValueError('Pagamento não corresponde ao pedido.')
    status = payment.get('status')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        order = dict(db.execute('SELECT * FROM orders WHERE id=?', (order['id'],)).fetchone())
        db.execute('INSERT INTO payment_events VALUES(?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET status=excluded.status,updated=excluded.updated',
                   (payment_id, order['id'], status, int(time.time())))
        if status == 'approved':
            if order['payment_id'] and order['payment_id'] != payment_id:
                db.execute('INSERT OR IGNORE INTO alerts(order_id,kind,created) VALUES(?,?,?)',
                           (order['id'], 'duplicate_payment:' + payment_id, int(time.time())))
            elif not order['payment_id']:
                # A late payment cannot reopen an expired order: refund instead.
                next_status = 'paid' if order['status'] in {'awaiting_payment','creating_checkout'} else 'refund_pending'
                db.execute('UPDATE orders SET payment_id=?,status=?,updated=? WHERE id=?',
                           (payment_id, next_status, int(time.time()), order['id']))
        elif status in {'refunded', 'charged_back'} and order['payment_id'] == payment_id:
            next_status = 'refunded' if order['status'] in {'refund_pending', 'paid', 'awaiting_payment'} else 'review_required'
            db.execute('UPDATE orders SET status=?,updated=? WHERE id=?', (next_status, int(time.time()), order['id']))
            db.execute('INSERT OR IGNORE INTO alerts(order_id,kind,created) VALUES(?,?,?)',
                       (order['id'], 'payment_' + status, int(time.time())))


def process_order(store, registrar, payments, order):
    order_id = order['id']
    if order['status'] == 'paid':
        claimed = store.execute("UPDATE orders SET status='registering',updated=? WHERE id=? AND status='paid'",
                                (int(time.time()), order_id))
        if not claimed:
            return
        try:
            # Recheck payment immediately before irreversible registration.
            payment = payments.payment(order['payment_id'])
            if payment.get('status') != 'approved' or not payments.matches(payment, order):
                store.update_order(order_id, status='review_required', note='Pagamento em análise. Fale com o suporte.')
                store.alert(order_id, 'payment_before_registration')
                return
            label, suffix = order['domain'].split('.', 1)
            available = registrar.availability(label, [suffix])[0]
            if not available['available']:
                if available['status'] == 'unknown':
                    raise ProviderError('Disponibilidade não confirmada')
                store.update_order(order_id, status='refund_pending', note='O domínio deixou de estar disponível. Reembolso solicitado.')
                return
            user = store.one('SELECT email FROM users WHERE id=?', (order['user_id'],))
            contact = json.loads(order['registrant'])
            if not order['customer_id']:
                # Reuse only the same authenticated user's already-persisted customer ID.
                previous = store.one('SELECT customer_id FROM orders WHERE user_id=? AND customer_id IS NOT NULL LIMIT 1', (order['user_id'],))
                order['customer_id'] = previous['customer_id'] if previous else registrar.customer(contact, user['email'])
                store.update_order(order_id, customer_id=order['customer_id'])
            if not order['contact_id']:
                order['contact_id'] = registrar.contact(contact, user['email'], order['customer_id'],
                                                         'BrOrgContact' if suffix == 'com.br' else 'Contact')
                store.update_order(order_id, contact_id=order['contact_id'])
            if not order['admin_contact_id']:
                order['admin_contact_id'] = registrar.contact(contact, user['email'], order['customer_id'], 'BrContact') if suffix == 'com.br' else order['contact_id']
                store.update_order(order_id, admin_contact_id=order['admin_contact_id'])
            # Persist registering before the call. A crash/timeout requires operator reconciliation,
            # not another POST (the provider does not offer an idempotency key for registration).
            result = registrar.register(order)
            provider_id = result.get('entityid') or result.get('orderid')
            if not provider_id:
                raise ProviderError('Registro sem identificador')
            store.update_order(order_id, registrar_order_id=str(provider_id))
            if not store.update_order(order_id, from_status='registering', status='registration_pending',
                                      note='Pagamento recebido. Aguardando confirmação do registro.'):
                store.alert(order_id, 'payment_changed_during_registration')
        except Rejected:
            store.update_order(order_id, from_status='registering', status='refund_pending', note='Não foi possível registrar o domínio. Reembolso solicitado.')
        except ProviderError:
            store.update_order(order_id, from_status='registering', status='review_required', note='Estamos conferindo o registro. Não faça outro pagamento; fale com o suporte.')
            store.alert(order_id, 'registration_uncertain')
    elif order['status'] == 'registration_pending':
        try:
            data = registrar.details(order)
            if data.get('domainname') != order['domain'] or str(data.get('customerid')) != order['customer_id']:
                store.update_order(order_id, status='review_required')
                store.alert(order_id, 'registrar_owner_mismatch')
            elif data.get('currentstatus') == 'Active' and int(data.get('endtime', 0)) > time.time():
                store.update_order(order_id, from_status='registration_pending', status='active', expires=int(data['endtime']),
                                   note='Domínio registrado. Confira também o e-mail de verificação do titular.')
            elif time.time() - order['updated'] > 86400:
                store.update_order(order_id, status='review_required', note='O registro está demorando mais que o esperado. Fale com o suporte.')
                store.alert(order_id, 'registration_delayed')
        except (ProviderError, ValueError, TypeError):
            pass  # Read-only confirmation is safe to retry next cycle.
    elif order['status'] == 'refund_pending':
        try:
            result = payments.refund(order['payment_id'])
            if result.get('status') == 'approved':
                store.update_order(order_id, status='refunded', note='Reembolso confirmado. O prazo para receber depende do meio de pagamento.')
        except ProviderError:
            store.alert(order_id, 'refund_retry')


def tick(store, registrar, payments):
    now = int(time.time())
    # The payment link expires after 30 minutes; retain a 30-minute settlement buffer.
    store.execute("UPDATE orders SET status='expired',updated=? WHERE status='awaiting_payment' AND created<? AND payment_id IS NULL", (now, now-3600))
    # Abandoned work is never blindly replayed after a process crash.
    for row in store.all("SELECT id FROM orders WHERE status IN ('registering','creating_checkout') AND updated<?", (now-300,)):
        store.update_order(row['id'], status='review_required', note='Estamos conferindo seu pedido. Fale com o suporte antes de tentar novamente.')
        store.alert(row['id'], 'interrupted_operation')
    for order in store.all("SELECT * FROM orders WHERE status IN ('paid','registration_pending','refund_pending') ORDER BY created LIMIT 20"):
        process_order(store, registrar, payments, order)
    # Extra approved payments for the same order are refunded, with a stable key.
    for alert in store.all("SELECT * FROM alerts WHERE kind LIKE 'duplicate_payment:%'"):
        payment_id = alert['kind'].split(':', 1)[1]
        try:
            result = payments.refund(payment_id)
            if result.get('status') == 'approved':
                store.execute('DELETE FROM alerts WHERE id=?', (alert['id'],))
        except ProviderError:
            pass
    for table in ('sessions', 'tokens', 'quotes'):
        store.execute(f'DELETE FROM {table} WHERE expires<?', (now,))
