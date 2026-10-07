plugins { kotlin("multiplatform") version "2.4.20" }
repositories { mavenCentral() }
kotlin {
    js {
        browser { commonWebpackConfig { outputFileName = "resume-kotlin.js" } }
        binaries.executable()
    }
}
