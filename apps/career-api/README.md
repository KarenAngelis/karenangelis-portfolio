# Gestor de Carreira · piloto pessoal

Área privada em `/carreira/`, com API em `/api/career/`. O portfólio público e o
app Kotlin permanecem com seus serviços próprios. O primeiro acesso do piloto é
restrito ao e-mail definido em `CAREER_OWNER_EMAIL`.

## Fluxo implementado

1. Login Google e conexão adicional de Gmail/Agenda por OAuth, com renovação offline.
2. Importação dos dados públicos já existentes em `web/data/`, edição do currículo,
   preferências e respostas, e sincronização dos repositórios públicos do GitHub.
3. Consulta das fontes Greenhouse/Lever cadastradas por empresa e inclusão manual
   do link original de uma vaga. A coleta ocorre no servidor a cada dez minutos.
4. Compatibilidade explicada, verificação geográfica e preparação pelo Codex.
5. Candidatura por e-mail quando o anúncio publica um canal apropriado ou a
   proprietária informa esse canal. O envio automático segue a preferência salva.
6. Histórico persistente, material utilizado, comprovante Gmail e acompanhamento
   das respostas das conversas conhecidas. Um erro de envio gera reconciliação em
   SENT, sem repetir automaticamente o envio.
7. Entrevistas explícitas em convites ICS ou com instantes ISO/fuso verificáveis
   são registradas na agenda própria. Também há cadastro manual de uma entrevista
   confirmada. O serviço não envia convites nem confirma presença ao recrutador.

O piloto não oferece descoberta universal de vagas, submissão automática a todos
os portais, resolução de avaliações individuais ou acesso aos repositórios privados.
Formulários sem conector permanecem como próxima ação. O e-mail do piloto é uma
apresentação fundamentada, sem fingir anexar um PDF. Exportação/anexo de versões
de currículo e importação de processos antigos são próximas entregas.

Cancelamentos de convites são sinalizados e nunca criam uma nova entrevista.
Remarcação/remoção de um evento já registrado precisa de conferência no piloto.

## Estrutura

| Arquivo | Responsabilidade |
| --- | --- |
| `main.py` | Contratos HTTP, autenticação, sessão e CSRF |
| `career/store.py` | SQLite, snapshots imutáveis, histórico, deduplicação e leases |
| `career/matching.py` | Regras explícitas e pontuação de aderência |
| `career/sources.py` | Leitura das fontes de vagas e GitHub |
| `career/google.py` | OAuth, tokens cifrados, Gmail e Calendar |
| `career/codex.py` | Processo de raciocínio isolado, sem efeitos externos |
| `career/siwc.py` | Registro próprio do plano ChatGPT e renovação |
| `career/pipeline.py` | Busca, preparação, execução e acompanhamento |

Os efeitos pertencem ao backend. Conteúdos de vagas, currículos, repositórios e
e-mails entram como dados; não alteram as permissões do agente. O Codex não recebe
as credenciais Google e não controla shell, e-mail ou agenda diretamente.

## Executar e verificar localmente

Na raiz do repositório, crie um ambiente Python e instale
`apps/career-api/requirements.txt` e, para os testes do pareamento,
`apps/career-api/requirements-chatgpt-setup.txt`. Para usar o frontend e o proxy de desenvolvimento:

```bash
CAREER_DEV_PYTHON="$PWD/.venv/bin/python" npm run dev
```

No PowerShell, configure `$env:CAREER_DEV_PYTHON` com o caminho de
`.venv/Scripts/python.exe` e execute `npm run dev`. A API é iniciada como processo
filho; o worker fica desligado nesse modo. Abra `http://127.0.0.1:4173/carreira/`.

```bash
PYTHONPATH=apps/career-api .venv/bin/python -m unittest discover -s apps/career-api/tests -v
npm run sources
npm run check
```

Os testes simulam apenas serviços externos; banco, deduplicação, sessões, snapshots
e linha do tempo usam a implementação real. Eles não enviam e-mails ou criam eventos
na conta da proprietária. É necessário validar as conexões reais após o setup.

## Configurar o Google uma vez

No projeto Google Cloud da proprietária, habilite Gmail API e Calendar API e crie
um cliente OAuth de aplicação web. Cadastre o retorno exato:

`https://karenangelis.com/api/career/auth/google/callback`

Forneça `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `CAREER_ENCRYPTION_KEY` e
`CAREER_OWNER_EMAIL` no ambiente privado do serviço. A chave de cifragem deve ser
uma chave Fernet válida gerada e guardada no servidor. Preserve-a nos backups;
sem ela os tokens armazenados não podem ser recuperados. Nunca coloque credenciais
em `web/`, no Git ou em respostas do modelo.

O login solicita identidade básica. O botão de conexão adicional solicita
`gmail.readonly`, `gmail.send` e `calendar.events.owned`. O acesso do Gmail fica
restrito às operações implementadas; não há permissão para excluir mensagens.
O modo External/Testing do Google expira refresh tokens após sete dias para esses
escopos. O piloto pessoal pode usar a exceção de verificação aplicável, mantendo
os avisos e limites do Google. Publicar o produto para terceiros exige revisar o
cadastro e os requisitos correspondentes.

Fontes: [OAuth de servidor](https://developers.google.com/identity/protocols/oauth2/web-server),
[escopos Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes),
[escopos Calendar](https://developers.google.com/workspace/calendar/api/auth),
[expiração](https://developers.google.com/identity/protocols/oauth2/),
[uso pessoal](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification#exceptions).

## Conectar ChatGPT/Codex

Siga [CHATGPT_SETUP.md](CHATGPT_SETUP.md). O modo da VPS pessoal usa o registro
próprio do aplicativo open source autorizado pelo Sign in with ChatGPT. Sem esse
pareamento, o painel mostra a conexão pendente. A existência de uma assinatura,
de um binário ou de um catálogo de modelos não confirma acesso de inferência.

## Publicação e operação

O Compose inclui `career-api:8010` apenas na rede interna e o volume `career_data`.
O Caddy encaminha `/api/career/*`; os arquivos de `/carreira/` não contêm dados
privados. A API responde com `Cache-Control: no-store`. Faça backup privado do
volume, incluindo chave de cifragem e registro SIWC por canais próprios.

Use **uma réplica e um processo Uvicorn**. O piloto combina lock em memória e
lease no banco; renovação de tokens e envios não foram projetados para múltiplas
réplicas. O limite conservador observa até vinte mensagens enviadas no Gmail na
janela anterior de sessenta minutos. Isso não constitui uma reserva atômica com
agentes externos ou formulários: antes de habilitar o novo executor em produção,
concilie os executores existentes e seu controle compartilhado. Nenhuma automação
externa é pausada ou alterada por este código.

Depois de ler o estado real da VPS, conforme `docs/deployment.md`, configure os
segredos, construa `career-api` e `web`, valide o Caddy e confirme o fluxo completo:
login, importação, fonte real, análise, candidatura permitida com recibo, resposta
e entrevista no calendário. Verifique também o portfólio e os demais sites.

Estado desta entrega: código e testes preparados; sem publicação na VPS ou login
real nesta sessão. A prévia supervisionada não respondeu nesta execução, então a
verificação visual no navegador permanece pendente. O container precisa ser
construído e validado no ambiente com Docker antes da publicação.
