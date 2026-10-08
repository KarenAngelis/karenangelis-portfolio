"""Install the real APK and validate native screens and its custom app link."""
import pathlib
import subprocess
import time
import xml.etree.ElementTree as ET
import re

out = pathlib.Path("android-artifacts")
package = "com.karenangelis.curriculo"

def adb(*args):
    return subprocess.check_output(["adb", *args]).decode(errors="replace")

def snapshot():
    adb("shell", "uiautomator", "dump", "/sdcard/karen-screen.xml")
    return ET.fromstring(adb("shell", "cat", "/sdcard/karen-screen.xml"))

def find(text):
    for _ in range(10):
        root = snapshot()
        texts = [node.get("text", "") for node in root.iter("node")]
        if "Quickstep isn't responding" in texts:
            close = next(node for node in root.iter("node") if node.get("text") == "Close app")
            x1,y1,x2,y2 = map(int,re.findall(r"\d+",close.get("bounds")))
            adb("shell","input","tap",str((x1+x2)//2),str((y1+y2)//2))
            adb("shell","am","start","-W","-n",package+"/.MainActivity")
            continue
        for node in root.iter("node"):
            if node.get("text") == text or node.get("content-desc") == text:
                return node
        time.sleep(1)
    (out/"failure-ui.xml").write_text(ET.tostring(root,encoding="unicode"))
    (out/"failure-logcat.txt").write_text(adb("logcat","-d","-t","500"))
    adb("shell","screencap","-p","/sdcard/karen-failure.png")
    adb("pull","/sdcard/karen-failure.png",str(out/"android-failure.png"))
    raise AssertionError("Native screen text missing: " + text)

def tap(text):
    node = find(text)
    x1,y1,x2,y2 = map(int,re.findall(r"\d+",node.get("bounds")))
    adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))

adb("install", "-r", str(out/"karenangelis-curriculo.apk"))
adb("logcat", "-c")
adb("shell","input","keyevent","KEYCODE_WAKEUP")
adb("shell","wm","dismiss-keyguard")
adb("shell", "am", "start", "-W", "-n", package+"/.MainActivity")
find("Karen Denich de Angelis")
for _ in range(20):
    if "Resume profile refreshed from Go API" in adb("logcat", "-d", "-t", "500"):
        break
    time.sleep(1)
else:
    raise AssertionError("Native app did not refresh its profile from the Go API")
root = snapshot()
assert not any(node.get("text", "").startswith("Currículo atualizado") or node.get("text") == "Vamos conversar" for node in root.iter("node"))
for label in ("Habilidades", "Experiência", "Formação", "Idiomas", "Projetos", "Contato"):
    find(label)
adb("shell", "screencap", "-p", "/sdcard/karen-native.png")
adb("pull", "/sdcard/karen-native.png", str(out/"android-native.png"))
tap("Experiência")
find("WEG · IEL / Inova Talentos")
tap("Formação")
find("Análise e Desenvolvimento de Sistemas")
root = snapshot()
assert all("WebView" not in node.get("class", "") for node in root.iter("node"))
adb("shell", "am", "force-stop", package)
adb("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", "karenangelis://curriculo", "-p", package)
find("Karen Denich de Angelis")
print("APK installed; native skills, experience, education and app link passed.")
