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
from czechia_notify import notify_czechia
from czechia_topics import build_topics


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
        e
