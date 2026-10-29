# Prospecção de empresas — backend e painel privado

Serviço FastAPI independente em `apps/prospect-api`, painel `/prospeccao/` e API `/api/prospect/*`. Usa SQLite persistente e um worker separado. Não modifica o site público, o painel de visitas ou os serviços existentes. Não depende de n8n. Esta entrega adiciona código; não publica nem ativa disparos.

## O que está implementado

- Pesquisa Casa dos Dados v5 por data de abertura, em todo o Brasil, incluindo empresas sem e-mail, sem limite de 10 registros por rodada. O tamanho de página é configurável e NÃO limita o total coletado.
- Registro de progresso por dia/página. Cada página e checkpoint são gravados na mesma transação. CNPJ é texto, suporta formato alfanumérico e é único. Não armazena quadro societário nem CPF.
- Coleta diária opcional, recuperação desde `COLLECT_START_DATE` e reconsulta dos últimos sete dias para registros publicados com atraso. A cobertura é a da fonte; “complete” significa total informado pela consulta, não certificação de completude nacional.
- Cadastro de contatos verificados via API/painel. Uma fila única por CNPJ e por e-mail evita repetir a apresentação mesmo em várias execuções. Remoções, contatos prévios e respostas impedem novos envios.
- SMTP com STARTTLS obrigatório, HTML aprovado com logo CID, WhatsApp correto, domínio separado e CRM/app sob orçamento; links sem setas. Nome da empresa escapado, link de descadastro assinado, texto alternativo.
- Limite de tentativas por janela móvel de 24h e intervalo configuráveis. Ambos abrangem apenas ESTE serviço, não outros agentes nem uso manual da conta. Configure uma cota dedicada considerando os demais envios.
- Estados: `queued`, `sending`, `accepted`, `unknown`, `cancelled`, `replied`, `bounced`, `closed`, `not_interested`. `accepted` é aceite SMTP, não confirmação de entrega/leitura.
- Em falha/timeout SMTP ou interrupção do worker, a tentativa fica `unknown`, sem reenvio automático. Conferir a caixa de enviados/provedor pelo Message-ID antes de qualquer intervenção. Não há endpoint de retry para evitar duplicações acidentais.
- Descadastro GET mostra confirmação e POST remove. Também aceita POST de one-click. Pausa impede novas tentativas; não recolhe uma mensagem já em trânsito.
- Painel protegido nos endpoints por token administrativo (mínimo 32 caracteres), mantido apenas na memória da aba. Exportação CSV compatível com Excel, neutralização de fórmulas. É painel de operador único, não login multiusuário.

## Dependências reais ainda necessárias

1. **Casa dos Dados:** fornecer chave com acesso/saldo para pesquisa v5. A rota pode gerar cobrança; não foi chamada com credenciais reais. Consulte preços e condições antes de ativar. O schema público consultado não documenta o campo de e-mail no retorno: o conector NÃO inventa um mapeamento. Contatos devem ser importados e verificados separadamente; enriquecimento automático será uma integração adicional após confirmar o contrato do fornecedor.
2. **Envio:** configurar um remetente e SMTP que aceite o uso pretendido, com domínio autenticado conforme o provedor. Não há promessa de evitar spam. Nenhuma conta foi contratada/configurada nesta entrega.
3. **Histórico:** antes de ativar, importar contatos já abordados (inclusive os oito do Gmail), pedidos de remoção e devoluções com `POST /suppressions`. Dados de prospecção e credenciais ficam no banco/ambiente, nunca no GitHub público.
4. **Hospedagem:** publicar na VPS com acesso operacional e backup. O painel/serviço NÃO estão disponíveis no domínio até essa etapa.
5. **Retorno:** status de resposta/devolução é registrado pelo operador via API. Leitura automática do Gmail e webhooks de bounce ainda não estão implementados. Os eventos recebidos devem ser vinculados ao ID correto, sem endpoint público de evento não autenticado.

## Rodar localmente

```sh
python -m venv .venv-prospect
.venv-prospect/bin/pip install -r apps/prospect-api/requirements.txt
export PROSPECT_DB=/tmp/prospect-local.sqlite3
export PROSPECT_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
# Configure variáveis no processo, sem gravá-las no código.
.venv-prospect/bin/uvicorn main:app --app-dir apps/prospect-api --port 8002
```

Abra `http://127.0.0.1:8002/prospeccao/`. HTTP somente no localhost; produção exige HTTPS. Em outro processo com o MESMO ambiente, rode `python worker.py` dentro de `apps/prospect-api`. O worker exige Linux/Unix (usa flock). Há um worker por banco; ele impede uma segunda instância. Credenciais vazias impedem acesso administrativo, consulta paga e envio. Gerar `UNSUBSCRIBE_SECRET` independente do token administrativo e mantê-lo estável para preservar links enviados.

## Publicar sem interferir nos outros sites

Copiar `apps/prospect-api/.env.example` para `.env.prospect` na raiz e preencher somente no servidor. `chmod 600 .env.prospect`. Definir início de coleta e cota de envio conscientemente; defaults não coletam nem enviam. A credencial SMTP conectada no ChatGPT não é transferida automaticamente para esta aplicação.

```sh
docker compose -f compose.prospect.yaml up -d --build
```

Este Compose isolado expõe **apenas 127.0.0.1:4182**. Inspecionar o proxy existente e inserir, no virtual host de `karenangelis.com`, antes do encaminhamento geral:

```caddy
@prospect path /api/prospect/* /prospeccao /prospeccao/
handle @prospect {
    reverse_proxy 127.0.0.1:4182
}
```

O trecho pressupõe Caddy executando NO HOST, conforme a arquitetura VPS descrita no repositório. Se o proxy roda em container, conectar à rede Docker apropriada e usar `prospect-api:8002`; não usar localhost do container. Não substituir os arquivos globais de proxy ou as portas 80/443. Validar e recarregar a configuração existente após backup. Banco: volume `prospect_data`. Fazer backup consistente via SQLite backup API; não copiar arquivo aberto sem WAL.

Após verificar TLS, painel, banco persistente, histórico, descadastro e um envio de teste ao próprio remetente, ativar `COLLECT_ENABLED=true`, `AUTO_QUEUE_VERIFIED=true` se desejado, e `SEND_ENABLED=true` com `SEND_DAILY_LIMIT>0`. Alterações do env exigem recriar serviços. O botão Retomar não ignora essas travas. Limite zero desliga envio, NÃO limita coleta.

## API administrativa

Todas as rotas abaixo exigem `Authorization: Bearer <PROSPECT_ADMIN_TOKEN>`:

| Método e caminho (`/api/prospect`) | Corpo / finalidade |
|---|---|
| GET `/summary` | Contadores, configuração e últimas 90 datas de coleta |
| POST `/collect` | `{"start":"2026-10-27","end":"2026-10-27","refresh":false}`; agenda trabalho persistente |
| POST `/companies` | `cnpj,name,opened,source,city,state`; cadastro/importação |
| GET `/companies?offset=0&limit=100` | Lista paginada |
| PUT `/companies/{cnpj}/contact` | `{"email":"contato@example.com","verified":true}` |
| POST `/companies/{cnpj}/queue` | Enfileirar contato verificado; 409 se removido/duplicado/ausente |
| GET `/messages?offset=0&limit=100` | IDs e estados, sem expor HTML ou credenciais |
| POST `/messages/{id}/outcome` | `{"status":"replied"}`; também bounced, closed, not_interested |
| POST `/suppressions` | `{"email":"contato@example.com","reason":"Já abordado no Gmail"}` |
| POST `/control` | `{"paused":true}` |
| GET `/export.csv` | Controle para Excel |

Rotas públicas: `/health`, shell vazio do painel e descadastro assinado. Não expor secrets em query strings. Desabilitado access log no uvicorn para não registrar tokens de remoção; configurar também redaction/exclusão no proxy. Chave administrativa é de operador único; para uma aplicação multiusuário, substituir por autenticação de sessão/OIDC e papéis.

## Falhas, cobertura e limites

- 401/403/429, saldo insuficiente, schema inesperado e paginação truncada marcam a coleta `error`, preservando checkpoint. Reagendar com `refresh:true` após resolver; reinicia aquele dia com deduplicação. Dias recentes com erro são reconsultados no próximo ciclo diário.
- Não avançar silenciosamente se a fonte repete páginas ou retorna vazio antes do total. Se o fornecedor limita paginação total, usar exportação ou particionamento conforme contrato; esta versão sinaliza erro, não promete cobrir o excedente.
- Total e ordenação podem mudar durante uma coleta. Reconsultar dias recentes reduz lacunas, mas uma garantia rigorosa exige snapshot/cursor estável do fornecedor. Atrasos maiores que LOOKBACK_DAYS exigem ampliar a janela ou reprocessar datas anteriores.
- Cadastro valida formato de CNPJ, não dígito verificador nem situação cadastral oficial. Contato “verificado” é declaração do operador, não validação de entregabilidade SMTP.
- Envio SMTP não oferece exactly-once: mensagens ambíguas ficam para conferência. Há uma pequena janela entre última checagem de remoção e envio; cancelamentos não podem recolher e-mail em trânsito.
- O HTML é versionado em `templates/site.html`; edição visual do modelo pelo painel fica para próxima etapa. Alterações de template valem para novas mensagens, pois a fila guarda o conteúdo aprovado no momento do enfileiramento.

## Validação

```sh
python -m unittest discover -s apps/prospect-api -v
```

Testes usam HTTP mock e transporte de e-mail em memória. Nenhuma consulta paga ou mensagem externa é feita. CI próprio em `.github/workflows/prospect-api.yml`. Validar configuração Docker e proxy no servidor antes de publicar.

Referências do contrato consultado em 27/10/2026:
- https://docs.casadosdados.com.br/pesquisa-avan%C3%A7ada-de-empresas-16579062e0
- https://docs.casadosdados.com.br/informa%C3%A7%C3%B5es-b%C3%A1sicas-1278846m0

## Google Workspace — contato@karenangelis.com

O arquivo `.env.example` agora prepara SMTP `smtp.gmail.com:587` com STARTTLS,
remetente e usuário `contato@karenangelis.com`, teto de **1.500 tentativas em
24 horas móveis**, intervalo mínimo de 55 segundos e worker a cada 5 segundos.
É um teto, não uma garantia de volume ou entrega. O banco preserva a contagem
entre reinícios; os envios manuais e de outros sistemas não entram nessa contagem.

`SEND_ENABLED=false` continua até a conexão e publicação reais. No servidor,
usar uma senha de app Google em `SMTP_PASSWORD` (quando permitida pela política
da conta e com verificação em duas etapas); nunca a senha normal e nunca no Git.
A conexão Gmail do ChatGPT não fornece essa credencial ao backend.

Contas de teste têm limite de 500. A documentação do Google informa que o aumento
após o teste depende de pagamentos acumulados equivalentes a USD 100 e pode levar
até 75 dias após esse patamar. Ajustar temporariamente `SEND_DAILY_LIMIT` à cota
efetivamente disponível, descontando outros usos da caixa; contratar não comprova
liberação imediata dos 1.500. O aplicativo não contorna limites do provedor.

Qualquer falha no transporte pausa a fila persistentemente. A tentativa fica
`unknown` para reconciliação, e os demais contatos permanecem `queued`. Depois de
resolver credenciais/cota/conectividade, retomar pelo painel. Não há retry automático.

Antes da ativação: credencial no servidor, domínio e autenticação de e-mail
verificados, histórico importado, teste para a própria caixa e implantação com
banco persistente. Nenhum desses passos é comprovado apenas por abrir o Gmail.

Referências:
- https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app
- https://knowledge.workspace.google.com/admin/gmail/gmail-sending-limits-in-google-workspace
