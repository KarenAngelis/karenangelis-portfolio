# ChatGPT e Codex no piloto pessoal

O serviço usa o Codex App Server como componente de raciocínio. O banco e o backend
controlam candidaturas, Gmail e agenda. Nenhuma chave da API OpenAI é criada ou lida.

## Dois modos de autenticação

- **Desenvolvimento local**, com `CAREER_PUBLIC_URL` em endereço loopback: login
  gerenciado do Codex por código de dispositivo. É necessário habilitar esse login
  nas configurações da conta quando solicitado pelo próprio fluxo oficial.
- **Esta aplicação open source na VPS pessoal da proprietária**: registro próprio
  de **Sign in with ChatGPT (SIWC)**, autorizado para usar o plano ChatGPT e
  transferido de forma protegida para a VM. Não usar `auth.json` do Codex nesse modo.

O login gerenciado do App Server não é autenticação para um serviço comercial ou
hospedado para terceiros. Este procedimento de VM é o caminho documentado para o
mesmo aplicativo open source, a mesma pessoa e o mesmo workspace em uma VM própria.
Transformar o piloto em serviço para terceiros exige confirmar o fluxo e o acesso
apropriados com a OpenAI.

## Pareamento inicial da VPS

1. Na VM, prepare e preserve um identificador opaco próprio para o runtime, separado
   daquele usado no computador local. `SiwcCredentials.host_id()` cria uma vez o
   arquivo `host-id`, ao lado do registro configurado, com permissão `0600`.
2. No computador com o navegador e Python, abra o checkout e execute:

   ```bash
   python -m pip install -r apps/career-api/requirements-chatgpt-setup.txt
   python scripts/connect-career-chatgpt.py
   ```

   O helper abre o navegador, aguarda o retorno por até cinco minutos e salva o
   registro em configuração privada do usuário, fora do repositório. No Windows,
   o padrão é `%LOCALAPPDATA%/karen-career-manager/credentials.json`; em Linux/macOS,
   `$XDG_CONFIG_HOME/karen-career-manager/credentials.json` ou
   `~/.config/karen-career-manager/credentials.json`. O terminal mostra o caminho,
   a conta validada e os escopos, nunca os tokens. `--output` escolhe outro arquivo
   protegido fora do repositório. Reautorizar o mesmo registro exige `--replace`.
3. O helper já implementa o fluxo oficial **Registration and sign-in**, com state,
   nonce, PKCE S256, registro inicial por `dynamic_agent_client` e validação da
   assinatura do ID token via JWKS, issuer, audience, expiração e nonce. Exige os
   escopos `chatgpt.tokens.use.direct`, `resource.invoke` e `offline_access` e mantém
   a identidade do registro ao reautorizar. O callback é HTTP loopback em
   `127.0.0.1`; não é substituído pelo domínio HTTPS do portfólio.
4. Transfira **somente o registro selecionado desta aplicação** por canal protegido,
   como SSH, ao caminho configurado no servidor. O padrão é
   `/data/siwc/credentials.json`; `settings.siwc_credentials_file` permite escolher
   outro caminho protegido. Não enviar credenciais pelo chat, formulário da página,
   GitHub, e-mail ou armazenamento do navegador.
5. O arquivo deve ser regular, sem links simbólicos, pertencer ao usuário do serviço
   (UID `10001` no container) e ter permissão `0600`. O diretório deve ser privado
   e gravável pelo serviço porque tokens de renovação são rotativos. Preserve o
   arquivo `host-id` da VM ao importar um registro vindo do computador local.
6. Consulte a conexão no painel. `configured` informa que o registro tem os
   metadados e permissões necessários; `pairing_required` identifica configuração
   ausente, permissão negada ou sessão invalidada. `connected` informa que o token
   foi disponibilizado ao processo Codex. **Somente uma análise real concluída
   confirma acesso de inferência** (`access_verified`).

Copie o arquivo indicado pelo helper usando SSH/SCP para um destino privado da
sua VPS e importe-o no volume do serviço, no caminho configurado. Use o usuário e
o endereço de sua própria VPS; não envie o arquivo pelo chat. O arquivo `host-id`
do computador local fica no computador e não deve sobrescrever o `host-id` da VM.

Sem concluir esse pareamento real e a importação, a conexão da VPS permanece
pendente. Os testes do helper usam chaves de teste e HTTP simulado; nenhum login
real foi executado na construção do piloto.

## Formato do registro protegido

Use o formato retornado e validado pelo fluxo oficial. Os nomes esperados são:
`issuer`, `subject`, `client_id`, `email`, `access_token`, `refresh_token`,
`id_token`, `token_type`, `expires_in`, `scopes`, `saved_at` e
`ext_agent_host_id`. `issuer` deve ser `https://auth.openai.com` e `saved_at` deve
incluir fuso horário. Não preencher exemplos com tokens em arquivos versionados.

O serviço não revalida um OAuth inexistente nem transforma esses metadados em
prova de autenticação do usuário do site. A sessão do site continua pertencendo
ao Google; a importação administrativa de um registro local já validado é uma
etapa distinta.

O identificador estável enviado como `agent_name_hint` pelo helper é
`karen_career_manager`, o mesmo de `initialize.clientInfo.name` no App Server.
O título humano mostrado pela aplicação é “Gestor de Carreira”.

## Renovação e execução

O adaptador lê exclusivamente o arquivo configurado e renova perto do vencimento
pelo endpoint oficial, usando o `client_id` emitido, o último refresh token e o
resource `https://api.openai.com/v1`. Grava o novo conjunto inteiro atomicamente,
com modo `0600`, preservando a identidade e o host da VM. Falha temporária preserva
o registro; revogação confirmada exige novo pareamento.

Execute **um único worker/processo** para este registro. A renovação é serializada
nesse processo; não compartilhe o arquivo entre réplicas concorrentes. O Compose
do piloto executa um worker Uvicorn.

O token é passado somente pelo ambiente do processo filho (`ACCESS_TOKEN`) ao
provider Responses do Codex, com `requires_openai_auth=false` e HTTP/SSE conforme
documentado. Não aparece em argumentos, logs ou respostas do painel. Depois de
renovar, o processo é reiniciado antes da próxima análise; não se troca o token
no meio de um turno ativo. Não há mudança automática para outra forma de cobrança.

## Fontes oficiais

- [Registro e login](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [VMs próprias](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)
- [Renovação e sessões](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
- [Codex com provider SIWC](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
- [Limitações atuais](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
- [Autenticação do App Server](https://learn.chatgpt.com/docs/app-server)
