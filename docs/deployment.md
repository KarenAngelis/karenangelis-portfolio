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
