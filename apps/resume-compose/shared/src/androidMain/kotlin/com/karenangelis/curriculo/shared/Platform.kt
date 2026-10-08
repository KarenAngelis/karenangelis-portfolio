package com.karenangelis.curriculo.shared
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
internal actual fun platformLocale(): String = "pt-BR"
internal actual suspend fun loadProfileBody(): String = withContext(Dispatchers.IO) {
    val connection=URL("https://karenangelis.com/api/profile").openConnection() as HttpURLConnection
    try {
        connection.connectTimeout=8000;connection.readTimeout=8000
        check(connection.responseCode==200)
        connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
    } finally { connection.disconnect() }
}
