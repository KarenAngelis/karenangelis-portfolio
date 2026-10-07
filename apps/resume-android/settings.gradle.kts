pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement { repositories { google(); mavenCentral() } }
rootProject.name = "KarenAngelisAndroid"
include(":app")
include(":shared")
project(":shared").projectDir = file("../resume-compose/shared")
