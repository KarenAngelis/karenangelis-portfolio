@file:OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)
package com.karenangelis.curriculo.shared
import androidx.compose.ui.window.ComposeViewport
import io.ktor.client.HttpClient
import io.ktor.client.engine.js.Js
import io.ktor.client.plugins.HttpTimeout
import kotlinx.browser.document
internal actual fun platformClient() = HttpClient(Js) { install(HttpTimeout) { requestTimeoutMillis=12000 } }
fun main() { ComposeViewport(document.getElementById("app-root")!!) { ResumeApp() } }
