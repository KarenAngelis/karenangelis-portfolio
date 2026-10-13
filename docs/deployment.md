# Publicação com serviços já existentes

Primeiro inventariar: sistema operacional, espaço em disco, containers, processos, listeners nas portas 80/443, volumes e proxy atual. Não instalar outro roteador nem reiniciar serviços de Luniay/Clycka sem necessidade.

Se houver Traefik, Caddy ou Nginx já ativo:

- Construir as imagens do projeto sem publicar as portas 80/443 do `compose.yaml` padrão.
- Ligar os containers à rede do proxy existente com nomes exclusivos.
- Criar uma regra de host para `karenangelis.com`, com raiz estática e encaminhamentos `/api/profile` para Go e `/api/trends`, `/docs`, `/openapi.json` para FastAPI.
- Para a imagem Caddy interna, configurar o domínio como `http://karenangelis.com` e usar a porta 80 interna. O proxy externo ficará responsável pelo HTTPS. Não publicar a porta interna na internet.
- Aplicar a configuração específica somente após ler o estado da VPS e registrar as alterações previstas.
- Preservar DNS de outros domínios, MX, TXT, SPF, DKIM e DMARC.
- Validar TLS e o fluxo completo do navegador antes de considerar a publicação concluída.

O Compose padrão atende a VPS sem roteador existente. A configuração final será adaptada após obter acesso à VPS, evitando conflito de portas e interferência com projetos já hospedados.

## VPS identificada em 7 de outubro de 2026

Ubuntu 24.04, com Caddy existente no container `karsuel-proxy-1` usando rede host e arquivo `/opt/karsuel/infra/vps/Caddyfile.clycka` montado como somente leitura. Clycka usa portas locais 3100/8100.

Para este ambiente, usar `docker compose -p karenangelis-portfolio -f compose.vps.yaml up -d --build`. Essa configuração publica apenas `127.0.0.1:4180`, serve o bundle Kotlin já validado pelo GitHub e mantém as APIs na rede interna. Adicionar o bloco de `infra/Caddyfile.host-snippet` ao Caddy existente, com cópia de segurança e validação antes de recarregar.

O DNS de `karenangelis.com` precisa resolver para a VPS; a publicação só termina após validar domínio, TLS e demonstrações reais.

Publicação concluída em 7 de outubro de 2026: registro A do domínio atualizado para a VPS com TTL 300; CNAME www preservado. Caddy emitiu certificados Let's Encrypt para ambos os nomes. `scripts/check-live.py` passou na VPS, validando frontend, Kotlin compilado, currículo Go e tendências reais FastAPI via HTTPS. O Clycka retornou HTTP 200 antes e após a alteração de roteamento.

Backup da configuração anterior: `/opt/karsuel/infra/vps/Caddyfile.clycka.before-karen-20261007T145810Z`. A regra do portfólio deve ser preservada ao atualizar a configuração do Clycka no futuro.

## Painel público de visitas nesta VPS

O proxy externo já encaminha todo o domínio para `127.0.0.1:4180`. O Caddy interno deste repositório encaminha `/api/stats/*` ao serviço, portanto o proxy externo não precisa de outra rota. Depois de enviar o código à VPS:

1. Suba o serviço com `docker compose -p karenangelis-portfolio -f compose.vps.yaml up -d --build --no-deps stats-api`. Na inicialização, a tabela antiga `panel_auth` é removida; o backup do SQLite feito antes da migração preserva uma cópia.
2. Suba o site com `docker compose -p karenangelis-portfolio -f compose.vps.yaml up -d --build --no-deps web`. O volume `stats_data` preserva os totais entre reinícios.
3. Remova o antigo `STATS_TOKEN` do `.env` da VPS e do computador. Ele não é mais usado.
4. Confirme que `https://karenangelis.com/api/stats/health` responde `{"status":"ok"}` e que `https://karenangelis.com/api/stats/summary` responde com os totais sem autenticação.
5. Abra `https://karenangelis.com/painel/` e confira os números e o seletor de período. Os totais começam em zero em uma instalação nova.

O serviço não grava IP ou navegador no SQLite e inicia o Uvicorn sem log de acesso. O controle de abuso usa identificadores temporários só na memória.

Se a cópia na VPS tiver mudanças manuais que ainda não estão no Git, use `scripts/deploy-stats-vps.py` para acrescentar apenas a rota e o carregamento do script. Execute primeiro sem `--apply` para listar os arquivos; `--apply` cria um backup separado antes de escrever. Depois transfira somente `apps/stats-api/`, `web/painel/` e `web/assets/track.js`, valide `docker compose -f compose.vps.yaml config --quiet` e valide o Caddyfile antes de reconstruir os contêineres.
