# Currículo Android nativo

Aplicativo Kotlin com Activity e Views Android. Não usa WebView, HTML ou JavaScript para renderizar o currículo.

- Habilidades por área, busca, experiências, formação, cursos, idiomas, projetos e contato.
- Perfil incluído no APK e cache privado para uso offline.
- Atualização por HTTPS em `https://karenangelis.com/api/profile`, servida pela API Go.
- App link de abertura: `karenangelis://curriculo`.
- Android 8/API 26 ou superior; versão 1.0.0.

## Compilar

JDK 17, Gradle 8.14.3 e Android SDK 35:

```sh
gradle -p apps/resume-android assemblePortfolio
```

Saída: `app/build/outputs/apk/portfolio/app-portfolio.apk`. O perfil vem de `web/data/profile.json`, sem duplicação manual dos dados profissionais.

O flavor `portfolio` usa assinatura de demonstração e não é debuggable. A chave de demonstração é mantida no cache privado do workflow Android; não é commitada. Para uma distribuição comercial/Google Play com atualizações duradouras, configurar uma chave de release permanente fora do repositório.

O workflow verifica a assinatura, instala o APK em emulador Android 15, abre telas nativas, verifica a ausência de WebView nas telas e testa a abertura por URI. O artefato inclui screenshot, metadados e SHA-256.

## Distribuição

`web/downloads/karenangelis-curriculo.apk` é a versão demonstrativa do portfólio. No desktop o site oferece o APK. No Android compatível, o botão usa um Intent para abrir o app instalado; quando não está instalado, o fallback é o download do APK. O usuário realiza a instalação pelo próprio sistema Android.

O antigo `/demos/kotlin/` redireciona para o APK. A alternativa web fica em `/demos/curriculo/`. iPhone não instala APK Android.
