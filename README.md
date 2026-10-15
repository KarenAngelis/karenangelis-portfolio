# Karen Angelis · portfólio interativo

Portfólio para `karenangelis.com`, com habilidades demonstradas por experiências clicáveis, links para Luniay e Clycka e projetos públicos do GitHub.

Publicado na VPS Hostinger em 7 de outubro de 2026: https://karenangelis.com.

- Currículo em app web Kotlin/JS + API Go: https://karenangelis.com/app/?version=kotlin
- Currículo HTML, legível sem JavaScript e imprimível: `/curriculo/`
- Demonstração histórica do currículo web: https://karenangelis.com/demos/curriculo/
- Busca de notícias + FastAPI: https://karenangelis.com/demos/trends/
- Documentação interativa da API: https://karenangelis.com/docs

A entrada da página inicial apresenta a stack, links para projetos e currículo HTML, seguida por três projetos selecionados com seu estado atual. O laboratório e todas as demonstrações continuam disponíveis. O card do currículo em app usa um print real e abre o app Compose Multiplatform compilado para WebAssembly em `/app/?version=kotlin`, conectada à API Go, sem instalação ou download. Os links de APK e abertura nativa foram retirados do fluxo público. No computador, o app fica centralizado com largura máxima de 420px, sem moldura de telefone, iframe ou apresentação externa. No celular, usa toda a largura e altura disponíveis. A interface é desenhada pelo Compose, com navegação interna e a mesma implementação usada no Android. Android e web executam as mesmas telas, navegação, busca e cliente da API, definidos em `apps/resume-compose/shared/src/commonMain`. A versão web é compilada do app para WebAssembly; ela não é uma página HTML recriando suas telas nem um emulador de APK. Interações web foram testadas no navegador local. A rede corporativa WEG bloqueou o domínio público por reputação ainda não verificada; a inspeção visual do endereço público nesse PC ficou limitada por esse filtro.

## Entrada de recrutamento e currículo HTML

- `/curriculo/` é gerado de `web/data/profile.json`; experiência, projetos, formação e idiomas são HTML estático e continuam legíveis sem JavaScript. O botão de impressão abre o diálogo nativo do navegador para imprimir ou salvar em PDF. Não há um PDF estático novo.
- Após mudar os dados do perfil, rode `npm run resume`. O comando `npm run check` verifica se o HTML gerado está atualizado.
- `web/assets/resume.css` contém o layout responsivo e as regras de impressão. O seletor existente mantém os quatro idiomas; novos textos ficam em `web/data/translations.json`.
- `/app/` mantém o aplicativo Kotlin/WebAssembly e um link permanente para o currículo HTML. Falhas de carregamento, exceções após a criação do canvas e perda do contexto gráfico exibem recuperação; a existência do canvas não é tratada como prova de renderização.
- Os arquivos `index.html`, `shell.css` e `shell.js` de `web/app/` devem continuar idênticos aos de `apps/resume-compose/shared/src/wasmJsMain/resources/`, para que um novo build não remova a recuperação.
- `npm run check` executa também os testes de entrada/currículo e os cenários de falha do shell. Esses testes usam DOM simulado; não substituem uma inspeção visual em desktop/mobile nem um smoke test do bundle real antes de publicar.

## Estrutura

```text
web/                  Portfólio responsivo e demonstrações no navegador
web/data/profile.json Dados compartilhados do currículo
apps/trends-api/      FastAPI: Google Trends RSS → JSON
apps/resume-api/      Go: endpoint de currículo
apps/resume-kotlin/   Interface Kotlin/JS que consome a API Go
apps/resume-android/  Aplicativo Android nativo com Kotlin, dados offline e API Go
infra/                Caddy e imagens Docker para a VPS
compose.yaml          Serviços da publicação
```

## Recursos para quem lê código

A página inicial foi pensada para desenvolvedores: além de testar, dá para inspecionar.

- **Terminal do topo** (`web/assets/terminal.js`): comandos reais sobre `profile.json` e as APIs (`help`, `skills fastapi`, `curl /api/profile`, `cat main.go`).
- **Console de API** (`web/assets/api-console.js`, `api.js`): envia requisições a `/api/news`, `/api/profile` e `/openapi.json` e mostra status, tempo, tamanho, cabeçalhos, corpo e o `curl` equivalente. No PC usa a API local quando ela está ligada; senão, a API publicada.
- **Visualizador de código** (`web/assets/code-viewer.js`): os botões "Ver código" e as abas "Testar | Código" mostram os arquivos reais do projeto, empacotados em `web/data/sources.json`. O repositório pode continuar privado.
- **Arquitetura e sinais** (`web/assets/architecture.js`): decisões e trade-offs de cada peça, contagem de testes tirada do repositório e tempos medidos no navegador de quem visita.
- **Evidências** (`web/data/evidence.json`): liga competências a arquivos em repositórios públicos ou ao visualizador, e projetos aos selos de CI do GitHub.

Depois de alterar qualquer arquivo listado em `scripts/sources.mjs`, atualize o pacote de código:

```powershell
npm run sources
```

`npm run check` falha quando `sources.json` está diferente do código-fonte. Textos novos da página precisam de entrada em `web/data/translations.json` para os outros três idiomas.

## Rodar no PC

Requisitos: Node.js 22+ e Python 3.12+. Go 1.26 para o serviço de currículo; JDK 21 e Gradle 8.14.3 para compilar Kotlin/JS.

```powershell
npm run dev
```

Abra http://localhost:4173. O portfólio não precisa de instalação npm.

Em outro terminal, na raiz do projeto:

```powershell
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r apps/trends-api/requirements.txt
.venv/Scripts/python.exe -m uvicorn main:app --app-dir apps/trends-api --host 127.0.0.1 --port 8000
```

API: http://127.0.0.1:8000/api/news?q=Python&geo=BR&limit=10. Documentação: http://127.0.0.1:8000/docs. A busca exige um assunto e retorna apenas notícias.

```powershell
cd apps/resume-api
go run .
```

A demonstração histórica em `/demos/curriculo/` usa JavaScript e dados locais. A implementação Kotlin/JS anterior foi preservada em `apps/resume-kotlin`; ela não é o app compartilhado atual. O currículo atual usa `ResumeApp()` tanto no Android quanto na web. O endereço antigo `/demos/kotlin/` redireciona para `/app/?version=kotlin`.

```powershell
gradle -p apps/resume-kotlin jsBrowserDistribution --no-daemon
Copy-Item apps/resume-kotlin/build/dist/js/productionExecutable/* web/demos/kotlin/ -Recurse -Force
```

A versão Android está em `apps/resume-android`; consulte seu README para build e assinatura de demonstração. Ela usa as mesmas telas e estado do módulo compartilhado que a versão WebAssembly, acessível sem instalação.

## Verificar

```powershell
npm run check
cd apps/trends-api
../../.venv/Scripts/python.exe -m unittest -v
```

O workflow do GitHub verifica o frontend, testa FastAPI e Go e compila Kotlin, disponibilizando seu bundle como artefato.

O painel de tendências consulta o feed real. Países permitidos: BR, US, PT. Cache em memória por 5 minutos; limite de 1 a 20 itens; erros da fonte retornam HTTP 502. Não é a API de séries históricas do Google Trends. A verificação TLS usa certificados confiáveis do sistema operacional, inclusive no Windows.

## Publicar na VPS Hostinger

Antes de publicar, inspecione os serviços existentes e seus roteadores. **Não execute este Compose em uma VPS que já ocupe as portas 80/443**: nesses casos, use o proxy já instalado, conforme `docs/deployment.md`. Não altere serviços dos outros sites.

Em uma VPS sem proxy existente, com Docker e Compose instalados:

1. Clone este repositório em `/opt/karenangelis-portfolio`.
2. Crie `.env` a partir de `.env.example`.
3. Aponte o registro DNS A de `karenangelis.com` para o IPv4 da VPS. Verifique registros AAAA antes de publicar; um IPv6 incorreto pode impedir acesso e emissão de certificado. Preserve e-mail e demais registros existentes.
4. Libere TCP 80/443 e execute `docker compose up -d --build`.
5. Confira a página, `/api/profile`, `/api/trends?geo=BR&limit=2` e `/docs` via HTTPS.

O Caddy serve o frontend, encaminha as APIs e emite HTTPS automaticamente após o domínio resolver para esta VPS. Os serviços Go e FastAPI não expõem portas diretamente. A imagem web compila Kotlin durante o build. Credenciais e chaves SSH não entram no repositório.

## Conteúdo

Links selecionados pela Karen: https://luniay.com.br/ e https://clycka.com/.
Resumo inicial adaptado do perfil público https://github.com/KarenAngelis/KarenAngelis.
Os blocos visuais de Luniay/Clycka são composições gráficas do portfólio, não capturas das telas dos produtos.

## Aplicativo compartilhado Android + Web

O app tem cinco abas (Início, Habilidades, Experiência, Projetos, Contato) em `ResumeApp.kt`. Na web ele é instalável: `web/app/` traz manifesto, ícones, tela de abertura (`shell.js`, `shell.css`) e um service worker (`sw.js`) que permite abrir o currículo sem rede depois da primeira visita. Os mesmos arquivos ficam em `apps/resume-compose/shared/src/wasmJsMain/resources/`; mantenha as duas cópias iguais.

Para recompilar a versão web (JDK 17, Gradle 8.14.3 e Android SDK 35) e publicar em `web/app/`:

```sh
gradle -p apps/resume-compose :shared:wasmJsBrowserDistribution
rm web/app/*.wasm
cp apps/resume-compose/shared/build/dist/wasmJs/productionExecutable/{*.wasm,resume-app.js,resume-app.js.map,resume-app.js.LICENSE.txt} web/app/
npm run sources
```

A aba em segundo plano pausa o desenho do Compose; teste com a aba visível.

`apps/resume-compose/shared` contém `ResumeApp()` e a camada de dados compartilhada. A Activity Android e o ponto de entrada WebAssembly chamam essa mesma função. O workflow `resume-multiplatform.yml` compila os dois alvos juntos.

```powershell
gradle -p apps/resume-android :shared:wasmJsBrowserDistribution :app:assemblePortfolio --no-daemon
```

O pacote web compilado fica em `apps/resume-compose/shared/build/dist/wasmJs/productionExecutable`. Publique os arquivos em `web/app/`. O currículo incluído no build permite usar a interface quando a API está indisponível; o botão Atualizar consulta a API Go.

## Painel de visitas

`apps/stats-api/` (FastAPI + SQLite) conta visitas e cliques sem cookies. O servidor guarda só totais por dia (`dia, tipo, chave, total`); IP e navegador não são gravados. `web/assets/track.js` envia os eventos e respeita Do Not Track. O painel público fica em `/painel/`, e os mesmos totais estão em `/api/stats/summary`. Os dados ficam no volume `stats_data`.

No PC:

```powershell
$env:STATS_DB = "apps/stats-api/stats.sqlite3"
.venv/Scripts/python.exe -m uvicorn main:app --app-dir apps/stats-api --host 127.0.0.1 --port 8001
```

Depois abra http://localhost:4173/painel/. Testes: `cd apps/stats-api; ../../.venv/Scripts/python.exe -m unittest -v`.
