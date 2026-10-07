package com.karenangelis.curriculo.shared
import io.ktor.client.HttpClient
import io.ktor.client.engine.android.Android
import io.ktor.client.plugins.HttpTimeout
internal actual fun platformClient() = HttpClient(Android) { install(HttpTimeout) { requestTimeoutMillis=12000 } }
