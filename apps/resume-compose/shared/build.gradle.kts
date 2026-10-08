import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.compose")
    id("com.android.library")
}
kotlin {
    androidTarget { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }
    @OptIn(ExperimentalWasmDsl::class)
    wasmJs {
        browser { commonWebpackConfig { outputFileName = "resume-app.js" } }
        binaries.executable()
    }
    sourceSets {
        commonMain {
            kotlin.srcDir(layout.buildDirectory.dir("generated/profile"))
            dependencies {
                implementation(compose.runtime)
                implementation(compose.foundation)
                implementation(compose.material3)
                implementation(compose.ui)
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")
                implementation("io.ktor:ktor-client-core:3.2.3")
            }
        }
        androidMain.dependencies { implementation("io.ktor:ktor-client-android:3.2.3") }
        wasmJsMain.dependencies {
            implementation("io.ktor:ktor-client-js:3.2.3")
            implementation("org.jetbrains.kotlinx:kotlinx-browser:0.3")
        }
    }
}
android {
    namespace = "com.karenangelis.curriculo.shared"
    compileSdk = 35
    defaultConfig { minSdk = 26 }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
val prepareProfile by tasks.registering {
    val input=rootProject.file("../../web/data/profile.json")
    val output=layout.buildDirectory.file("generated/profile/com/karenangelis/curriculo/shared/BundledProfile.kt")
    inputs.file(input);outputs.file(output)
    doLast {
        val escaped=input.readText().replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("$", "\\$")
        output.get().asFile.apply { parentFile.mkdirs(); writeText("package com.karenangelis.curriculo.shared\ninternal object BundledProfile { val json = \"$escaped\" }\n") }
    }
}
val prepareTranslations by tasks.registering {
    val input=rootProject.file("../../web/data/translations.json")
    val output=layout.buildDirectory.file("generated/profile/com/karenangelis/curriculo/shared/BundledTranslations.kt")
    inputs.file(input);outputs.file(output)
    doLast {
        val chunks=input.readText().chunked(8000).joinToString("\n") {
            val escaped=it.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("$", "\\$")
            "append(\"$escaped\")"
        }
        output.get().asFile.apply { parentFile.mkdirs();writeText("package com.karenangelis.curriculo.shared\ninternal object BundledTranslations { val json = buildString {\n$chunks\n} }\n") }
    }
}
tasks.configureEach { if(name.startsWith("compileKotlin") || name.startsWith("compileDebugKotlin") || name.startsWith("compileReleaseKotlin")) dependsOn(prepareProfile,prepareTranslations) }
