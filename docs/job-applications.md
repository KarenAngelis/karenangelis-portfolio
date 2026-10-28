# Candidaturas por e-mail — implementação inicial, não ativada

Conta exclusiva: karen.denich@gmail.com. Independente da campanha comercial,
com banco, volume, variáveis e serviço próprios. Não altera a coleta RFB.

## Implementado

- Consulta SerpApi Google Jobs para BR/PT/IT a cada 12h (3 consultas/ciclo,
  primeira página apenas). Fonte requer chave e plano; nenhuma compra realizada.
- Preserva descrição, empresa, links, candidatos a e-mail e data de descoberta.
- Deduplica anúncios por ID da fonte. Resultados entram em `review`.
- HTML com currículo online, GitHub e três projetos. Idiomas pt-BR/pt-PT/it/en;
  nome da empresa escapado e saudação alternativa quando não informado.
- Worker para registros preparados, SMTP Gmail TLS, teto móvel de 24h,
  intervalo mínimo de 180s, bloqueio de concorrência e supressão.
- Teto solicitado 500, reserva padrão 50: no máximo 450 tentativas/24h.
  Não mede outros envios da conta. Limites do Google continuam prevalecendo.
- Só uma tentativa por endereço; erros ambíguos pausam toda a fila e não
  são reenviados. `accepted` significa aceito pelo SMTP, não entregue.

## Pendências antes de ativar

### Google Sheets — conexão preparada, migração ainda pendente

Planilha: https://docs.google.com/spreadsheets/d/1XaS_gJ_gp7V3NHFInpx4qrQNecz3ApmBWr4maHugt8o/edit

`sheets.py` implementa autenticação por refresh token do servidor, leitura com
validação de colunas/IDs e escrita RAW no histórico. `python sheets.py` testa
somente a conexão/leitura; não envia e-mails. Os testes usam transporte simulado.
Ainda é necessário autorizar OAuth, integrar descoberta/fila/status à planilha
e validar na VPS. O worker existente continua com SQLite; não afirmar migração
concluída. Alterar um status na planilha ainda não dispara envio.

O HTML pt-BR usa agora o arquivo original aprovado, preservando layout, cartões,
cores e os dois botões de mesma largura. Os outros idiomas ainda usam o template
traduzido anterior; antes da ativação, aplicar as traduções ao layout aprovado.

Hostinger pediu login em 28/10/2026; nenhum deploy desta integração foi realizado.

### Demais requisitos

1. SERPAPI_API_KEY para conta/plano escolhido pelo usuário.
2. Autenticação de servidor do Gmail solicitado (senha de app, quando disponível).
   A conexão Gmail do ChatGPT não exporta tokens para a VPS.
3. Currículo PDF aprovado e anexação para anúncios que o exigem (não implementada).
4. Triagem de compatibilidade: vaga ainda ativa, nível pleno/intermédio/middle,
   fullstack/frontend/SQL/DBA; freelance ou emprego, idioma e elegibilidade para
   trabalho a partir do Brasil. Não confundir inglês da mensagem com fluência.
5. Confirmar que cada e-mail é canal de candidatura, não suporte ou privacidade;
   seguir assunto e documentação pedidos pelo anúncio. A extração não prova isso.
6. Teste para a própria conta e conciliação de respostas/devoluções antes de escala.

A triagem automática de compatibilidade e o processamento de devoluções ainda
não estão implementados. Não é uma automação de candidatura ponta a ponta.
O idioma é selecionado na preparação; priorizar idioma solicitado no anúncio,
depois idioma do anúncio e só então país. Não enviar com variáveis pendentes.

## Operação após configurar segredos e concluir validação

Copiar .env.example para .env.jobs na raiz; restringir permissões a 600.
Nunca versionar .env.jobs. Iniciar com JOBS_SEND_ENABLED=false.

    docker compose -p karen-jobs -f compose.jobs.yaml up -d --build
    docker compose -p karen-jobs -f compose.jobs.yaml exec job-applications python jobs.py status

Preparar somente após triagem, e somente se não houver exigência de anexos ou
instruções ainda não atendidas (suporte a isso pendente):

    python jobs.py prepare --id ID --email EMAIL_DO_ANUNCIO --language pt-BR

Não limpar pausa/status `unknown` sem conciliar a caixa de enviados. Caso o
processo morra em `sending`, ele bloqueia a fila para investigação, sem repetir.

## Testes

    cd apps/job-applications
    python -m unittest -v
