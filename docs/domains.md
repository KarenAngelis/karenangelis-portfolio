# Loja de domínios — /dominios/

## Estado da entrega

Implementação no repositório: busca por API, preços anuais em reais, cadastro/login com senha ou Google,
verificação de e-mail, recuperação de senha, checkout, webhook de pagamento, registro, confirmação,
reembolso de falhas explícitas e painel privado dos pedidos. Links na home e em `/empresas/`.

**Vendas desativadas por padrão.** Não existem credenciais ou preços comerciais aprovados neste repositório.
A página não inventa disponibilidade e não permite pagar enquanto faltar configuração.
Integrações foram verificadas com testes locais e respostas simuladas; a homologação com contas reais
dos fornecedores e a publicação na VPS ainda precisam ocorrer. O checkout usado é o **Checkout Pro**:
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
- https://manage.resellerclub.com/kb/answer/752 — registro.
- https://manage.resellerclub.com/kb/answer/770 — confirmação e titularidade.
- https://cp.resellerclub.com/kb/answer/753 — autenticação e endpoints HTTP.
- https://www.mercadopago.com.br/developers/en/reference/online-payments/checkout-pro-preferences/create-preference/post
- https://www.mercadopago.com.br/developers/en/docs/checkout-pro-preferences/payment-notifications
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
