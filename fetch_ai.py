#!/usr/bin/env python3
"""AI monitor: RSS zprávy o AI + výroky Elona Muska -> ai/data.json (Gemini)."""
import html
import json
import os
import re
import sys
import time
from calendar import timegm
from datetime import datetime, timedelta, timezone

import feedparser
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")  # viz fetch_usa.py
OUT = "ai/data.json"

NEWS_FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("Google News", "https://news.google.com/rss/search?q=artificial+intelligence+when:3d&hl=en-US&gl=US&ceid=US:en"),
]
MUSK_FEEDS = [
    ("Google News", "https://news.google.com/rss/search?q=%22Elon+Musk%22+AI+when:14d&hl=en-US&gl=US&ceid=US:en"),
    ("Google News", "https://news.google.com/rss/search?q=Musk+AGI+OR+Grok+OR+%22universal+high+income%22+when:14d&hl=en-US&gl=US&ceid=US:en"),
]


def clean(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def collect(feeds, per_feed, max_days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_days)
    seen, items = set(), []
    for source, url in feeds:
        try:
            feed = feedparser.parse(url)
        except Exception as exc:  # feed může být nedostupný
            print(f"Feed selhal ({source}): {exc}")
            continue
        n = 0
        for e in feed.entries:
            link, title = e.get("link"), clean(e.get("title"))
            if not link or not title or link in seen:
                continue
            p = e.get("published_parsed") or e.get("updated_parsed")
            dt = datetime.fromtimestamp(timegm(p), timezone.utc) if p else datetime.now(timezone.utc)
            if dt < cutoff:
                continue
            seen.add(link)
            items.append({
                "source": source,
                "title": title[:200],
                "url": link,
                "date": dt.strftime("%Y-%m-%d"),
                "text": clean(e.get("summary"))[:350],
            })
            n += 1
            if n >= per_feed:
                break
    return items


def load_old():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ask_gemini(prompt):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3)
    last = None
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt, config=cfg)
            return json.loads(resp.text)
        except Exception as exc:
            last = exc
            print(f"Gemini pokus {attempt + 1} selhal: {exc}")
            time.sleep(10 * (attempt + 1))
    raise last


def main():
    news = collect(NEWS_FEEDS, per_feed=8, max_days=4)
    musk_items = collect(MUSK_FEEDS, per_feed=10, max_days=14)
    if len(news) < 5:
        print("Málo zpráv z RSS, ponechávám původní data.")
        sys.exit(1)

    old = load_old()
    old_musk = old.get("musk", [])

    prompt = f"""Jsi redaktor českého AI monitoru. Piš česky, věcně a neutrálně.
Pracuj POUZE s položkami níže. Nic si nevymýšlej, žádná čísla ani citáty, které v položkách nejsou.
URL kopíruj přesně z položek. Texty parafrázuj vlastními slovy, nekopíruj věty ze zdrojů.

ZPRÁVY (JSON):
{json.dumps(news, ensure_ascii=False)}

ZPRÁVY O MUSKOVI (JSON):
{json.dumps(musk_items, ensure_ascii=False)}

STÁVAJÍCÍ ČASOVÁ OSA MUSKOVÝCH VÝROKŮ (JSON):
{json.dumps(old_musk, ensure_ascii=False)}

Vrať JSON přesně v tomto tvaru:
{{
  "articles": [  // 6 až 8 nejdůležitějších a různorodých zpráv o AI
    {{"title": "krátký český titulek", "summary": "2 věty česky", "tag": "jedno slovo: Modely|Regulace|Bezpečnost|Ekonomika|Věda|Společnost|Byznys|Hardware", "url": "URL z položky"}}
  ],
  "musk": [  // 0 až 3 NOVÉ výroky Elona Muska o AI, jen pokud je položka výslovně uvádí a nejsou už v časové ose
    {{"headline": "hlavní myšlenka česky, max 12 slov", "text": "1–2 věty česky", "url": "URL z položky"}}
  ],
  "essay": ["4 až 5 odstavců české úvahy o budoucnosti AI s ohledem na Muskovy výroky (časová osa i nové položky) a dnešní zprávy",
            "vyvážené: zohledni rozpor mezi Muskovými termíny a realitou, jeho zájem jako majitele xAI, rizika, ekonomiku a politiku",
            "každý odstavec max 90 slov, bez nadpisů, bez odrážek"],
  "watch": "1 věta: co sledovat v nejbližších týdnech"
}}"""

    data = ask_gemini(prompt)

    by_url = {i["url"]: i for i in news + musk_items}

    articles = []
    for a in data.get("articles", []):
        src = by_url.get(a.get("url"))
        if not src or not a.get("title") or not a.get("summary"):
            continue
        articles.append({
            "title": a["title"][:140],
            "summary": a["summary"][:420],
            "tag": str(a.get("tag", "AI"))[:20],
            "source": src["source"],
            "url": src["url"],
            "date": src["date"],
        })
    essay = [p.strip() for p in data.get("essay", []) if isinstance(p, str) and p.strip()]
    if len(articles) < 3 or len(essay) < 3:
        print("Neplatný výstup modelu, ponechávám původní data.")
        sys.exit(1)

    musk = list(old_musk)
    have = {m.get("url") for m in musk} | {m.get("headline") for m in musk}
    for m in data.get("musk", []):
        src = by_url.get(m.get("url"))
        if not src or not m.get("headline") or m["url"] in have or m["headline"] in have:
            continue
        musk.append({
            "sort": src["date"],
            "date": src["date"],
            "headline": m["headline"][:120],
            "text": str(m.get("text", ""))[:360],
            "url": src["url"],
        })
    musk.sort(key=lambda m: m.get("sort", ""))
    musk = musk[-8:]

    out = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "articles": articles[:8],
        "musk": musk,
        "essay": essay[:5],
        "watch": str(data.get("watch", ""))[:300],
    }
    os.makedirs("ai", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(out['articles'])} článků, {len(out['musk'])} výroků Muska.")


if __name__ == "__main__":
    main()
