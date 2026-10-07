import kotlinx.browser.document
import kotlinx.browser.window
import org.w3c.dom.HTMLElement

fun main() {
    val root = document.getElementById("kotlin-app") ?: return
    val status = document.getElementById("kotlin-status") ?: return
    val origin = if (window.location.hostname == "localhost" || window.location.hostname == "127.0.0.1") "http://127.0.0.1:8080" else ""
    window.fetch("$origin/api/profile").then { response ->
        if (!response.ok) error("HTTP ${response.status}")
        response.json()
    }.then { raw ->
        val profile: dynamic = raw
        root.textContent = ""
        val title = document.createElement("h2")
        title.textContent = profile.name as String
        val summary = document.createElement("p")
        summary.textContent = profile.summary as String
        root.appendChild(title)
        root.appendChild(summary)
        val skills = document.createElement("div") as HTMLElement
        skills.className = "skills"
        val list = profile.skills as Array<String>
        for (skill in list) {
            val badge = document.createElement("span")
            badge.textContent = skill
            skills.appendChild(badge)
        }
        root.appendChild(skills)
        val projects = profile.projects as Array<dynamic>
        for (index in projects.indices) {
            val item = projects[index]
            val row = document.createElement("article") as HTMLElement
            row.className = "project-row"
            val heading = document.createElement("h3")
            heading.textContent = item.name as String
            val link = document.createElement("a")
            link.setAttribute("href", item.url as String)
            link.setAttribute("target", "_blank")
            link.setAttribute("rel", "noopener noreferrer")
            link.textContent = "Abrir projeto ↗"
            row.appendChild(heading)
            row.appendChild(link)
            root.appendChild(row)
        }
        status.textContent = "Interface Kotlin/JS · currículo recebido da API Go."
    }.catch { error ->
        status.textContent = "API Go indisponível. Confira se o serviço está em execução."
        console.error(error)
    }
}
