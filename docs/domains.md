# Loja de domínios — /dominios/

## Estado da entrega

Implementação no repositório: busca por API, preços anuais em reais, cadastro/login com senha ou Google,
verificação de e-mail, recuperação de senha, checkout, webhook de pagamento, registro, confirmação,
reembolso de falhas explícitas e painel privado dos pedidos. Links na home e em `/empresas/`.

**Vendas desativadas por padrão.** Não existem credenciais ou preços comerciais aprovados neste repositório.
A página não inventa disponibilidade e não permite pagar enquanto faltar configuração.
Integrações têm testes locais com respostas simuladas e verificações externas parciais; o fluxo completo
de pagamento e registro ainda precisa ser homologado. A página e a API foram publicadas na VPS em 30/10/2026, com vendas desativadas. O checkout usado é o **Checkout Pro**:
o cliente sai temporariamente para a página segura do Mercado Pago e retorna à loja. Não é checkout
transparente embutido. Até 5 parcelas são solicitadas; elegibilidade, parcela mínima e juros dependem
do meio de pagamento. Não anunciamos “5x sem juros”.

Renovação e configuração de registros DNS são assistidas pelo atendimento nesta versão. Não há renovação
automática, compra de vários anos, transferências, código EPP, editor de zona DNS, premium ou IDN.
O painel apresenta a validade confirmada e os nameservers usados no pedido. Não confundir esses
nameservers com os registros A/CNAME/MX/TXT da hospedagem.

## Componentes

- `web/dominios/`: HTML, CSS e JS sem framework, alinhados ao portfólio.
- `apps/domains-api/`: FastAPI na porta interna 8002; SQLite no volume `domains_data`.
- Caddy encaminha `/api/domains/*`. O backend não publica porta no host.
- Os dois Compose incluem o serviço e leem opcionalmente `.env.domains` (Compose 2.24+).
- CI: `domains` executa `python -m unittest -v`.
- Um processo Uvicorn e um worker por volume. Não escalar réplicas sem migrar coordenação/armazenamento.

## Configuração privada

Copie `.env.domains.example` para `.env.domains` **na VPS**, com permissão 600. Nunca envie os valores
por commit ou inclua o arquivo em artefatos públicos. `DOMAINS_SALES_ENABLED=false` bloqueia novos
pedidos; com as demais credenciais válidas, os pedidos pagos continuam sendo processados.

1. **ResellerClub:** criar/habilitar uma conta de revenda, obter Reseller ID e API Key, autorizar o IP
   de saída da VPS e confirmar saldo, produtos habilitados, moeda e custos de registro/renovação.
   O adaptador usa a HTTP API documentada: sandbox `https://test.httpapi.com/api/`, live
   `https://httpapi.com/api/`. `DOMAINS_LIVE` seleciona ambos os ambientes de forma explícita.
   Verifique se a conta contratada mantém acesso a essa API; não trocar para v2 sem adaptar contratos.
2. **Preços:** `DOMAIN_PRICES_JSON` recebe preços finais de venda em **centavos BRL**, por exemplo
   `{"com":{"register":7500,"renew":8500}}` (exemplo, **não recomendação comercial**).
   Configure somente as extensões habilitadas e homologadas: `com`, `net`, `org`, `com.br`.
   Calcule custos do fornecedor, câmbio, parcelamento, tributos, suporte e margem. Não há conversão
   cambial nem atualização automática dos custos nesta versão. Revise a tabela quando o custo mudar.
3. **.com.br:** homologar `BrOrgContact` com CPF/CNPJ e `BrContact` separado para funções administrativas.
   Titulares existentes podem precisar de mudança de provedor no Registro.br. A interface orienta
   a falar com atendimento antes de pagar; não executamos essa mudança automaticamente. Habilite
   `com.br` na tabela somente após testar os cenários de titular novo e existente na conta contratada.
4. **DNS:** `DOMAIN_NAMESERVERS` precisa ter ao menos dois servidores reais já provisionados por seu
   fornecedor de DNS. Configurar nameservers não cria uma zona DNS. Provisionar a zona e os registros
   da hospedagem é tarefa operacional separada. Os servidores ficam congelados por pedido.
5. **Mercado Pago:** credencial de teste/live correspondente ao ambiente, `MERCADOPAGO_COLLECTOR_ID`
   da conta recebedora, segredo de Webhooks e notificações de **payments** para
   `https://karenangelis.com/api/domains/webhooks/mercadopago`. Usar Webhooks com assinatura, não IPN.
   Configurar regras de parcelamento na conta e testar retorno/assinatura/reembolso.
6. **Google:** OAuth Web Client com origem JavaScript `https://karenangelis.com`; colocar o client ID
   público em `GOOGLE_CLIENT_ID`. O servidor valida assinatura/audience/issuer/expiração pelo SDK oficial
   e nonce de uso único. Google não vincula automaticamente uma conta de senha existente.
7. **E-mail:** SMTP autenticado via STARTTLS (porta 587), remetente autorizado e SPF/DKIM apropriados.
   Os envs `DOMAIN_SMTP_*` são exclusivos desta aplicação. Não reutilizar/exportar segredos de outra
   automação sem configuração explícita. Mensagens de verificação e recuperação somente.
8. Confirmar dados comerciais, atendimento, condições publicadas e operação de renovação/reembolso;
   homologar o fluxo antes de `DOMAINS_LIVE=true` e `DOMAINS_SALES_ENABLED=true`.

## Publicação no host existente

Consultar `docs/deployment.md` e inventariar o checkout/containers atuais antes de mudar a VPS.
Há histórico de alterações locais não sincronizadas: preservar as rotas e serviços de e-mail,
estatísticas, Clycka e Luniay. Fazer backup do SQLite e do Compose/Caddy antes de atualizar.
Não sobrescrever a pasta remota inteira nem fazer reset forçado.

Após sincronizar esta mudança e configurar `.env.domains`:

```sh
docker compose -p karenangelis-portfolio -f compose.vps.yaml config --quiet
docker compose -p karenangelis-portfolio -f compose.vps.yaml up -d --build --no-deps domains-api
docker compose -p karenangelis-portfolio -f compose.vps.yaml up -d --build --no-deps web
```

O proxy externo já aponta para a porta 4180; não precisa alterar MX/DNS do `karenangelis.com`.
Validar `/api/domains/health`, `/api/domains/config`, `/dominios/`, links da home e de `/empresas/`.
Conferir login, e-mail, domínio disponível/ocupado, CPF/CNPJ, checkout, webhook, painel e retorno em
celular. Fazer os testes externos em sandbox, sem registrar domínios ou cobrar pessoas reais.
Não ativar live enquanto falhas de integração permanecerem abertas.

## Estados e recuperação

`creating_checkout → awaiting_payment → paid → registering → registration_pending → active`.
Disponibilidade revalidada antes do checkout e do registro. Cotação expira em 10 minutos, link de
pagamento em 30 minutos; após uma hora, pedido não pago expira. Um pagamento tardio é encaminhado
para reembolso, não reaproveitado para tentar registrar o domínio novamente.

O webhook verifica HMAC, timestamp, ID, valor exato, moeda, recebedor, ambiente e referência do pedido,
consultando a API do Mercado Pago. Redirect do navegador nunca muda um pedido para pago.
Um segundo pagamento aprovado para o mesmo pedido gera reembolso com chave estável. Uma falha
explícita do fornecedor gera `refund_pending`; status de refund aprovado confirma `refunded`.

**Timeout de registro é ambíguo. Não repetir o POST.** O pedido fica `review_required`, preservado após
reinício, para conferir no fornecedor. Operações interrompidas por mais de cinco minutos também entram
em revisão. Uma resposta com ID do fornecedor não é sucesso: a leitura seguinte deve confirmar
domínio, customer ID, estado Active e vencimento futuro.

Monitorar diariamente os estados `review_required`, `refund_pending`, `registration_pending` e a tabela
`alerts`. O worker registra apenas mensagens genéricas, sem segredos nem dados pessoais. Enquanto não
houver painel administrativo, a inspeção deve ser feita por operador autenticado na VPS:

```sql
SELECT id,domain,status,updated,note FROM orders
WHERE status IN ('review_required','refund_pending','registration_pending');
SELECT order_id,kind,created FROM alerts ORDER BY created;
```

Para revisão: conferir pedido/pagamento na conta correta dos dois fornecedores e a titularidade.
Se o domínio foi registrado, vincular o ID correto e retornar a `registration_pending` somente após
conferir o customer ID. Se não houve registro, confirmar isso com o fornecedor antes de iniciar o
reembolso no Mercado Pago. Registrar o resultado no pedido. Nunca marcar `active` com base apenas no
pagamento. Nunca repetir criação de cliente/contato/registro incerto por tentativa e erro.
Se um webhook não chegar, usar o reenvio autenticado do painel Mercado Pago; não há varredura de todos
os pagamentos nesta versão. Os eventos inválidos não são aceitos e pedidos pendentes não são liberados.

Renovações: manter acompanhamento operacional de vencimentos e atender pedidos de renovação antes
da expiração. A interface informa que a renovação não é automática. Esta entrega não envia lembretes
de vencimento nem confirma uma renovação que não foi realizada.

## Segurança e dados

Senhas scrypt com salt; sessões opacas guardadas por hash; cookie Secure/HttpOnly/SameSite; mutações
JSON com origem exata; rate limit persistente; tokens de e-mail e Google expiráveis de uso único.
Dados da conta e pedidos são filtrados pelo usuário autenticado. Preço/valor são definidos no servidor;
nenhum token de provedor, documento ou senha é retornado pelo painel. Campos inválidos não são ecoados.
Contas sem e-mail confirmado não compram. Redefinição de senha invalida sessões anteriores.

O SQLite contém dados pessoais necessários ao registro: proteger o volume, backups e acesso ao host;
definir política de retenção e atendimento de solicitações. Não copiar o banco para a pasta pública.
O worker precisa usar volume durável e backups consistentes (SQLite backup API); nenhum estado de
pagamento ou registro depende apenas da memória. Cópias de teste devem usar dados sintéticos.

## Verificação local

```sh
python -m venv .venv
.venv/bin/pip install -r apps/domains-api/requirements.txt
cd apps/domains-api
../../.venv/bin/python -m unittest -v
```

Na raiz: `npm run sources && npm run check`. A suíte cobre autenticação, isolamento, validade/preço,
assinatura de webhook, múltiplas entregas, corrida entre workers, indisponibilidade, resposta incerta,
refund, pagamento tardio, chargeback e mapeamento de contatos .br. Respostas externas são simuladas;
esses testes não substituem homologação com as contas de fornecedor.

## Referências oficiais usadas

- https://manage.resellerclub.com/kb/answer/764 — disponibilidade e premium/trademark.
- https://manage.resellerclub.com/kb/answer/790 — contatos e requisitos .br.
- https://cp.resellerclub.com/kb/answer/804 — cliente.
- https://cp.resellerclub.com/kb/node/91 — política de senha do cliente (9–16 caracteres).
- https://manage.resellerclub.com/kb/answer/752 — registro.
- https://manage.resellerclub.com/kb/answer/770 — confirmação e titularidade.
- https://cp.resellerclub.com/kb/answer/753 — autenticação e endpoints HTTP.
- https://www.mercadopago.com.br/developers/en/reference/online-payments/checkout-pro-preferences/create-preference/post
- https://www.mercadopago.com.br/developers/en/docs/checkout-pro-preferences/payment-notifications
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token

## Publicação de 30/10/2026

PR #4 integrado ao main no commit `6ecee51335ff317a6977806552252061c8af999d`. Todos os seis jobs do GitHub passaram, incluindo 32 testes da API de domínios.

Atualização seletiva em `/opt/karenangelis-portfolio`, preservando o mount local `web/meet-italiano` e os demais serviços. Backup em `/opt/karenangelis-backups/domains-20261030T121846Z`. Imagens `web` e `domains-api` construídas, Caddy validado e somente esses serviços atualizados.

HTTPS: 200 em `/`, `/empresas/`, `/dominios/`, `/meet-italiano/`, `/api/profile` e `/api/stats/health`. `/api/domains/health` retornou `status: ok`. Configuração publicada: `search_ready=false`, `sales_ready=false`, `email_ready=false`, Google sem client ID; ainda não há `.env.domains` com fornecedores configurados. Nenhum pagamento ou registro real foi executado.

A rede corporativa WEG bloqueou a abertura no navegador conectado por reputação não verificada. Conferência visual ficou pendente; nenhum bloqueio de rede foi contornado.

## Configuração de 02/11/2026

Configuração privada dos fornecedores e SMTP aplicada na VPS. Busca real de disponibilidade e preços
verificada no navegador; envio de e-mail aceito pelo SMTP. A configuração de processamento está completa,
mas `DOMAINS_SALES_ENABLED=false` permanece até concluir a preparação operacional e a homologação.
Google OAuth foi configurado posteriormente na VPS com cliente restrito a `https://karenangelis.com`;
o botão de login foi conferido no navegador, mas a autenticação completa ainda precisa ser validada.
`.com.br` ainda não está habilitado; cadastro com e-mail e senha está disponível.

Uma preferência de Checkout Pro foi criada em sandbox pelo adaptador real. A página exibiu o valor
esperado e opções de 1 a 5 parcelas. Nenhum pagamento ou registro real foi realizado; isso não valida
o ciclo completo de webhook, registro, confirmação e reembolso externo.

Corrigida a senha automática do cadastro na registradora para respeitar a política de 9–16 caracteres,
com maiúscula, minúscula, número e símbolo permitido. Um teste de regressão reproduziu a falha anterior;
os 33 testes da API passaram após a correção. Esses testes usam fornecedores simulados.

## Preparação de envio automático à registradora — ainda não ativada

O objetivo é iniciar o envio do custo de registro após a confirmação do pagamento e disponibilidade
do dinheiro, manter a margem na conta recebedora e registrar o domínio após a confirmação do crédito.
Encontrada a API Payouts do Mercado Pago, que permite transferências bancárias e Pix.

`payouts.py` prepara o transporte via Pix, com credencial separada da cobrança, validação da identidade
e do ambiente, destino configurado, limite em centavos, referência estável, assinatura Ed25519 em
produção e consulta de status. Uma resposta 202 apenas inicia o processamento. Falhas de escrita são
tratadas como incertas, sem repetição automática; erros não exibem credenciais ou dados do destinatário.
O modo padrão é `disabled`, o limite é zero e transferências reais exigem configuração explícita.

**Este módulo não está conectado ao checkout nem ao worker e não foi publicado na VPS.** Não representa
uma recarga automática funcional. Os 12 novos testes são simulados; não houve transferência externa.

Teste externo posterior: a credencial de sandbox foi confirmada em `/users/me` como conta de teste.
O `POST /v1/payouts`, com headers de sandbox e dados do exemplo oficial, retornou HTTP 403; nenhum
payout foi criado. A liberação/permissão de Payouts para essa aplicação ainda precisa ser esclarecida
com o Mercado Pago. O código já passou nas verificações de CI, mas isso não substitui a homologação.
O par Ed25519 foi preparado no host, fora do repositório e com chave privada protegida; a chave pública
ainda não foi cadastrada junto ao Mercado Pago.

Antes de conectar ou habilitar essa etapa:

1. Obter da ResellerClub um destino oficial, a forma de vincular cada pagamento à conta de revenda,
   as taxas e uma confirmação verificável do crédito. Não assumir que uma transferência para uma
   conta bancária genérica se transforma automaticamente em saldo de revenda. A API para adicionar
   fundos de clientes/sub-revendedores não é uma recarga do saldo contratado junto ao fornecedor.
2. Homologar Payouts com credencial de teste e uma conta destinatária de teste. Para produção,
   cadastrar a chave pública na equipe de Integrações do Mercado Pago; chave privada somente no host,
   com permissão 600. Não usar a credencial real da cobrança em testes.
3. Implementar o diário durável de remessas por pedido: congelar custo/taxas/destino/referência antes
   do envio, impedir duplicação inclusive após expirar a idempotência do provedor e reconciliar
   estados incertos antes de qualquer nova escrita. Persistir payout e transaction IDs.
4. Revalidar o pagamento e a disponibilidade do dinheiro antes da remessa. Revalidar o domínio antes
   do envio e antes do registro. Não iniciar registro até confirmar o crédito do fornecedor; tratar
   falhas, pagamentos estornados e domínio indisponível sem confundir remessa com reembolso ao cliente.
5. Confirmar recebedor, teto por operação, tratamento de taxas e prazos de recebimento antes de
   autorizar transferências reais. Concluir a homologação externa antes de habilitar vendas.

Não é necessário depositar saldo real para preparar e executar a homologação em sandbox. Aprovação de
pagamento, disponibilidade do dinheiro, conclusão da transferência e crédito na revenda são etapas
distintas, com confirmações próprias.

Referências: https://www.mercadopago.com.br/developers/pt/docs/payouts/overview,
https://www.mercadopago.com.br/developers/pt/docs/payouts/integration-test e
https://www.mercadopago.com.br/developers/pt/docs/payouts/go-to-production.

