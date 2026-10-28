# Fonte própria de CNPJ

A API existente passa a usar `COLLECT_PROVIDER=rfb` por padrão. O worker não chama Casa dos Dados nesse modo, mesmo se houver chave antiga. SMTP, histórico e descadastro permanecem no banco próprio.

`rfb_import.py` importa os ZIPs oficiais de **Estabelecimentos**, com leitura sequencial e lotes de 1.000 registros. Não extrai arquivos no disco, preserva CNPJ textual e filtra situação ativa e data de abertura. O município é o código RFB, não nome nem código IBGE. Sem nome fantasia, identifica a empresa pelo CNPJ; não inventa razão social. E-mails importados são candidatos: revisão de contato é necessária antes do enfileiramento automático. Formato válido não comprova entregabilidade.

Exemplo dentro do ambiente do serviço, com o volume de dados e arquivos montados:

```sh
python rfb_import.py /imports/Estabelecimentos*.zip --since 2026-09-01 --until 2026-10-28 --competence 2026-10
```

Reexecução de uma carga concluída com mesmo SHA-256 e intervalo é ignorada. Cargas interrompidas podem ser reexecutadas: os lotes persistidos são atualizados por CNPJ, sem criar mensagens ou sobrescrever contatos já verificados. A conclusão só é registrada após leitura completa. Importações diferentes devem ser executadas sequencialmente.

Os arquivos oficiais são disponibilizados por competência: isso não garante acesso às empresas abertas hoje. O download da competência deve ser validado no catálogo oficial antes da importação. O serviço prospect-rfb-sync descobre a competência mais recente via WebDAV oficial a cada 24 horas quando RFB_SYNC_ENABLED=true. Baixa e importa um ZIP de cada vez, remove-o após sucesso e registra ETag/tamanho para evitar repetição. Falhas são repetidas após uma hora. Downloads interrompidos recomeçam; lotes já gravados são deduplicados. O padrão filtra abertura desde 60 dias antes do início da competência; RFB_SINCE permite outra data. A carga inicial precisa terminar para afirmar cobertura completa. A importação não afirma cobertura nacional até todos os ZIPs da competência serem processados.

Catálogo oficial: https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj

Nenhum arquivo de empresas, banco ou credencial deve ser publicado no GitHub.

## Enfileiramento automático

AUTO_VALIDATE_CONTACTS=true habilita checagem de formato e MX de contatos da RFB, em lotes de 10. AUTO_QUEUE_VERIFIED=true enfileira os elegíveis; SEND_ENABLED=true libera o worker respeitando limite e pausa. contact_checks registra a evidência: mx_ok significa apenas domínio com rota de e-mail, não caixa comprovada nem consentimento. Falhas temporárias de DNS são reavaliadas após uma hora; ausência de MX após sete dias. Remoções e contatos anteriores são excluídos antes da checagem e novamente no envio. Não há sondagem SMTP de destinatários.
