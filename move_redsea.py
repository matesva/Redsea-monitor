import os

SITE = "https://matesva.github.io/Redsea-monitor/"
ROOT = "index.html"
HUB = "monitory/index.html"
RS_DIR = "redsea"
RS = RS_DIR + "/index.html"

if os.path.exists(RS):
    print("Už provedeno: redsea/index.html existuje")
    raise SystemExit(0)
if not (os.path.exists(ROOT) and os.path.exists(HUB)):
    raise SystemExit("Chybí index.html nebo monitory/index.html")

root = open(ROOT, encoding="utf-8").read()
if "Red Sea & Investment AI Monitor" not in root:
    raise SystemExit("Kořenový index.html nevypadá jako stránka Rudého moře, končím")

# 1) stránka Rudého moře do složky redsea/ s upravenými cestami
reps = [
    ("fetch('data.json')", "fetch('../data.json')"),
    ('href="rss.xml"', 'href="../rss.xml"'),
    ('href="manifest.json"', 'href="../manifest.json"'),
    ('rel="canonical" href="' + SITE + '"', 'rel="canonical" href="' + SITE + 'redsea/"'),
    ("const pageUrl = '" + SITE + "';", "const pageUrl = '" + SITE + "redsea/';"),
]
for d in ["usa", "europe", "middle-east", "asia", "japan", "czechia"]:
    reps.append(('href="%s/"' % d, 'href="../%s/"' % d))
for a, b in reps:
    if a not in root:
        print("POZOR, nenalezeno:", a)
    root = root.replace(a, b)
os.makedirs(RS_DIR, exist_ok=True)
open(RS, "w", encoding="utf-8").write(root)
print("vytvořeno:", RS)

# 2) přehled monitorů se stane kořenovou stránkou
hub = open(HUB, encoding="utf-8").read()
hub_root = hub.replace(SITE + "monitory/", SITE)
open(ROOT, "w", encoding="utf-8").write(hub_root)
print("kořenová stránka = přehled monitorů")

# 3) stará adresa /monitory/ jen přesměruje na kořen
redirect = (
    '<!DOCTYPE html><html lang="cs"><head><meta charset="UTF-8">'
    '<meta http-equiv="refresh" content="0; url=/Redsea-monitor/">'
    '<link rel="canonical" href="' + SITE + '">'
    '<title>Přehled monitorů</title></head>'
    '<body><a href="/Redsea-monitor/">Přehled monitorů</a></body></html>\n'
)
open(HUB, "w", encoding="utf-8").write(redirect)
print("monitory/index.html = přesměrování")

# 4) štítek odkazu zpět na stránce Česko
cz = "czechia/index.html"
if os.path.exists(cz):
    s = open(cz, encoding="utf-8").read()
    s = s.replace("← REDSEA MONITOR", "← PŘEHLED MONITORŮ")
    open(cz, "w", encoding="utf-8").write(s)
    print("upraveno:", cz)
