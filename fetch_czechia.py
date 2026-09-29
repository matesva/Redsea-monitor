import os, json, re, hashlib, datetime, urllib.parse
import feedparser
from google import genai

MODEL = "gemini-3.5-flash-lite"  # případně novější Flash / Flash-Lite
OUT = "czechia/articles.json"
MAX_NEW = 120

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
]
CR_QUERIES = [
    "česká politika", "volební průzkum preference", "vláda koalice krize",
    "Poslanecká sněmovna hlasování", "Senát volby", "prezident Pavel politika",
    "předvolební kampaň", "komentář politika", "názor volby",
    "rozpočet státní dluh vláda", "Ústavní soud politika", "krajské volby",
    "volby do zastupitelstev obcí", "průzkum STEM Median Kantar",
    "politický spor",
]
FEEDS += [gnews(q) for q in PARTIES + PRAHA_QUERIES + CR_QUERIES]

KEYWORDS = re.compile(
    r"vol[bby]|politi|kandid|strana|hnutí|koalic|opozic|vláda|parlament|"
    r"senát|primátor|zastupitel|ANO|ODS|STAN|Piráti|SPD|TOP 09|KDU|ČSSD|Praha",
    re.I,
)

def load():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

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
                "source": e.get("source", {}).get("title")
                          or feed.feed.get("title", url),
                "published": e.get("published", ""),
                "snippet": re.sub(r"<[^>]+>", "", e.get("summary", ""))[:500],
            })
    print(f"Feedy OK: {ok}/{len(FEEDS)}")
    for u, why in failed:
        print("  SELHAL:", u, why)
    return new[:MAX_NEW]

PROMPT = """Jsi analytik české politiky. Pro každý článek vrať JSON pole objektů
se stejným pořadím a klíči:
- "id": beze změny
- "shrnuti": 1–2 věcné české věty, vlastními slovy, bez hodnocení
- "region": "Praha" | "ČR" | "Jiný"
- "temata": pole 1–3 krátkých témat (např. "volby", "doprava", "rozpočet")
- "strany": pole zmíněných politických stran/hnutí (zkratky), může být prázdné
- "ton": "neutrální" | "kritický" | "pozitivní" (tón textu vůči hlavnímu aktérovi)
- "relevantni": true pokud jde o politiku/volby, jinak false
Vrať pouze JSON, žádný další text.

Články:
"""

def analyze(client, articles):
    payload = [{"id": a["id"], "titulek": a["title"], "text": a["snippet"],
                "zdroj": a["source"]} for a in articles]
    resp = client.models.generate_content(
        model=MODEL,
        contents=PROMPT + json.dumps(payload, ensure_ascii=False),
        config={"response_mime_type": "application/json", "temperature": 0.2},
    )
    return {r["id"]: r for r in json.loads(resp.text)}

def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    data = load()
    new = collect({a["id"] for a in data})
    if not new:
        print("Nic nového.")
        return
    for i in range(0, len(new), 10):
        batch = new[i:i + 10]
        try:
            res = analyze(client, batch)
        except Exception as ex:
            print("Chyba Gemini:", ex)
            continue
        for a in batch:
            r = res.get(a["id"])
            if not r or not r.get("relevantni", True):
                continue
            a.update({k: r.get(k) for k in
                      ("shrnuti", "region", "temata", "strany", "ton")})
            a.pop("snippet", None)
            a["added"] = datetime.datetime.utcnow().isoformat(timespec="minutes")
            data.append(a)
    data = sorted(data, key=lambda a: a["added"], reverse=True)[:1500]
    os.makedirs("czechia", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
