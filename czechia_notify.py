import os, json, hashlib, datetime, urllib.request
from zoneinfo import ZoneInfo

NTFY_URL = "https://ntfy.sh/"
SITE = "https://matesva.github.io/Redsea-monitor/czechia/"
STATE = "czechia/notify_state.json"
BIG = 3.0  # změna v procentních bodech, od které se upozorní zvlášť


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(state):
    os.makedirs("czechia", exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def send(topic, title, message, priority=3, tags=None, click=None):
    payload = {"topic": topic, "title": title,
               "message": message[:3500], "priority": priority}
    if tags:
        payload["tags"] = tags
    if click:
        payload["click"] = click
    req = urllib.request.Request(
        NTFY_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception as ex:
        print("ntfy chyba:", str(ex)[:200])
        return False


def poll_key(p):
    raw = "|".join([
        p.get("agentura", ""), p.get("region", ""), p.get("datum", ""),
        ",".join("%s=%s" % kv for kv in sorted(p.get("vysledky", {}).items())),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _cz(v):
    return ("%.1f" % v).replace(".", ",")


def format_poll(p, polls):
    vys = p["vysledky"]
    top = sorted(vys.items(), key=lambda kv: -kv[1])[:5]
    lines = [" · ".join("%s %s %%" % (k, _cz(v)) for k, v in top)]
    prev = [q for q in polls
            if q is not p
            and q.get("agentura") == p.get("agentura")
            and q.get("region") == p.get("region")
            and q.get("datum", "") < p.get("datum", "")]
    big = False
    if prev:
        prev.sort(key=lambda q: q["datum"], reverse=True)
        old = prev[0]["vysledky"]
        diffs = [(k, v - old[k]) for k, v in vys.items() if k in old]
        if diffs:
            k, dv = max(diffs, key=lambda kv: abs(kv[1]))
            if abs(dv) >= BIG:
                big = True
                lines.append("Největší změna: %s %s%s p. b. oproti předchozímu průzkumu."
                             % (k, "+" if dv > 0 else "−", _cz(abs(dv))))
    lines.append("Zdroj: %s" % p.get("zdroj", ""))
    return "\n".join(lines), big


def _parse_utc(s):
    try:
        return datetime.datetime.fromisoformat(str(s))
    except ValueError:
        return None


def notify_czechia(polls, summary):
    topic = os.environ.get("NTFY_TOPIC_CZECHIA", "").strip()
    state = _load(STATE, None)
    now_cz = datetime.datetime.now(ZoneInfo("Europe/Prague"))
    today = now_cz.date().isoformat()
    keys = {poll_key(p): p for p in polls}

    if state is None:
        _save({"polls": sorted(keys), "last_digest": "", "digest_hash": ""})
        print("Notifikace: první běh, stávající průzkumy označeny jako známé (bez odeslání)")
        return
    if not topic:
        print("Notifikace: NTFY_TOPIC_CZECHIA není nastaveno, přeskakuji")
        return

    seen = set(state.get("polls", []))
    for k in sorted(keys, key=lambda k: keys[k].get("datum", "")):
        if k in seen:
            continue
        p = keys[k]
        msg, big = format_poll(p, polls)
        title = "Nový průzkum: %s (%s)" % (p.get("agentura", "?"), p.get("region", ""))
        if send(topic, title, msg, priority=4 if big else 3,
                tags=["bar_chart"], click=SITE):
            seen.add(k)
            print("Notifikace odeslána:", title)
    state["polls"] = sorted(seen)

    s = ((summary or {}).get("obdobi") or {}).get("1")
    upd = _parse_utc((summary or {}).get("updated", ""))
    fresh = upd is not None and (datetime.datetime.utcnow() - upd).total_seconds() < 20 * 3600
    in_window = 6 <= now_cz.hour < 14
    if s and fresh and in_window and state.get("last_digest") != today:
        lines = [s.get("uvod", "")]
        lines += ["• " + x for x in (s.get("praha") or [])[:2]]
        lines += ["• " + x for x in (s.get("cr") or [])[:2]]
        text = "\n".join(l for l in lines if l)
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        if h == state.get("digest_hash"):
            print("Notifikace: shrnutí je stejné jako minule, přeskakuji")
        elif send(topic, "Česká politika: ranní přehled", text,
                  priority=3, tags=["newspaper"], click=SITE):
            state["last_digest"] = today
            state["digest_hash"] = h
            print("Notifikace odeslána: ranní přehled")
    _save(state)
