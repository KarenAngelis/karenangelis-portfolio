import kotlinx.browser.document
import kotlinx.browser.window
import org.w3c.dom.HTMLElement
import org.w3c.dom.HTMLInputElement

fun node(tag: String, text: String = "", css: String = ""): HTMLElement {
    val element = document.createElement(tag) as HTMLElement
    element.textContent = text
    element.className = css
    return element
}

fun projectLink(label: String, url: String): HTMLElement {
    val link = node("a", "$label", "text-link")
    link.setAttribute("href", url)
    link.setAttribute("target", "_blank")
    link.setAttribute("rel", "noopener noreferrer")
    return link
}

fun entry(parent: HTMLElement, title: String, subtitle: String, description: String) {
    val row = node("article", css = "resume-entry")
    row.appendChild(node("h3", title))
    row.appendChild(node("p", subtitle, "resume-role"))
    row.appendChild(node("p", description))
    parent.appendChild(row)
}

fun skillCatalog(parent: HTMLElement, groups: Array<dynamic>, query: String = "") {
    parent.textContent = ""
    val term = query.trim().lowercase()
    var visible = 0
    for (group in groups) {
        val items = group.items as Array<String>
        val title = group.title as String
        val example = group.example as String
        val description = group.description as String
        val searchable = "$title $description $example ${items.joinToString(" ")}".lowercase()
        if (term.isNotEmpty() && !searchable.contains(term)) continue
        visible++
        val card = node("details", css = "skill-card")
        if (term.isNotEmpty()) card.setAttribute("open", "")
        val summary = node("summary")
        summary.appendChild(node("span", title))
        summary.appendChild(node("small", "${items.size} competências"))
        val body = node("div", css = "skill-body")
        body.appendChild(node("p", description))
        val badges = node("div", css = "skills")
        for (item in items) badges.appendChild(node("span", item))
        body.appendChild(badges)
        body.appendChild(node("p", example, "skill-example"))
        body.appendChild(projectLink(group.demoLabel as String, group.demoUrl as String))
        card.appendChild(summary)
        card.appendChild(body)
        parent.appendChild(card)
    }
    if (visible == 0) parent.appendChild(node("p", "Nenhuma área encontrada. Tente outro termo.", "status"))
}

fun main() {
    val root = document.getElementById("kotlin-app") as? HTMLElement ?: return
    val status = document.getElementById("kotlin-status") ?: return
    val origin = if (window.location.hostname == "localhost" || window.location.hostname == "127.0.0.1") "http://127.0.0.1:8080" else ""
    window.fetch("$origin/api/profile").then { response ->
        if (!response.ok) error("HTTP ${response.status}")
        response.json()
    }.then { raw ->
        val profile: dynamic = raw
        root.textContent = ""
        root.appendChild(node("h2", profile.fullName as String))
        root.appendChild(node("p", profile.role as String, "resume-role"))
        root.appendChild(node("p", profile.summary as String, "intro"))
        val tabs = node("div", css = "profile-tabs")
        tabs.setAttribute("role", "group")
        tabs.setAttribute("aria-label", "Seções do currículo")
        root.appendChild(tabs)
        val sections = mutableMapOf<String, HTMLElement>()
        val buttons = mutableMapOf<String, HTMLElement>()
        val names = listOf("skills" to "Habilidades", "experience" to "Experiência", "education" to "Formação", "languages" to "Idiomas", "soft" to "Como trabalho", "projects" to "Projetos")
        for ((id, label) in names) {
            val button = node("button", label, if (id == "skills") "active" else "")
            button.setAttribute("aria-pressed", if (id == "skills") "true" else "false")
            tabs.appendChild(button)
            val section = node("section")
            section.setAttribute("aria-label", label)
            if (id != "skills") section.setAttribute("hidden", "")
            root.appendChild(section)
            sections[id] = section
            buttons[id] = button
            button.addEventListener("click", {
                for ((key, panel) in sections) {
                    if (key == id) panel.removeAttribute("hidden") else panel.setAttribute("hidden", "")
                    buttons[key]?.className = if (key == id) "active" else ""
                    buttons[key]?.setAttribute("aria-pressed", if (key == id) "true" else "false")
                }
            })
        }
        val skills = sections.getValue("skills")
        val search = node("input", css = "kotlin-search") as HTMLInputElement
        search.type = "search"
        search.placeholder = "Buscar: Flutter, QA, OAuth, compliance…"
        search.setAttribute("aria-label", "Buscar habilidade")
        skills.appendChild(search)
        val catalog = node("div", css = "skill-catalog")
        skills.appendChild(catalog)
        val groups = profile.skillGroups as Array<dynamic>
        skillCatalog(catalog, groups)
        search.addEventListener("input", { skillCatalog(catalog, groups, search.value) })

        for (item in profile.experience as Array<dynamic>) {
            entry(sections.getValue("experience"), item.company as String, "${item.role} · ${item.period}", item.description as String)
        }
        val education = sections.getValue("education")
        education.appendChild(node("h2", "Formação acadêmica"))
        for (item in profile.education as Array<dynamic>) {
            entry(education, item.title as String, "${item.institution} · ${item.status}", item.detail as String)
        }
        education.appendChild(node("h2", "Cursos e certificados"))
        for (item in profile.courses as Array<dynamic>) {
            entry(education, item.title as String, item.institution as String, item.detail as String)
        }
        val more = node("details", css = "skill-card")
        more.appendChild(node("summary", "Outras formações e estudos registrados"))
        more.appendChild(node("p", "Registros de formação e estudo; conclusão e carga horária variam por curso."))
        val studies = node("ul")
        for (text in profile.additionalStudies as Array<String>) studies.appendChild(node("li", text))
        more.appendChild(studies)
        education.appendChild(more)

        for (item in profile.languages as Array<dynamic>) {
            entry(sections.getValue("languages"), item.name as String, item.level as String, "")
        }
        val soft = sections.getValue("soft")
        soft.className = "soft-grid"
        for (item in profile.softSkills as Array<dynamic>) {
            val card = node("article", css = "soft-card")
            card.appendChild(node("h3", item.title as String))
            card.appendChild(node("p", item.example as String))
            soft.appendChild(card)
        }
        for (item in profile.projects as Array<dynamic>) {
            val row = node("article", css = "resume-entry")
            row.appendChild(node("h3", item.name as String))
            row.appendChild(node("p", item.description as String))
            row.appendChild(projectLink(item.linkLabel as String, item.url as String))
            sections.getValue("projects").appendChild(row)
        }
        status.textContent = "Interface Kotlin/JS · currículo recebido da API Go."
    }.catch { error ->
        status.textContent = "Não foi possível carregar o currículo. Tente novamente mais tarde."
        console.error(error)
    }
}
