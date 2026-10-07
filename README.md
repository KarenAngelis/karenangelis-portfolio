# Karen Angelis · portfólio interativo

Portfólio para `karenangelis.com`, com habilidades demonstradas por experiências clicáveis, links para Luniay e Clycka e projetos públicos do GitHub.

Publicado na VPS Hostinger em 7 de outubro de 2026: https://karenangelis.com.

- Aplicativo Android em Kotlin + API Go: https://karenangelis.com/downloads/karenangelis-curriculo.apk
- Alternativa de currículo web: https://karenangelis.com/demos/curriculo/
- Google Trends + FastAPI: https://karenangelis.com/demos/trends/
- Documentação interativa da API: https://karenangelis.com/docs

O currículo aparece uma única vez na página inicial, com um print real do aplicativo Android. No computador, o card abre a versão interativa Kotlin/JS em `/demos/kotlin/`, conectada à API Go. No Android, tenta abrir o aplicativo nativo e oferece o APK como alternativa. A versão web permite buscar habilidades e navegar pelas seções; ela não executa o APK em um emulador. Interações web foram testadas no navegador local. A rede corporativa WEG bloqueou o domínio público por reputação ainda não verificada; a inspeção visual do endereço público nesse PC ficou limitada por esse filtro.

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

API: http://127.0.0.1:8000/api/trends?geo=BR&limit=10. Documentação: http://127.0.0.1:8000/docs.

```powershell
cd apps/resume-api
go run .
```

A demonstração em `/demos/curriculo/` usa JavaScript e dados locais, com botão para consultar Go. A interface Kotlin real fica em `/demos/kotlin/` e depende do bundle compilado e da API Go, sem dados fictícios de fallback:

```powershell
gradle -p apps/resume-kotlin jsBrowserDistribution --no-daemon
Copy-Item apps/resume-kotlin/build/dist/js/productionExecutable/* web/demos/kotlin/ -Recurse -Force
```

A versão Android solicitada pela Karen está em `apps/resume-android`; consulte seu README para build, assinatura de demonstração e distribuição. A versão web é uma alternativa e não substitui o app nativo.

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
