"""Explainable, conservative matching; a score is adherence, not hiring odds."""
import re
import unicodedata


def _norm(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", str(value)).casefold()
                            if not unicodedata.combining(c)).split())


_SKILLS = {
    "Python": ["python"], "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"], "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"], "FastAPI": ["fastapi", "fast api"],
    "Django": ["django"], "PostgreSQL": ["postgresql", "postgres"],
    "SQL": ["sql"], "MySQL": ["mysql"], "SQLite": ["sqlite", "sqlite3"],
    "Node.js": ["node.js", "nodejs"], "NestJS": ["nestjs", "nest.js"],
    "Java": ["java"], "Kotlin": ["kotlin"], "Go": ["golang", "go"],
    "Docker": ["docker"], "AWS": ["aws", "amazon web services"],
    "Git": ["git"], "HTML": ["html", "html5"], "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind", "tailwind css"], "Flutter": ["flutter"],
    "Dart": ["dart"], "C#": ["c#", "csharp"], "C++": ["c++", "cpp"],
    "Redis": ["redis"], "MongoDB": ["mongodb", "mongo"],
}
_ALIASES = {_norm(alias): name for name, aliases in _SKILLS.items() for alias in [name, *aliases]}
_COUNTRIES = {
    "BR": ["brasil", "brazil"], "IT": ["italia", "italy"], "PT": ["portugal"],
    "US": ["united states", "estados unidos", "usa", "eua"],
    "GB": ["united kingdom", "reino unido", "uk"], "CA": ["canada"],
    "DE": ["germany", "alemanha", "deutschland"], "FR": ["france", "franca"],
    "ES": ["spain", "espanha", "espana"], "IE": ["ireland", "irlanda"],
}


def _has(text, term):
    return re.search(r"(?<!\w)" + re.escape(_norm(term)) + r"(?!\w)", _norm(text)) is not None


def _skill(value):
    return _ALIASES.get(_norm(value), str(value).strip())


def _countries(value):
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_countries(item) for item in value)) if value else set()
    text = _norm(value or "")
    if text.upper() in _COUNTRIES:
        return {text.upper()}
    return {code for code, names in _COUNTRIES.items() if any(_has(text, name) for name in names)}


def _strings(value):
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def evaluate(profile, job):
    preferences = profile.get("preferences") or {}
    facts = profile.get("facts") or {}
    title, description, location = (str(job.get(key) or "") for key in ("title", "description", "location"))
    text = " ".join((title, description, location))
    profile_skills = {_skill(value).casefold(): _skill(value) for value in _strings(profile.get("skills"))}
    explicit = _strings(job.get("required_skills")) or _strings(job.get("skills"))
    required = {_skill(value).casefold(): _skill(value) for value in explicit}
    if not required:
        required = {name.casefold(): name for name, aliases in _SKILLS.items() if any(_has(text, alias) for alias in aliases)}
        # User-specific skill names are useful even when absent from our small vocabulary.
        required.update({key: value for key, value in profile_skills.items() if _has(text, value)})
    matched = sorted((required[key] for key in required.keys() & profile_skills.keys()), key=str.casefold)
    missing = sorted((required[key] for key in required.keys() - profile_skills.keys()), key=str.casefold)
    score = round(100 * len(matched) / len(required)) if required else 0
    blockers = []
    if not required:
        blockers.append("Requisitos técnicos insuficientes para avaliar.")
    elif _strings(job.get("required_skills")) and missing:
        blockers.append("Requisito técnico obrigatório não confirmado: " + ", ".join(missing) + ".")

    roles = _strings(preferences.get("roles"))
    role_words = {word for role in roles for word in re.findall(r"[\w+#.]+", _norm(role))
                  if word not in {"junior", "pleno", "senior", "jr", "sr", "de", "em", "of", "and", "e"}}
    if roles and not any(_has(title, word) for word in role_words):
        blockers.append("Cargo fora das funções configuradas.")

    mode = _norm(job.get("workplace_type") or job.get("workplaceType") or job.get("work_mode") or "")
    hybrid = mode in {"hybrid", "hibrido"} or _has(location, "hybrid") or _has(location, "hibrido")
    onsite = mode in {"on-site", "onsite", "on site", "presencial"} or _has(location, "presencial") or _has(location, "on-site")
    remote = not (hybrid or onsite) and (job.get("remote") is True or mode in {"remote", "remoto"}
             or any(_has(text, word) for word in ("remote", "remoto", "remota", "full remote")))
    if preferences.get("remote_only"):
        if hybrid or onsite:
            blockers.append("A vaga exige trabalho presencial ou híbrido.")
        elif not remote:
            blockers.append("Modalidade remota não confirmada.")

    vacancy_countries = _countries(job.get("country") or job.get("countries") or location)
    selected_countries = _countries(preferences.get("countries"))
    world = (job.get("international_remote") is True or
             any(_has(text, term) for term in ("remote worldwide", "worldwide remote", "work from anywhere",
                 "anywhere in the world", "remoto global", "de qualquer lugar do mundo")) or
             _norm(location) in {"worldwide", "global", "anywhere"})
    if selected_countries and vacancy_countries and selected_countries.isdisjoint(vacancy_countries):
        blockers.append("País da vaga fora dos países configurados.")
    elif selected_countries and not vacancy_countries and not world:
        blockers.append("País da vaga não confirmado.")

    residence = _countries(facts.get("residence_country") or facts.get("country") or facts.get("location"))
    allowed = _countries(job.get("eligible_countries") or job.get("allowed_countries") or job.get("accepts_remote_from"))
    restriction = any(_has(text, term) for term in ("residents only", "residentes", "residir", "residencia obrigatoria",
                      "must be based", "must reside", "based in", "somente", "apenas", "only"))
    if allowed:
        if not residence:
            blockers.append("País de residência não informado para verificar elegibilidade.")
        elif residence.isdisjoint(allowed):
            blockers.append("Residência incompatível com os países aceitos pela vaga.")
    elif not world:
        if not residence:
            blockers.append("País de residência não informado para verificar elegibilidade.")
        elif vacancy_countries and residence.isdisjoint(vacancy_countries):
            blockers.append("Restrição geográfica incompatível com sua residência." if restriction or not remote
                            else "Elegibilidade para trabalhar remotamente do seu país não confirmada.")
        elif not vacancy_countries:
            blockers.append("Elegibilidade geográfica não confirmada.")

    # These are factual checks only: projects and skill names never become years or fluency.
    years = job.get("required_years")
    if isinstance(years, (int, float)) and years > 0:
        experience = facts.get("experience_years")
        if not isinstance(experience, (int, float)):
            blockers.append("Tempo de experiência exigido ainda não confirmado no perfil.")
        elif experience < years:
            blockers.append("Tempo de experiência inferior ao requisito obrigatório.")
    languages = _strings(job.get("required_languages"))
    known_languages = facts.get("languages") or {}
    known = list(known_languages) if isinstance(known_languages, dict) else _strings(known_languages)
    language_aliases = {"ingles": "english", "italiano": "italian", "portugues": "portuguese", "espanhol": "spanish"}
    language_key = lambda value: language_aliases.get(_norm(value), _norm(value))
    for language in languages:
        if language_key(language) not in {language_key(item) for item in known}:
            blockers.append("Idioma obrigatório não confirmado: " + language + ".")
    minimum = preferences.get("min_score", 70)
    if not isinstance(minimum, (int, float)) or not 0 <= minimum <= 100:
        minimum = 70
    if score < minimum:
        blockers.append("Aderência técnica abaixo do mínimo configurado.")
    return {"score": score, "matched_skills": matched, "missing_skills": missing,
            "blockers": list(dict.fromkeys(blockers)), "eligible": not blockers}
