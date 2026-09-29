import json, os, re, datetime
from czechia_config import MODEL
from czechia_politici import article_dt

OUT = "czechia/summary.json"

PROMPT = """Jsi věcný, politicky neutrální redaktor. Z podkladů (shrnutí zpráv) sepiš
přehled česky. Vrať JSON objekt s klíči:
- "uvod": 2–3 věty o tom, co se v daném období hlavně dělo
- "praha": pole 3–5 odrážek (každá 1 věta) o dění v Praze a předvolebním dění
- "cr": pole 3–5 odrážek (každá 1 věta) o dění v celé republice
- "temata": pole max. 5 nejčastějších témat
- "pozn": 1 věta o tom, kde se média nebo strany rozcházejí, jinak prázdný řetězec
Pravidla: čerpej jen z podkladů, nic si nedomýšlej, nehodnoť, nedoporučuj komu
volit, jmenuj strany a osoby jen pokud jsou v podkladech. Pouze JSON.

Podklady:
"""

def _parse(text):
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw).strip()
    return json.loads(raw)

def _load_prev():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f).get("obdobi", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _lst(x, n):
    return [str(i) for i in (x or [])][:n]

def build_summary(client, data):
    prev = _load_prev()
    now = datetime.datetime.utcnow()
    res = {}
    for days in (1, 7):
        key = str(days)
        lim = now - datetime.timedelta(days=days)
        arts = [a for a in data
                if a.get("shrnuti")
                and (article_dt(a) or datetime.datetime.min) >= lim]
        if len(arts) < 3:
            if key in prev:
                res[key] = prev[key]
            continue
        items = [{"region": a.get("region"), "zdroj": a.get("source"),
                  "text": a["shrnuti"]} for a in arts[:60]]
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=PROMPT + json.dumps(items, ensure_ascii=False),
            )
            s = _parse(resp.text)
            res[key] = {
                "uvod": str(s.get("uvod", "")),
                "praha": _lst(s.get("praha"), 5),
                "cr": _lst(s.get("cr"), 5),
                "temata": _lst(s.get("temata"), 5),
                "pozn": str(s.get("pozn", "")),
                "pocet": len(arts),
            }
        except Exception as ex:
            print(f"Chyba Gemini u shrnutí ({type(ex).__name__}):", str(ex)[:300])
            if key in prev:
                res[key] = prev[key]
    os.makedirs("czechia", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": now.isoformat(timespec="minutes"), "obdobi": res},
                  f, ensure_ascii=False, indent=1)
    print("Shrnutí zpráv:", list(res.keys()))
