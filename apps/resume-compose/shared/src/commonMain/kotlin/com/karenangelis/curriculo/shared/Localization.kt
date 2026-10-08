package com.karenangelis.curriculo.shared

import kotlinx.serialization.json.*

internal expect fun platformLocale(): String
private val locale by lazy { platformLocale() }
private val translations by lazy { Json.parseToJsonElement(BundledTranslations.json).jsonObject }
internal fun tr(text: String): String {
    if(locale == "pt-BR") return text
    return (translations[text] as? JsonObject)?.text(locale)?.takeIf { it.isNotEmpty() } ?: text
}
internal fun localizeProfile(profile: JsonObject): JsonObject {
    fun translate(value: JsonElement): JsonElement = when(value) {
        is JsonObject -> JsonObject(value.mapValues { translate(it.value) })
        is JsonArray -> JsonArray(value.map { translate(it) })
        is JsonPrimitive -> if(value.isString) JsonPrimitive(tr(value.content)) else value
    }
    return translate(profile).jsonObject
}
