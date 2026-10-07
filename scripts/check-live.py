"""Run from an authorized network to verify deployment, TLS and API integration."""
import json
from urllib.request import urlopen

base = "https://karenangelis.com"
for path, marker in [("/", "Ideias ganham"), ("/demos/kotlin/", "kotlin-app"), ("/demos/kotlin/resume-kotlin.js", "api/profile"), ("/demos/trends/", "Google Trends")]:
    with urlopen(base + path, timeout=20) as response:
        text = response.read().decode()
        assert response.status == 200 and marker in text, path
    print("OK", path)
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
print("OK skills + dynamic UI + WhatsApp")
with urlopen(base + "/api/trends?geo=BR&limit=2", timeout=20) as response:
    trends = json.load(response)
    assert trends["geo"] == "BR" and len(trends["items"]) <= 2
print("OK /api/trends", len(trends["items"]), "items")
with urlopen("https://www.karenangelis.com", timeout=20) as response:
    assert "Ideias ganham" in response.read().decode()
print("OK www + TLS")
