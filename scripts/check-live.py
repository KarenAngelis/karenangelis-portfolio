"""Run from an authorized network to verify deployment, TLS and API integration."""
import json
import io
import zipfile
from urllib.request import urlopen

base = "https://karenangelis.com"
for path, marker in [("/", "Ideias ganham"), ("/demos/trends/", "Google Trends")]:
    with urlopen(base + path, timeout=20) as response:
        text = response.read().decode()
        assert response.status == 200 and marker in text, path
    print("OK", path)
with urlopen(base + "/demos/kotlin/", timeout=30) as response:
    assert response.geturl().endswith("/downloads/karenangelis-curriculo.apk")
    assert "application/vnd.android.package-archive" in response.headers.get("Content-Type", "")
    apk = response.read()
    assert apk.startswith(b"PK") and len(apk) > 100_000
with zipfile.ZipFile(io.BytesIO(apk)) as archive:
    assert "classes.dex" in archive.namelist() and "AndroidManifest.xml" in archive.namelist()
    assert json.loads(archive.read("assets/profile.json"))["name"] == "Karen Angelis"
print("OK native Android APK + legacy link redirects to download")
with urlopen(base + "/api/profile", timeout=20) as response:
    profile = json.load(response)
    assert profile["name"] == "Karen Angelis" and profile["projects"]
print("OK /api/profile", profile["name"])
assert len(profile["skillGroups"]) == 12
assert "Python" in profile["skills"] and "JavaScript" in profile["skills"] and "Dart" in profile["skills"]
assert profile["education"][0]["title"] == "Análise e Desenvolvimento de Sistemas"
assert profile["whatsapp"] == "https://wa.me/5547997336808"
with urlopen(base, timeout=20) as response:
    home = response.read().decode()
    assert "Linguagens e bases" in home and "JavaScript" in home and "scenario-chooser" in home and "https://wa.me/5547997336808" in home
    for technology in ["Python", "JavaScript", "TypeScript", "Dart", "Kotlin", "Go", "SQL", "HTML", "CSS", "React", "Next.js", "FastAPI", "Flutter", "Spring Boot", "Express", "Node.js", "PostgreSQL", "Docker", "Kubernetes / Rancher", "VPS", "CI/CD"]:
        assert technology in home, technology
print("OK skills + infrastructure + dynamic UI + WhatsApp")
with urlopen(base + "/api/trends?geo=BR&limit=2", timeout=20) as response:
    trends = json.load(response)
    assert trends["geo"] == "BR" and len(trends["items"]) <= 2
print("OK /api/trends", len(trends["items"]), "items")
with urlopen(base + "/api/trends?geo=BR&q=Python&limit=2", timeout=20) as response:
    news = json.load(response)
    assert news["mode"] == "news" and news["query"] == "Python"
    assert news["source"].startswith("https://news.google.com/rss/search")
    assert news["items"] and len(news["items"]) <= 2
print("OK topic search + external news", len(news["items"]), "items")
with urlopen(base + "/data/career.json", timeout=20) as response:
    career = json.load(response)
assert len(career) == 8
for entry in career:
    with urlopen(base + "/trajetoria/" + entry["slug"] + "/", timeout=20) as response:
        page = response.read().decode()
        assert "HARD SKILLS" in page and "SOFT SKILLS" in page
    if entry["logo"]:
        with urlopen(base + "/assets/companies/" + entry["logo"], timeout=20) as response:
            assert len(response.read()) > 100
print("OK 8 career pages + official logos")
with urlopen("https://www.karenangelis.com", timeout=20) as response:
    assert "Ideias ganham" in response.read().decode()
print("OK www + TLS")
