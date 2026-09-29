import os, json, re, hashlib, datetime, html, urllib.parse, urllib.request
from collections import Counter
from email.utils import parsedate_to_datetime
import feedparser
from google import genai

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
OUT = "czechia/articles.json"
PARTIES_OUT = "czechia/parties.json"
POLLS_OUT = "czechia/polls.json"
MAX_NEW = 120
BATCH = 10
MAX_FETCH_TEXT = 15   # kolik článků o průzkumech za běh stáhnout celých
MIN_STRAN = 3         # minimum stran v průzkumu, aby se uložil

PARTY_LIST = [
    "ANO", "ODS", "STAN", "Piráti", "SPD", "TOP 09", "KDU-ČSL", "Motoristé",
    "Stačilo", "ČSSD", "KSČM", "Zelení", "Přísaha", "Svobodní", "Trikolora",
    "Prague Together", "Praha Sobě", "Spojené síly pro Prahu", "Naše Praha",
]

def gnews(q, days=3):
    qq = urllib.parse.quote_plus(f"{q} when:{days}d")
    return f"https://news.google.com/rss/search?q={qq}&hl=cs&gl=CZ&ceid=CZ:cs"

FEEDS = [
    "https://ct24.ceskatelevize.cz/rss/hlavni-zpravy",
    "https://www.irozhlas.cz/rss/irozhlas",
    "https://www.irozhlas.cz/rss/irozhlas/section/zpravy-domov",
    "https://www.ceskenoviny.cz/sluzby/rss/zpravy.php",
    "https://www.novinky.cz/rss",
    "https://www.aktualne.cz/rss/",
    "https://www.seznamzpravy.cz/rss",
    "https://servis.idnes.cz/rss.aspx?c=zpravodaj",
    "https://servis.idnes.cz/rss.aspx?c=praha",
    "https://servis.lidovky.cz/rss.aspx?r=ln_domov",
    "https://www.blesk.cz/rss",
    "https://www.denik.cz/rss/",
    "https://hn.cz/rss/",
    "https://www.info.cz/rss",
    "https://denikn.cz/feed/",
    "https://echo24.cz/rss",
    "https://www.reflex.cz/rss",
    "https://www.forum24.cz/feed/",
    "https://www.parlamentnilisty.cz/export/rss.aspx",
    "https://www.respekt.cz/rss",
    "https://demagog.cz/rss",
]

PARTIES = [
    "ANO Babiš", "ODS Fiala", "STAN Rakušan", "Piráti Hřib", "SPD Okamura",
    "TOP 09", "KDU-ČSL Výborný", "Motoristé sobě", "Stačilo", "ČSSD",
    "KSČM", "Zelení", "Přísaha", "Svobodní", "Trikolora", "Prague Together",
    "Praha Sobě", "Spojené síly pro Prahu", "Naše Praha",
]
PRAHA_QUERIES = [
    "volby Praha", "komunální volby Praha kandidáti", "kandidátka Praha volby",
    "primátor Praha", "Praha zastupitelstvo koalice", "Praha rozpočet magistrát",
    "Praha MHD doprava politika", "Praha bydlení metropolitní plán",
    "Praha městské části volby", "lídr kandidátky Praha",
    "předvolební debata Praha", "průzkum volební preference Praha",
    "předvolební slib Praha", "volební program Praha",
    "volební model Praha průzkum",
]
CR_QUERIES = [
    "česká politika", "volební průzkum preference", "vláda koalice krize",
    "Poslanecká sněmovna hlasování", "Senát volby", "prezident Pavel politika",
    "předvolební kampaň", "komentář politika", "názor volby",
    "rozpočet státní dluh vláda", "Ústavní soud politika", "krajské volby",
    "volby do zastupitelstev obcí", "průzkum STEM Median Kantar",
    "politický spor", "volební program slibuje", "předvolební slib",
    "Demagog ověřil výrok politik", "průzkum STEM preference",
    "průzkum Kantar preference", "průzkum Median preference",
    "průzkum NMS preference", "průzkum Ipsos preference", "volební model",
]
FEEDS += [gnews(q) for q in PARTIES + PRAHA_QUERIES + CR_QUERIES]

KEYWORDS = re.compile(
    r"vol[bby]|politi|kandid|strana|hnutí|koalic|opozic|vláda|parlament|"
    r"senát|primátor|zastupitel|slib|program|průzkum|preferenc|ANO|ODS|"
    r"STAN|Piráti|SPD|TOP 09|KDU|ČSSD|Praha",
    re.I,
)
POLL_RE = re.compile(r"průzkum|preferenc|volební model|odhad", re.I)

PROMPT = """Jsi věcný analytik české politiky. Pro každý článek vrať JSON pole objektů
se stejným pořadím a těmito klíči:
- "id": beze změny
- "shrnuti": 1–2 věcné české věty, vlastními slovy, bez hodnocení
- "region": "Praha" | "ČR" | "Jiný"
- "temata": pole 1–3 krátkých témat (např. "doprava", "bydlení", "rozpočet")
- "strany": pole zmíněných stran, POUZE z tohoto seznamu: {PARTIES}. Ostatní vynech.
- "ton": "neutrální" | "kritický" | "pozitivní" (tón článku vůči hlavnímu aktérovi)
- "sliby": pole objektů {"strana": <ze seznamu>, "slib": "jedna krátká česká věta",
  "tema": "krátké téma"}. Uveď jen tehdy, když článek VÝSLOVNĚ uvádí slib, program
  nebo konkrétní návrh strany či jejího kandidáta. Nic si nedomýšlej. Jinak [].
- "overeni": null, nebo jedna z hodnot "pravda" | "nepravda" | "zavádějící" |
  "nelze určit", jen pokud jde o fact-checking politického výroku.
- "pruzkum": null, nebo objekt {"agentura": "název agentury", "region": "ČR" | "Praha",
  "vysledky": {"<strana ze seznamu>": číslo v procentech}}. Vyplň JEN když text
  výslovně uvádí číselné výsledky průzkumu stranických/volebních preferencí. Čísla
  přepiš přesně, nic nedopočítávej ani neodhaduj. Jinak null.
- "relevantni": true pokud jde o politiku/volby, jinak false
Vrať pouze JSON, žádný další text.

Články:
"""

PROFILE_PROMPT = """Jsi věcný, politicky neutrální analytik. Níže jsou pro každou stranu
shrnutí nedávných zpráv. Pro každou stranu napiš:
- "profil": 2–3 věty česky o tom, čím se strana v poslední době zabývá a co
  prosazuje, výhradně z dodaných shrnutí
- "kritika": 1 věta, co jí média či oponenti nejčastěji vytýkají (pokud to z
  podkladů plyne, jinak prázdný řetězec)
Nehodnoť, nedoporuč komu volit, nic si nedomýšlej. Vrať JSON objekt ve tvaru
{"<strana>": {"profil": "...", "kritika": "..."}}. Pouze JSON.

Podklady:
"""

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
                       "sliby", "overeni", "pruzkum")})
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
    if data and (added or not os.path.exists(PARTIES_OUT)):
        build_parties(client, data)

if __name__ == "__main__":
    main()
