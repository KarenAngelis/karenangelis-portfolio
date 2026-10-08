@file:OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
package com.karenangelis.curriculo.shared
import androidx.compose.ui.window.ComposeViewport
import io.ktor.client.HttpClient
import io.ktor.client.engine.js.Js
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.get
import io.ktor.client.statement.bodyAsText
import kotlinx.browser.document
import kotlinx.browser.window
internal actual fun platformLocale(): String {
    val requested=window.location.search.removePrefix("?").split("&").firstOrNull { it.startsWith("lang=") }?.substringAfter("=")
    return requested?.takeIf { it in listOf("pt-BR","pt-PT","en-US","it-IT") } ?: "pt-BR"
}
internal actual suspend fun loadProfileBody(): String {
    val local=window.location.hostname=="localhost" || window.location.hostname=="127.0.0.1"
    val endpoint=if(local) "http://127.0.0.1:8080/api/profile" else window.location.origin+"/api/profile"
    val client=HttpClient(Js) { install(HttpTimeout) { requestTimeoutMillis=12000 } }
    try {
        val response=client.get(endpoint)
        check(response.status.value==200)
        return response.bodyAsText()
    } finally { client.close() }
}
fun main() { ComposeViewport(document.getElementById("app-root")!!) { ResumeApp() } }
