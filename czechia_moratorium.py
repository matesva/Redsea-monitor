import os, re, json, gzip, base64, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Prague")


def _dt(y, m, d, h=0, mi=0):
    return datetime.datetime(y, m, d, h, mi, tzinfo=TZ)


# Okna moratoria: začátek s rezervou 12 hodin dopředu (kdyby se běh workflow zpozdil),
# konec = ukončení hlasování. Uprav podle skutečných termínů voleb.
WINDOWS = [
    (_dt(2026, 10, 5, 12, 0), _dt(2026, 10, 10, 14, 0)),    # 1. kolo, volby 9.-10. 10.
    (_dt(2026, 10, 12, 12, 0), _dt(2026, 10, 17, 14, 0)),   # případné 2. kolo Senátu 16.-17. 10.
]

HOLD = "czechia/hold.dat"
STATIC = ("polls_manual.json", "pruzkumy_info.json")

POLL_RE = re.compile(
    r"průzkum|sondáž|volební model|volební odhad|volební preferenc|"
    r"stranick\S*\s+preferenc|preferenc\S*\s+stran|exit[\s-]?poll|"
    r"odhad výsledk|volební potenciál",
    re.I,
)
NEUTRAL_INTRO = "Přehled hlavních událostí (bez zmínek o předvolebních průzkumech, volební moratorium)."


def active(now=None):
    force = os.environ.get("MORATORIUM_FORCE", "").strip().lower()
    if force in ("1", "on", "true"):
        return True
    if force in ("0", "off", "false"):
        return False
    now = now or datetime.datetime.now(TZ)
    return any(a <= now < b for a, b in WINDOWS)


def is_poll_text(s):
    return bool(POLL_RE.search(str(s or "")))


def is_poll_article(a):
    if a.get("pruzkum"):
        return True
    txt = " ".join([str(a.get("title", "")), str(a.get("shrnuti", "")),
                    " ".join(str(t) for t in (a.get("temata") or []))])
    return is_poll_text(txt)


# ---------- pomocné čtení a zápis ----------

def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ---------- úschova (neveřejně čitelná) ----------

def load_hold():
    try:
        with open(HOLD, encoding="ascii") as f:
            raw = f.read().strip()
        return json.loads(gzip.decompress(base64.b64decode(raw)).decode("utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}


def save_hold(h):
    if not h or (not h.get("articles") and not h.get("static")):
        if os.path.exists(HOLD):
            os.remove(HOLD)
        return
    blob = gzip.compress(json.dumps(h, ensure_ascii=False, sort_keys=True).encode("utf-8"), mtime=0)
    text = base64.b64encode(blob).decode("ascii")
    try:
        with open(HOLD, encoding="ascii") as f:
            if f.read().strip() == text:
                return
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(HOLD), exist_ok=True)
    with open(HOLD, "w", encoding="ascii") as f:
        f.write(text)


def held_ids():
    return {a.get("id") for a in load_hold().get("articles", []) if a.get("id")}


def hold_articles(items):
    h = load_hold()
    cur = {a["id"]: a for a in h.get("articles", []) if a.get("id")}
    for a in items:
        if a.get("id"):
            cur[a["id"]] = a
    h["articles"] = list(cur.values())
    save_hold(h)


def enter(data):
    """Zapnuté moratorium: články o průzkumech a statické soubory s průzkumy se uschovají."""
    h = load_hold()
    held = {a["id"]: a for a in h.get("articles", []) if a.get("id")}
    keep = []
    for a in data:
        if is_poll_article(a):
            if a.get("id"):
                held[a["id"]] = a
        else:
            keep.append(a)
    h["articles"] = list(held.values())
    st = h.get("static", {})
    for name in STATIC:
        path = "czechia/" + name
        cur = _read(path, [])
        if cur:
            st[name] = cur
            _write(path, [])
    h["static"] = st
    save_hold(h)
    return keep


def leave(data):
    """Moratorium skončilo: uschovaná data se vrátí zpět."""
    h = load_hold()
    if not h:
        return data
    ids = {a.get("id") for a in data}
    back = [a for a in h.get("articles", []) if a.get("id") not in ids]
    for name, content in (h.get("static") or {}).items():
        path = "czechia/" + name
        if content and not _read(path, []):
            _write(path, content)
    if os.path.exists(HOLD):
        os.remove(HOLD)
    print("Moratorium skončilo, vráceno článků:", len(back))
    return data + back


# ---------- čištění veřejných výstupů ----------

def write_empty_polls():
    _write("czechia/polls.json", {
        "updated": datetime.datetime.utcnow().isoformat(timespec="minutes"),
        "pruzkumy": [],
        "moratorium": True,
    })


def _bad(s):
    return is_poll_text(s)


def sanitize_outputs():
    d = _read("czechia/summary.json", None)
    if isinstance(d, dict):
        for s in (d.get("obdobi") or {}).values():
            if _bad(s.get("uvod")):
                s["uvod"] = NEUTRAL_INTRO
            for k in ("praha", "cr", "temata"):
                s[k] = [x for x in (s.get(k) or []) if not _bad(x)]
            if _bad(s.get("pozn")):
                s["pozn"] = ""
        _write("czechia/summary.json", d)

    d = _read("czechia/topics.json", None)
    if isinstance(d, dict):
        out = []
        for t in d.get("temata") or []:
            if _bad(t.get("nadpis")) or _bad(t.get("popis")) or _bad(t.get("rozdily")):
                continue
            t["clanky"] = [c for c in (t.get("clanky") or []) if not _bad(c.get("title"))]
            t["pohledy"] = [p for p in (t.get("pohledy") or []) if not _bad(p.get("uhel"))]
            out.append(t)
        d["temata"] = out
        _write("czechia/topics.json", d)

    d = _read("czechia/parties.json", None)
    if isinstance(d, dict):
        for p in (d.get("strany") or {}).values():
            for k in ("profil", "kritika"):
                if _bad(p.get(k)):
                    p[k] = ""
            p["temata"] = [x for x in (p.get("temata") or []) if not _bad(x)]
            p["sliby"] = [s for s in (p.get("sliby") or []) if not _bad(s.get("slib"))]
        _write("czechia/parties.json", d)

    d = _read("czechia/politicians.json", None)
    if isinstance(d, dict):
        for rows in (d.get("politici") or {}).values():
            for r in rows:
                r["clanky"] = [c for c in (r.get("clanky") or []) if not _bad(c.get("title"))]
        _write("czechia/politicians.json", d)

    for name in ("articles.json", "articles_recent.json"):
        path = "czechia/" + name
        arts = _read(path, None)
        if isinstance(arts, list):
            clean = [a for a in arts if not is_poll_article(a)]
            if len(clean) != len(arts):
                _write(path, clean)

    write_empty_polls()
