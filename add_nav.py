
import os

TAG = '<script src="/Redsea-monitor/nav.js"></script>'
PAGES = [
    "index.html", "usa/index.html", "europe/index.html",
    "middle-east/index.html", "asia/index.html",
    "japan/index.html", "czechia/index.html", "monitory/index.html",
]

for p in PAGES:
    if not os.path.exists(p):
        print("chybí:", p)
        continue
    s = open(p, encoding="utf-8").read()
    if "nav.js" in s:
        print("už má:", p)
        continue
    if "</body>" not in s:
        print("bez </body>:", p)
        continue
    s = s.replace("</body>", "    " + TAG + "\n</body>", 1)
    open(p, "w", encoding="utf-8").write(s)
    print("upraveno:", p)
