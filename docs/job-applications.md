# Candidaturas com Google Sheets e Gmail

Conta: karen.denich@gmail.com. Projeto Google: subtle-hangar-513017-p2.
Planilha: https://docs.google.com/spreadsheets/d/1XaS_gJ_gp7V3NHFInpx4qrQNecz3ApmBWr4maHugt8o/edit

## Operação

`compose.jobs.yaml` executa `sheet_worker.py`. As vagas e o registro durável de
cada tentativa ficam na planilha. Não usa o SQLite da implementação anterior.
`jobs.py` preserva os comandos antigos apenas para compatibilidade/testes e
fornece o renderizador; não iniciar seu comando `run` em paralelo.

Um único coordenador na VPS mantém lock no volume jobs_data. O histórico impede
reenvios por ID e por endereço, inclusive se alguém redefinir o status. Uma
reserva sem confirmação do Gmail bloqueia toda a fila para conciliação manual.
Não apagar nem editar IDs, Histórico ou os campos de envio. Usar visualizações
com filtro; não reordenar fisicamente linhas durante processamento. Uma planilha
não oferece transações entre vários escritores; só o coordenador envia.

A cada 12h são feitas até três consultas SerpApi (BR/PT/IT), primeira página.
O início de cada consulta é persistido antes da chamada; reinícios não gastam
novamente a cota. Plano observado: 250 buscas/mês; agenda usa até186/mês.
A consulta de vagas não faz candidatura em sites nem triagem automática por IA.

Para liberar e-mail, um agente deve conferir vigência, nível/stack, elegibilidade
para trabalhar do Brasil, idioma e instruções/anexos. Depois, preencher descrição
original contendo o e-mail, fonte, link, idioma e observação `TRIAGEM APROVADA`,
e mudar Status para `Pronto para e-mail`, Canal `E-mail`. Vagas que exigem anexos
ou assunto específico não devem ser liberadas: suporte ainda pendente.

O coordenador verifica a fila a cada60s. Máximo configurado:500 menos50 de reserva
para uso pessoal=450 tentativas/24h; mínimo180s entre tentativas. Isso não garante
cota do Google nem mede outros envios da conta. Vagas por link permanecem na
planilha para os agentes. `Candidatura concluída` indica aceite pela API Gmail,
não leitura/entrega ao destinatário. ID e link da mensagem são guardados.
Respostas/devoluções não são sincronizadas automaticamente (escopo gmail.send).

## Credenciais e implantação

Pasta dedicada VPS: /opt/karen-jobs. Segredos em secrets/client.json,
secrets/token.json e secrets/serpapi.txt, fora do Git e do contexto Docker.
OAuth pede identificação de e-mail, Google Sheets e Gmail send. O escopo Sheets
é amplo; o cliente do backend fixa a planilha acima. A autorização do usuário foi
concedida em28/10/2026. Leitura de8 registros e testeHTML para a própria conta
confirmados; Gmail ID1a183aa26387d64f, registrado no Histórico.

`compose.jobs-oauth.yaml` executa callback na porta local4183. Caddy encaminha
somente /api/jobs/oauth/*, com backup antes da alteração. Não há logs de códigos.
PKCE, state de uso único e validação do e-mail protegem a conexão. Para reconectar:

    docker compose -p karen-jobs-oauth -f compose.jobs-oauth.yaml exec -T jobs-oauth python oauth_service.py authorize

O projeto Google ainda está em modo Testando. A autorização offline pode expirar
em7dias; concluir o branding/publicação OAuth antes de prometer operação contínua.

## HTML e testes

Todos os idiomas usam a estrutura do HTML aprovado: currículo e GitHub com mesma
largura, cards Luniay/Clycka/StockMaster, cores, espaçamento e botões. Idiomas
pt-BR, pt-PT, italiano e inglês. Sem anexação automática de currículo.

    cd apps/job-applications
    python -m unittest -q

26 testes: OAuth/PKCE, schema, duplicação, reserva antes do envio, falhas ambíguas,
link-only, limite, destinatário presente na fonte e corpo HTML. Testes de rede
simulados, exceto a leitura e o envio real de teste mencionados acima.
