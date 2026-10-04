import os, sys, json, datetime, urllib.request, urllib.parse, urllib.error

SITE = "redsea-monitor"
API = "https://%s.goatcounter.com/api/v0" % SITE
OUT = "navstevnost/stats.json"
DAYS = 30
BASE = "/Redsea-monitor"
NAMES = [
    (BASE + "/redsea", "Rudé moře"),
    (BASE + "/usa", "USA"),
    (BASE + "/europe", "Evropa"),
    (BASE + "/middle-east", "Blízký východ"),
    (BASE + "/asia", "Čína a Asie"),
    (BASE + "/japan", "Japonsko"),
    (BASE + "/czechia", "Česko"),
    (BASE + "/monitory", "Přehled (monitory)"),
    (BASE + "/uspesnost", "Úspěšnost"),
    (BASE + "/hledani", "Hledání"),
    (BASE + "/navstevnost", "Návštěvnost"),
]


def get(path, params, token):
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        sys.exit("GoatCounter %s: HTTP %s %s" % (path, e.code, body))


def monitor_of(path):
    p = path.split("?")[0]
    if p.endswith("/index.html"):
        p = p[:-len("/index.html")]
    p = p.rstrip("/")
    if p in ("", BASE):
        return "Úvodní stránka (kořen)"
    for key, name in NAMES:
        if p == key or p.startswith(key + "/"):
            return name
    return "Ostatní"


def main():
    token = os.environ.get("GOATCOUNTER_TOKEN")
    if not token:
        sys.exit("Chybí GOATCOUNTER_TOKEN (GitHub secret)")

    today = datetime.date.today()
    start = today - datetime.timedelta(days=DAYS - 1)
    rng = {"start": start.isoformat(), "end": today.isoformat()}

    tot = get("/stats/total", rng, token)
    byday = {}
    for s in tot.get("stats", []):
        n = s.get("daily")
        if n is None:
            n = sum(s.get("hourly") or [])
        byday[str(s.get("day"))[:10]] = int(n or 0)

    days = []
    d = start
    while d <= today:
        days.append({"day": d.isoformat(), "n": byday.get(d.isoformat(), 0)})
        d += datetime.timedelta(days=1)

    hits = get("/stats/hits", dict(rng, limit=100, daily="true"), token)
    pages = []
    for h in hits.get("hits", []):
        if h.get("event"):
            continue
        path = h.get("path", "")
        pages.append({
            "path": path,
            "count": int(h.get("count", 0) or 0),
            "monitor": monitor_of(path),
        })
    pages.sort(key=lambda p: -p["count"])

    mon = {}
    for p in pages:
        mon[p["monitor"]] = mon.get(p["monitor"], 0) + p["count"]
    monitors = [{"name": k, "count": v}
                for k, v in sorted(mon.items(), key=lambda kv: -kv[1])]

    out = {
        "updated": datetime.datetime.utcnow().isoformat(timespec="minutes"),
        "start": rng["start"],
        "end": rng["end"],
        "days": days,
        "monitors": monitors,
        "pages": pages[:30],
    }
    os.makedirs("navstevnost", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("Dny:", len(days), "| stránky:", len(pages), "| monitory:", len(monitors))


if __name__ == "__main__":
    main()
