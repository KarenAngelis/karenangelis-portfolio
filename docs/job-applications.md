# Candidaturas com coleta direta, Google Sheets e Gmail

Conta: karen.denich@gmail.com. Projeto Google: subtle-hangar-513017-p2.
Planilha: https://docs.google.com/spreadsheets/d/1XaS_gJ_gp7V3NHFInpx4qrQNecz3ApmBWr4maHugt8o/edit

## Operação

`compose.jobs.yaml` executa `sheet_worker.py`. Vagas e histórico ficam na planilha.
O volume local guarda apenas o lock do coordenador. `jobs.py` fornece o renderizador;
seus comandos SQLite/SMTP são legados e não devem ser iniciados em paralelo.
O coletor legado foi desativado para impedir consumo acidental da SerpApi.

`direct_sources.py` consulta os feeds públicos dos empregadores em Lever,
Greenhouse e Ashby e extrai seções de páginas de carreiras. A lista explícita em
`sources.json` contém empresas, páginas de origem, tipos de integração e intervalos.
Não usa SerpApi, chave de busca nem o catálogo do Google Empregos. Não há cota de
250 pesquisas, mas há limites dos sites, capacidade da planilha e cobertura
restrita às fontes cadastradas. Não descobre automaticamente todas as empresas
existentes. A lista pode ser ampliada após validar o feed de cada empresa.

Configuração inicial: Brafton, CI&T, Truv, Salsify, Amplemarket, Sensor Tower,
Apto e DevInterface. Consulta a cada 6 horas por fonte. São preservados conteúdo,
link, modalidade e localização original. Filtra fullstack, frontend, web e banco
de dados; exclui títulos somente sênior/liderança/júnior e locais explicitamente
presenciais ou híbridos. Nível/modalidade não informados e anúncios Mid/Senior
ficam para revisão. País é classificação de mercado, nunca autorização de
trabalho nem garantia de contratação a partir do Brasil.

Paginação Lever: até 15 páginas de 200 itens, com erro explícito se exceder.
Leituras por fonte são limitadas a 12 MB e têm timeout; não há repetição automática
de 429, login ou CAPTCHA. Uma fonte com erro não impede as demais. O histórico
registra DIRECT_ATTEMPT, DIRECT_COMPLETE (contagens) e DIRECT_ERROR. O intervalo
é preservado entre reinícios; tentativas falhas voltam no próximo intervalo.
Não se deve apagar o histórico. Novos registros usam valores RAW e entram sempre
em Triagem. Deduplicação por ID estável e empresa/título, incluindo registros
manuais anteriores. A tabela nativa é expandida quando novas linhas entram.
Capacidade atual: 999 vagas e 9.999 linhas de histórico; o serviço falha de modo
explícito ao atingir a capacidade, sem sobrescrever candidaturas.

## Envio

Um único coordenador na VPS mantém lock no volume jobs_data. O histórico impede
reenvios por ID e endereço, inclusive se alguém redefinir o status. Uma reserva
sem confirmação do Gmail bloqueia a fila para conciliação manual. Não apagar nem
editar IDs, Histórico ou campos de envio. Usar visualizações com filtro; não
reordenar fisicamente linhas durante processamento. Uma planilha não oferece
transações entre vários escritores; só o coordenador envia.

Para liberar e-mail, conferir vigência, nível/stack, elegibilidade para trabalhar
do Brasil, idioma e instruções/anexos. Preencher descrição contendo o e-mail,
fonte, link, idioma e observação `TRIAGEM APROVADA`; mudar Status para
`Pronto para e-mail` e Canal para `E-mail`. O HTML e o assunto padrão incluem
nome da empresa e título da vaga. Anexos e assuntos fora do padrão ainda não são
suportados. A extração de um e-mail no anúncio não libera envio por si só.

Fila verificada a cada 60 segundos, exceto durante a coleta. Configuração:
500 menos 50 de reserva = 450 tentativas/24h; mínimo de 180 segundos entre envios.
Isso não garante cota do Google nem contabiliza outros envios da conta.
Vagas por link ficam para candidatura por agentes. Candidatura concluída significa
aceite pela API Gmail, não leitura/entrega. Guarda ID e link da mensagem.
Respostas/devoluções ainda não são sincronizadas (escopo gmail.send).

## Credenciais e implantação

Pasta VPS: `/opt/karen-jobs`. Segredos Google em `secrets/client.json` e
`secrets/token.json`, fora do Git e do contexto Docker. A chave antiga
`secrets/serpapi.txt`, caso exista, não é lida pelo coletor atual.

OAuth pede identificação, Sheets e Gmail send. Sheets é um escopo amplo, mas o
cliente fixa a planilha acima. Projeto publicado Em produção em 28/10/2026,
autorização renovada depois da publicação. O app pessoal não tem selo de
verificação Google. Envio HTML para a própria conta e candidaturas reais para
Locus/Apto foram confirmados no Gmail e registrados na planilha em 28/10/2026.

`compose.jobs-oauth.yaml` serve callback na porta local 4183. Caddy encaminha
somente `/api/jobs/oauth/*`. Sem logs de códigos; PKCE, state de uso único e
validação do e-mail protegem a conexão. Privacidade em `/api/jobs/oauth/privacy`.
Para reconectar:

    docker compose -p karen-jobs-oauth -f compose.jobs-oauth.yaml exec -T jobs-oauth python oauth_service.py authorize

## Validação

    cd apps/job-applications
    python -m unittest -q
    python direct_sources.py

O segundo comando é uma consulta real de leitura, sem credenciais Google, sem
alterar planilha e sem enviar e-mail. Produção escreve as vagas no ciclo normal
sob o lock do coordenador; não executar uma segunda instância do worker.

Os testes cobrem OAuth, HTML, reserva antes de envio, resultados incertos,
duplicações, cotas, filtros, paginação, isolamento de erros, ausência de tokens
Google nas fontes e preservação/expansão da tabela. Nenhuma nova dependência de
produção foi acrescentada. Os quatro idiomas mantêm o HTML aprovado com os dois
botões de mesma largura e os projetos Luniay, Clycka e StockMaster.
