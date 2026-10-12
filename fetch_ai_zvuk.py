#!/usr/bin/env python3
"""Sbírá články o AI ve zvukové postprodukci a shrnuje je přes Gemini."""
import html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

OUT = "ai-zvuk-data.json"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
KEY = os.environ.get("GEMINI_API_KEY", "")
MAX_KEEP, MAX_AGE_DAYS, MAX_NEW = 30, 60, 8
UA = {"User-Agent": "Mozilla/5.0 (compatible; ai-zvuk-bot/1.0)"}
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"


def gnews(q, hl="en-US", gl="US", ceid="US:en"):
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
            + f"&hl={hl}&gl={gl}&ceid={ceid}")


# (název, url, direct) – direct=True: plný text z feedu + filtr klíčových slov
FEEDS = [
    ("Production Expert", "https://www.production-expert.com/?format=rss", True),
    ("A Sound Effect", "https://www.asoundeffect.com/feed/", True),
    ("Designing Sound", "https://designingsound.org/feed/", True),
    ("postPerspective", "https://postperspective.com/feed/", True),
    ("Google News", gnews('AI ("audio post-production" OR "sound design" OR "dialogue replacement" OR "re-recording mixer" OR "sound editor") when:14d'), False),
    ("Google News", gnews('AI dubbing voice cloning film when:14d'), False),
    ("Google News", gnews('AI dabing OR "zvuková postprodukce" when:30d', "cs", "CZ", "CZ:cs"), False),
]

KEYWORDS = re.compile(
    r"\bAI\b|artificial intelligence|generative|machine learning|neural|"
    r"voice clon|dubbing|synthetic|deepfake|text-to-speech|\bTTS\b", re.I)


AUDIO = re.compile(
    r"sound|audio|dubb|dabing|dabér|dabing|zvuk|voice|vocal|dialogue|dialog|foley|"
    r"re-recording|mixer|mixing|post-production|postprodukc|speech|izotope|pro tools|"
    r"soundtrack|sfx", re.I)


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def clean(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def parse_date_iso(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def collect():
    found = {}
    for name, url, direct in FEEDS:
        try:
            root = ET.fromstring(get(url))
        except Exception as e:
            print(f"[skip] {name}: {e}", file=sys.stderr)
            continue
        for it in root.iter("item"):
            title = clean(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            if not title or not link.startswith("http"):
                continue
            text = ""
            source = name
            if not AUDIO.search(title):
                if not direct:
                    continue
            if direct:
                text = clean(it.findtext(CONTENT) or it.findtext("description"))[:3500]
                if not KEYWORDS.search(title + " " + text):
                    continue
                if not AUDIO.search(title + " " + text):
                    continue
            else:
                s = it.find("source")
                if s is not None and s.text:
                    source = s.text.strip()
                title = re.sub(r"\s+-\s+" + re.escape(source) + r"$", "", title)
            key = re.sub(r"\W+", "", title.lower())[:80]
            if key in found or any(a["link"] == link for a in found.values()):
                continue
            found[key] = {
                "title": title, "link": link, "source": source, "text": text,
                "published": parse_date(it.findtext("pubDate")).isoformat(),
            }
    return list(found.values())


def gemini(prompt):
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }).encode()
    models = [MODEL] + ([FALLBACK] if FALLBACK and FALLBACK != MODEL else [])
    for model in models:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
               f":generateContent?key={KEY}")
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    data = json.load(r)
                return json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
            except urllib.error.HTTPError as e:
                print(f"[gemini] {model} pokus {attempt + 1}: HTTP {e.code}", file=sys.stderr)
                if e.code in (400, 401, 403, 404):
                    break  # špatný model nebo klíč, další pokusy nemají smysl
            except Exception as e:
                print(f"[gemini] {model} pokus {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    return None


def summarize(batch):
    lines = []
    for i, a in enumerate(batch):
        lines.append(f"ID {i}\nTitulek: {a['title']}\nZdroj: {a['source']}\n"
                     f"Text: {a['text'] or '(není k dispozici, jen titulek)'}\n")
    prompt = (
        "Jsi redaktor webu o zvukové postprodukci (dialogy, ADR = automated dialogue replacement, "
        "dabing, sound design, střih zvuku, mix, hudba a zvuk pro film a TV). "
        "U každého článku nejprve posuď, zda se skutečně týká zvuku, zvukové postprodukce, dabingu nebo hlasů "
        "ve filmu a médiích ve spojení s AI. Články o čemkoli jiném (např. finance, ADR jako "
        "depozitní certifikáty, medicína, právo) označ relevant=false. "
        "U relevantních napiš česky shrnutí o 2–3 větách, vlastními slovy, bez doslovných citací, "
        "se zaměřením na dopad AI na tuto profesi. Pokud je k dispozici jen titulek, napiš jednu "
        "krátkou větu o čem titulek je a nic nepřidávej ani nedomýšlej. "
        "Vrať POUZE JSON pole objektů {\"id\": číslo, \"relevant\": true/false, \"summary\": \"...\"}.\n\n"
        + "\n".join(lines))
    res = gemini(prompt)
    out = {}
    if isinstance(res, list):
        for r in res:
            try:
                out[int(r["id"])] = (bool(r.get("relevant", True)), str(r.get("summary", "")).strip())
            except Exception:
                pass
    return out


def overview(articles):
    lines = [f"- {a['title']}: {a['summary']}" for a in articles[:12]]
    prompt = (
        "Na základě těchto shrnutí napiš česky přehled o 4–5 větách: co se aktuálně děje s AI "
        "ve zvukové postprodukci a dabingu a jaké jsou hlavní trendy či obavy. Nepřidávej žádná "
        "fakta, která ve shrnutích nejsou. Vrať POUZE JSON {\"overview\": \"...\"}.\n\n"
        + "\n".join(lines))
    res = gemini(prompt)
    return res.get("overview", "").strip() if isinstance(res, dict) else ""


def main():
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {"articles": [], "overview": ""}
    rejected = list(old.get("rejected", []))
    # vyčistit dříve uložené články, které se zvuku netýkají
    kept_old = [a for a in old.get("articles", [])
                if AUDIO.search(a.get("title", "") + " " + a.get("summary", ""))]
    removed = len(old.get("articles", [])) - len(kept_old)
    known = {a["link"] for a in kept_old} | set(rejected)
    limit = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    fresh = [a for a in collect()
             if a["link"] not in known and parse_date_iso(a["published"]) > limit]
    fresh.sort(key=lambda a: a["published"], reverse=True)
    fresh = fresh[:MAX_NEW]
    print(f"Nových kandidátů: {len(fresh)}, vyřazeno starých nerelevantních: {removed}")

    added = []
    if fresh and KEY:
        sums = summarize(fresh)
        for i, a in enumerate(fresh):
            if i not in sums:
                continue  # Gemini neodpovědělo, zkusí se příště
            relevant, summ = sums[i]
            if relevant and summ:
                added.append({
                    "title": a["title"], "link": a["link"], "source": a["source"],
                    "published": a["published"], "summary": summ,
                    "basis": "text" if a["text"] else "titulek",
                })
            elif not relevant:
                rejected.append(a["link"])
    elif fresh:
        print("Chybí GEMINI_API_KEY, shrnutí přeskočena.", file=sys.stderr)

    arts = [a for a in added + kept_old
            if parse_date_iso(a["published"]) > limit]
    arts.sort(key=lambda a: a["published"], reverse=True)
    arts = arts[:MAX_KEEP]

    ov = old.get("overview", "")
    if KEY and arts and (added or removed or not ov):
        ov = overview(arts) or ov

    now = datetime.now(timezone.utc).isoformat()
    out = {"updated": now, "last_updated": now,
           "overview": ov, "articles": arts, "rejected": rejected[-300:]}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"Hotovo: {len(arts)} článků, {len(added)} nových, {len(rejected)} odmítnutých.")


if __name__ == "__main__":
    main()
