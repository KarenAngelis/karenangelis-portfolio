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
