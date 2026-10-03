import json, os, re, datetime
from czechia_config import MODEL
from czechia_politici import article_dt

OUT = "czechia/topics.json"

PROMPT = """Jsi věcný, politicky neutrální redaktor. Dostaneš očíslované zprávy
(i, zdroj, region, text) z posledních hodin. Najdi události, o kterých píší
alespoň 2 RŮZNÉ zdroje, a seskup je. Vrať JSON pole max. 5 příběhů seřazených
podle počtu zdrojů, každý s klíči:
- "nadpis": krátký neutrální nadpis události
- "popis": 1–2 věty, co se stalo
- "indexy": pole hodnot i zpráv, které k události patří
- "pohledy": pole objektů {"zdroj": "...", "uhel": "jedna krátká věta: na co
  zpráva klade důraz"} (nejvýše jeden na zdroj)
- "rozdily": 1 věta, v čem se zdroje liší důrazem nebo tónem, jinak ""
Pravidla: čerpej jen z podkladů, nic nedomýšlej, nehodnoť, nedoporučuj komu
volit. Pouze JSON.

Zprávy:
"""


def _parse(text):
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw).strip()
    return json.loads(raw)


def build_topics(client, data):
    now = datetime.datetime.utcnow()
    lim = now - datetime.timedelta(hours=36)
    arts = []
    for a in data:
        d = article_dt(a)
        if a.get("shrnuti") and d and d >= lim:
            arts.append(a)
        if len(arts) >= 80:
            break
    if len(arts) < 6:
        print("Téma dne: málo zpráv, ponechávám předchozí")
        return

    items = [{"i": i, "zdroj": a.get("source", ""), "region": a.get("region", ""),
              "text": a["shrnuti"]} for i, a in enumerate(arts)]
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=PROMPT + json.dumps(items, ensure_ascii=False),
        )
        parsed = _parse(resp.text)
        if isinstance(parsed, dict):
            parsed = next((v for v in parsed.values() if isinstance(v, list)), [])
    except Exception as ex:
        print("Téma dne: chyba Gemini (%s): %s" % (type(ex).__name__, str(ex)[:300]))
        return

    out = []
    for s in parsed:
        if not isinstance(s, dict):
            continue
        idx = [i for i in (s.get("indexy") or [])
               if isinstance(i, int) and 0 <= i < len(arts)]
        srcs = {arts[i].get("source", "") for i in idx}
        if len(srcs) < 2:
            continue
        out.append({
            "nadpis": str(s.get("nadpis", "")),
            "popis": str(s.get("popis", "")),
            "zdroju": len(srcs),
            "clanky": [{"title": arts[i].get("title", ""), "link": arts[i].get("link", ""),
                        "source": arts[i].get("source", ""), "ton": arts[i].get("ton", "")}
                       for i in idx][:10],
            "pohledy": [{"zdroj": str(p.get("zdroj", "")), "uhel": str(p.get("uhel", ""))}
                        for p in (s.get("pohledy") or []) if isinstance(p, dict)][:8],
            "rozdily": str(s.get("rozdily", "")),
        })
    out.sort(key=lambda x: -x["zdroju"])
    os.makedirs("czechia", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": now.isoformat(timespec="minutes"), "temata": out[:5]},
                  f, ensure_ascii=False, indent=1)
    print("Téma dne:", len(out[:5]))
