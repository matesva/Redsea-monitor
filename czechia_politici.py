import json, os, datetime
from collections import Counter, defaultdict
from email.utils import parsedate_to_datetime

OUT = "czechia/politicians.json"

TITLES = {
    "ing", "mgr", "bc", "judr", "mudr", "phdr", "rndr", "phd", "csc", "mba",
    "prof", "doc", "gen", "plk", "msc", "dis", "dr", "pan", "paní", "premiér",
    "premiérka", "ministr", "ministryně", "primátor", "primátorka", "poslanec",
    "poslankyně", "senátor", "senátorka", "prezident", "prezidentka",
    "předseda", "předsedkyně", "hejtman", "hejtmanka", "europoslanec",
    "europoslankyně", "starosta", "starostka", "náměstek", "náměstkyně",
}

def norm_name(n):
    toks = [t.strip(",.;:()") for t in str(n).replace("\u00a0", " ").split()]
    toks = [t for t in toks if t and t.lower().replace(".", "") not in TITLES]
    return " ".join(toks)

def clean_politici(raw, party_list):
    out, seen = [], set()
    for p in raw or []:
        if isinstance(p, str):
            p = {"jmeno": p}
        if not isinstance(p, dict):
            continue
        n = norm_name(p.get("jmeno", ""))
        if len(n) < 3 or n.lower() in seen:
            continue
        seen.add(n.lower())
        s = p.get("strana")
        out.append({"jmeno": n, "strana": s if s in party_list else ""})
    return out[:4]

def article_dt(a):
    try:
        d = parsedate_to_datetime(a.get("published", ""))
        if d.tzinfo:
            d = d.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return d
    except Exception:
        try:
            return datetime.datetime.fromisoformat(a.get("added", ""))
        except Exception:
            return None

def build_politici(data, top=5):
    now = datetime.datetime.utcnow()
    res = {}
    for days in (7, 30):
        lim = now - datetime.timedelta(days=days)
        arts = []
        for a in data:
            d = article_dt(a) if a.get("politici") else None
            if d and d >= lim:
                arts.append(a)

        full = defaultdict(set)  # příjmení -> plná jména
        for a in arts:
            for p in a["politici"]:
                if " " in p["jmeno"]:
                    full[p["jmeno"].split()[-1].lower()].add(p["jmeno"])

        def canon(n):
            if " " not in n:
                c = full.get(n.lower(), set())
                return next(iter(c)) if len(c) == 1 else n
            return n

        cnt = Counter()
        party = defaultdict(Counter)
        tony = defaultdict(Counter)
        heads = defaultdict(list)
        for a in arts:
            names = {}
            for p in a["politici"]:
                n = canon(p["jmeno"])
                if " " in n:
                    names[n] = p["strana"]
            ton = a.get("ton") if a.get("ton") in ("pozitivní", "neutrální", "kritický") else "neutrální"
            for n, s in names.items():
                cnt[n] += 1
                if s:
                    party[n][s] += 1
                tony[n][ton] += 1
                if len(heads[n]) < 3:
                    heads[n].append({"title": a["title"], "link": a["link"], "zdroj": a["source"]})

        res[str(days)] = [{
            "jmeno": n,
            "pocet": c,
            "strana": party[n].most_common(1)[0][0] if party[n] else "",
            "tony": dict(tony[n]),
            "clanky": heads[n],
        } for n, c in cnt.most_common(top)]

    os.makedirs("czechia", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": now.isoformat(timespec="minutes"), "politici": res},
                  f, ensure_ascii=False, indent=1)
    print("Žebříček politiků:", {k: [r["jmeno"] for r in v] for k, v in res.items()})
