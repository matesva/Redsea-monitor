import os, json, re, hashlib, datetime, html, urllib.request
from collections import Counter
from email.utils import parsedate_to_datetime
import feedparser
from google import genai

from czechia_config import (
    MODEL, OUT, PARTIES_OUT, POLLS_OUT, MAX_NEW, BATCH, MAX_FETCH_TEXT,
    MIN_STRAN, PARTY_LIST, FEEDS, KEYWORDS, POLL_RE, PROMPT, PROFILE_PROMPT,
)
from czechia_politici import clean_politici, build_politici
from czechia_summary import build_summary
from czechia_rss import build_rss

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(path, obj):
    os.makedirs("czechia", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)

def parse_json(text):
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw).strip()
    return json.loads(raw)

def collect(existing_ids):
    new, ok, failed = [], 0, []
    for url in FEEDS:
        try:
            feed = feedparser.parse(
                url, agent="Mozilla/5.0 (compatible; politicky-prehled-bot)")
            if feed.bozo and not feed.entries:
                raise ValueError(str(feed.bozo_exception))
        except Exception as ex:
            failed.append((url, str(ex)[:80]))
            continue
        ok += 1
        for e in feed.entries:
            link = e.get("link", "")
            title = e.get("title", "")
            text = f"{title} {e.get('summary', '')}"
            _id = hashlib.sha1(link.encode()).hexdigest()[:16]
            if not link or _id in existing_ids or not KEYWORDS.search(text):
                continue
            existing_ids.add(_id)
            new.append({
                "id": _id,
                "title": title,
                "link": link,
                "source": (e.get("source", {}) or {}).get("title")
                          or feed.feed.get("title", url),
                "published": e.get("published", ""),
                "snippet": re.sub(r"<[^>]+>", "", e.get("summary", ""))[:500],
            })
    print(f"Feedy OK: {ok}/{len(FEEDS)}")
    for u, why in failed:
        print("  SELHAL:", u, why)
    return new[:MAX_NEW]

def fetch_text(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; politicky-prehled-bot)"})
    with urllib.request.urlopen(req, timeout=10) as r:
        page = r.read(400000).decode("utf-8", "ignore")
    page = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", page)
    txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))
    idx = txt.lower().find("průzkum")
    start = max(0, idx - 200) if idx >= 0 else 0
    return txt[start:start + 2500]

def enrich_poll_articles(new):
    done = 0
    for a in new:
        if done >= MAX_FETCH_TEXT:
            break
        if "news.google.com" in a["link"] or not POLL_RE.search(a["title"]):
            continue
        try:
            body = fetch_text(a["link"])
            if len(body) > 200:
                a["snippet"] = body
                done += 1
        except Exception as ex:
            print("Nelze stáhnout text:", a["link"][:70], str(ex)[:60])
    print(f"Stažen text u článků o průzkumech: {done}")

def analyze(client, articles):
    payload = [{"id": a["id"], "titulek": a["title"], "text": a["snippet"],
                "zdroj": a["source"]} for a in articles]
    prompt = PROMPT.replace("{PARTIES}", ", ".join(PARTY_LIST))
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt + json.dumps(payload, ensure_ascii=False),
    )
    parsed = parse_json(resp.text)
    if isinstance(parsed, dict):
        parsed = next((v for v in parsed.values() if isinstance(v, list)), [])
    return {str(r["id"]): r for r in parsed}

def clean_pruzkum(p):
    if not isinstance(p, dict):
        return None
    vys = {}
    for k, v in (p.get("vysledky") or {}).items():
        try:
            v = float(str(v).replace(",", ".").replace("%", "").strip())
        except ValueError:
            continue
        if k in PARTY_LIST and 0 < v <= 60:
            vys[k] = v
    if len(vys) < MIN_STRAN or sum(vys.values()) > 105:
        return None
    return {"agentura": str(p.get("agentura") or "neuvedeno")[:40],
            "region": "Praha" if p.get("region") == "Praha" else "ČR",
            "vysledky": vys}

def clean_fields(r):
    r["strany"] = [s for s in (r.get("strany") or []) if s in PARTY_LIST]
    sliby = []
    for s in r.get("sliby") or []:
        if isinstance(s, dict) and s.get("strana") in PARTY_LIST and s.get("slib"):
            sliby.append({"strana": s["strana"], "slib": s["slib"],
                          "tema": s.get("tema", "")})
    r["sliby"] = sliby
    if r.get("overeni") not in ("pravda", "nepravda", "zavádějící", "nelze určit"):
        r["overeni"] = None
    r["pruzkum"] = clean_pruzkum(r.get("pruzkum"))
    r["politici"] = clean_politici(r.get("politici"), PARTY_LIST)
    return r

def article_date(a):
    try:
        return parsedate_to_datetime(a.get("published", "")).date().isoformat()
    except Exception:
        return (a.get("added") or "")[:10]

def build_polls(data):
    seen, polls = set(), []
    for a in data:
        p = a.get("pruzkum")
        if not p:
            continue
        d = article_date(a)
        key = (p["agentura"].lower(), p["region"], d,
               tuple(sorted(p["vysledky"].items())))
        if key in seen:
            continue
        seen.add(key)
        polls.append({**p, "datum": d, "link": a["link"], "zdroj": a["source"]})
    polls.sort(key=lambda x: x["datum"], reverse=True)
    save_json(POLLS_OUT, {
        "updated": datetime.datetime.utcnow().isoformat(timespec="minutes"),
        "pruzkumy": polls[:300],
    })
    print(f"Průzkumů uloženo: {len(polls)}")

def build_parties(client, data):
    prev = load_json(PARTIES_OUT, {}).get("strany", {})
    cutoff = (datetime.datetime.utcnow()
              - datetime.timedelta(days=90)).isoformat(timespec="minutes")
    result, digest = {}, {}
    for name in PARTY_LIST:
        arts = [a for a in data
                if name in (a.get("strany") or []) and a.get("added", "") >= cutoff]
        if not arts:
            continue
        tony = {"pozitivní": 0, "neutrální": 0, "kritický": 0}
        for a in arts:
            tony[a.get("ton") if a.get("ton") in tony else "neutrální"] += 1
        temata = Counter(t for a in arts for t in (a.get("temata") or []))
        sliby, seen = [], set()
        for a in arts:
            for s in a.get("sliby") or []:
                if s.get("strana") != name:
                    continue
                key = s["slib"].lower()[:60]
                if key in seen:
                    continue
                seen.add(key)
                sliby.append({"slib": s["slib"], "tema": s.get("tema", ""),
                              "link": a["link"], "zdroj": a["source"],
                              "datum": a.get("published") or a.get("added", "")})
        overeni = Counter(a["overeni"] for a in arts if a.get("overeni"))
        result[name] = {
            "pocet": len(arts),
            "praha": sum(1 for a in arts if a.get("region") == "Praha"),
            "tony": tony,
            "temata": [t for t, _ in temata.most_common(6)],
            "sliby": sliby[:40],
            "overeni": dict(overeni),
            "profil": prev.get(name, {}).get("profil", ""),
            "kritika": prev.get(name, {}).get("kritika", ""),
        }
        if len(arts) >= 3:
            digest[name] = [a.get("shrnuti", "") for a in arts[:12] if a.get("shrnuti")]
    if digest:
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=PROFILE_PROMPT + json.dumps(digest, ensure_ascii=False),
            )
            for name, p in parse_json(resp.text).items():
                if name in result and isinstance(p, dict):
                    result[name]["profil"] = p.get("profil", "")
                    result[name]["kritika"] = p.get("kritika", "")
        except Exception as ex:
            print(f"Chyba Gemini u profilů ({type(ex).__name__}):", str(ex)[:300])
    save_json(PARTIES_OUT, {
        "updated": datetime.datetime.utcnow().isoformat(timespec="minutes"),
        "strany": result,
    })
    print(f"Profily stran: {len(result)}")

def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    data = load_json(OUT, [])
    new = collect({a["id"] for a in data})
    enrich_poll_articles(new)
    added = 0
    for i in range(0, len(new), BATCH):
        batch = new[i:i + BATCH]
        try:
            res = analyze(client, batch)
        except Exception as ex:
            print(f"Chyba Gemini ({type(ex).__name__}):", str(ex)[:400])
            continue
        for a in batch:
            r = res.get(a["id"])
            if not r or not r.get("relevantni", True):
                continue
            r = clean_fields(r)
            a.update({k: r.get(k) for k in
                      ("shrnuti", "region", "temata", "strany", "ton",
                       "sliby", "overeni", "pruzkum", "politici")})
            a.pop("snippet", None)
            a["added"] = datetime.datetime.utcnow().isoformat(timespec="minutes")
            data.append(a)
            added += 1
    print(f"Přidáno článků: {added}, celkem: {len(data)}")
    if data and added:
        data = sorted(data, key=lambda a: a["added"], reverse=True)[:1500]
        save_json(OUT, data)
    if data:
        build_polls(data)
        build_politici(data)
        build_rss(data)
    if data and (added or not os.path.exists(PARTIES_OUT)):
        build_parties(client, data)
    if data and (added or not os.path.exists("czechia/summary.json")):
        build_summary(client, data)

if __name__ == "__main__":
    main()
