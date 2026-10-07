plugins { id("com.android.application"); id("org.jetbrains.kotlin.android"); id("org.jetbrains.kotlin.plugin.compose") }
android {
    namespace = "com.karenangelis.curriculo"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.karenangelis.curriculo"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "2.0.0"
    }
    buildTypes {
        create("portfolio") {
            initWith(getByName("release"))
            matchingFallbacks += listOf("release")
            signingConfig = signingConfigs.getByName("debug")
            isDebuggable = false
            isMinifyEnabled = false
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
    sourceSets.getByName("main").assets.srcDir(layout.buildDirectory.dir("generated/profileAssets"))
}
val prepareProfile by tasks.registering(Copy::class) {
    from(rootProject.file("../../web/data/profile.json"))
    into(layout.buildDirectory.dir("generated/profileAssets"))
}
tasks.named("preBuild").configure { dependsOn(prepareProfile) }
dependencies {
    implementation(project(":shared"))
    implementation("androidx.activity:activity-compose:1.10.1")
}
