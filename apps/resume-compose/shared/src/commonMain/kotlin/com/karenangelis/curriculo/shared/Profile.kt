package com.karenangelis.curriculo.shared

import kotlinx.serialization.json.*

internal expect suspend fun loadProfileBody(): String
internal fun JsonObject.text(key: String): String = (get(key) as? JsonPrimitive)?.contentOrNull.orEmpty()
internal fun JsonObject.rows(key: String): List<JsonObject> = (get(key) as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
internal fun JsonObject.strings(key: String): List<String> = (get(key) as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()
internal fun parseProfile(body: String): JsonObject {
    require(body.length < 1_000_000)
    val result=Json.parseToJsonElement(body).jsonObject
    require(result.text("name")=="Karen Angelis" && result.rows("skillGroups").isNotEmpty())
    return result
}
internal suspend fun fetchProfile(): JsonObject {
    return parseProfile(loadProfileBody())
}
