# Fonte própria de CNPJ

A API existente passa a usar `COLLECT_PROVIDER=rfb` por padrão. O worker não chama Casa dos Dados nesse modo, mesmo se houver chave antiga. SMTP, histórico e descadastro permanecem no banco próprio.

`rfb_import.py` importa os ZIPs oficiais de **Estabelecimentos**, com leitura sequencial e lotes de 1.000 registros. Não extrai arquivos no disco, preserva CNPJ textual e filtra situação ativa e data de abertura. O município é o código RFB, não nome nem código IBGE. Sem nome fantasia, identifica a empresa pelo CNPJ; não inventa razão social. E-mails importados são candidatos: revisão de contato é necessária antes do enfileiramento automático. Formato válido não comprova entregabilidade.

Exemplo dentro do ambiente do serviço, com o volume de dados e arquivos montados:

```sh
python rfb_import.py /imports/Estabelecimentos*.zip --since 2026-09-01 --until 2026-10-28 --competence 2026-10
```

Reexecução de uma carga concluída com mesmo SHA-256 e intervalo é ignorada. Cargas interrompidas podem ser reexecutadas: os lotes persistidos são atualizados por CNPJ, sem criar mensagens ou sobrescrever contatos já verificados. A conclusão só é registrada após leitura completa. Importações diferentes devem ser executadas sequencialmente.

Os arquivos oficiais são disponibilizados por competência: isso não garante acesso às empresas abertas hoje. O download da competência deve ser validado no catálogo oficial antes da importação. Não há downloader nem atualização agendada nesta versão; a carga inicial ainda precisa ser realizada. A importação não afirma cobertura nacional até todos os ZIPs da competência serem processados.

Catálogo oficial: https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj

Nenhum arquivo de empresas, banco ou credencial deve ser publicado no GitHub.
