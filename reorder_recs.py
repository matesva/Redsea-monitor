import os

# Stránky, na kterých se pořadí upraví (zbytečné klidně smaž)
PAGES = [
    "redsea/index.html", "usa/index.html", "europe/index.html",
    "middle-east/index.html", "asia/index.html", "japan/index.html",
]
BUL = '<div class="bulletin">'


def bounds(s, sec_id):
    i = s.find('id="%s"' % sec_id)
    if i < 0:
        return None
    start = s.rfind(BUL, 0, i)
    nxt = s.find(BUL, i)
    if start < 0 or nxt < 0:
        return None
    return start, nxt


for p in PAGES:
    if not os.path.exists(p):
        print("chybí:", p)
        continue
    s = open(p, encoding="utf-8").read()
    r = bounds(s, "sec-recs")
    c = bounds(s, "sec-chart")
    if not r or not c:
        print("bez sekcí:", p)
        continue
    if r[0] > c[0]:
        print("už je za grafem:", p)
        continue
    recs = s[r[0]:r[1]]
    s = s[:r[0]] + s[r[1]:]
    c = bounds(s, "sec-chart")
    s = s[:c[1]] + recs + s[c[1]:]
    open(p, "w", encoding="utf-8").write(s)
    print("upraveno:", p)
