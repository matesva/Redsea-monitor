import feedparser
import json
import os
import urllib.request
import html
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
NTFY_TOPIC = os.environ.get("NTFY_TOPIC_MIDEAST") or os.environ.get("NTFY_TOPIC")

RSS_FEEDS = [
    "https://www.timesofisrael.com/feed/",
    "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
    "https://www.haaretz.com/cmlink/1.628752",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.middleeasteye.net/rss",
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://apnews.com/hub/middle-east?output=rss",
    "https://www.iranintl.com/en/rss",
    "https://www.naharnet.com/stories.rss",
    "https://www.rudaw.net/english/rss",
    "https://www.reuters.com/world/middle-east/rss",
    "https://english.alarabiya.net/.mrss/en.xml",
]

# Keywords deliberately EXCLUDE Houthi/Yemen/Red Sea/Bab-el-Mandeb terms,
# since that ground is already covered by the Red Sea Monitor.
KEYWORDS = [
    "Israel", "Gaza", "Hamas", "Hezbollah", "Iran", "Tehran", "Syria",
    "Damascus", "Lebanon", "Beirut", "Iraq", "Baghdad", "IDF",
    "West Bank", "Netanyahu", "Khamenei", "IRGC", "nuclear deal",
    "airstrike", "ceasefire", "Golan", "Kurdistan", "Erbil"
]

EXCLUDE_KEYWORDS = ["Houthi", "Yemen", "Red Sea", "Bab-el-Mandeb", "Bab al-Mandeb"]

THREAT_MAP = {"STABLE": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

LOCATIONS = {
    "Jerusalem": {"lat": 31.7683, "lon": 35.2137, "name_cs": "Jeruzalém", "name_en": "Jerusalem"},
    "Gaza": {"lat": 31.5017, "lon": 34.4668, "name_cs": "Gaza", "name_en": "Gaza"},
    "Tel Aviv": {"lat": 32.0853, "lon": 34.7818, "name_cs": "Tel Aviv", "name_en": "Tel Aviv"},
    "Tehran": {"lat": 35.6892, "lon": 51.3890, "name_cs": "Teherán", "name_en": "Tehran"},
    "Damascus": {"lat": 33.5138, "lon": 36.2765, "name_cs": "Damašek", "name_en": "Damascus"},
    "Beirut": {"lat": 33.8938, "lon": 35.5018, "name_cs": "Bejrút", "name_en": "Beirut"},
    "Baghdad": {"lat": 33.3152, "lon": 44.3661, "name_cs": "Bagdád", "name_en": "Baghdad"},
    "Erbil": {"lat": 36.1901, "lon": 44.0091, "name_cs": "Erbil", "name_en": "Erbil"},
    "West Bank": {"lat": 31.9522, "lon": 35.2332, "name_cs": "Západní břeh Jordánu", "name_en": "West Bank"},
}


def fetch_articles():
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = html.unescape(entry.get("title", ""))
                summary = html.unescape(entry.get("summary", ""))
                combined = (title + summary).lower()
                if any(ex.lower() in combined for ex in EXCLUDE_KEYWORDS):
                    continue
                if any(kw.lower() in combined for kw in KEYWORDS):
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "link": entry.get("link", "#"),
                        "published": entry.get("published", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
                        "source": feed.feed.get("title", "News")
                    })
        except Exception as e:
            print(f"Error processing feed {feed_url}: {e}")
            continue
    return articles[:20]


def extract_locations(articles):
    found = {}
    text_blob = " ".join([a['title'] + " " + a['summary'] for a in articles])
    for key, loc in LOCATIONS.items():
        if key.lower() in text_blob.lower():
            found[key] = {"key": key, "lat": loc["lat"], "lon": loc["lon"], "name_cs": loc["name_cs"], "name_en": loc["name_en"]}
    return list(found.values())


def fetch_yahoo_price(symbol, divisor=1):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    chart_result = result.get("chart", {}).get("result")
    if not chart_result:
        raise ValueError(f"Yahoo Finance returned no data for {symbol}")

    meta = chart_result[0].get("meta", {})
    price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
    timestamp = meta.get("regularMarketTime")

    if price is None:
        raise ValueError(f"Missing price in response for {symbol}")

    date_str = (datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
                if timestamp else datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    return {"value": round(float(price) / divisor, 2), "date": date_str, "cached": False}


def fetch_market_data(previous):
    data = {"brent": None, "ta35": None, "usdils": None}
    symbols = {"brent": ("BZ=F", 1), "ta35": ("TA35.TA", 1), "usdils": ("ILS=X", 1)}

    for label, (symbol, divisor) in symbols.items():
        try:
            data[label] = fetch_yahoo_price(symbol, divisor)
        except Exception as e:
            print(f"Error fetching {label} ({symbol}): {e}")

    if previous:
        for label in symbols:
            if not data.get(label) and previous.get(label):
                cached = dict(previous[label])
                cached["cached"] = True
                data[label] = cached

    return data


def fetch_usd_czk():
    try:
        url = "https://api.frankfurter.app/latest?from=USD&to=CZK"
        with urllib.request.urlopen(url, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            rate = result.get("rates", {}).get("CZK")
            date = result.get("date")
            if rate:
                return {"value": round(rate, 3), "date": date}
    except Exception as e:
        print(f"Error fetching USD/CZK rate: {e}")
    return None


def load_previous_data():
    if os.path.exists("middle-east/data.json"):
        try:
            with open("middle-east/data.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def fallback_assessment():
    return {
        "threat_level": "STABLE",
        "sentiment_score": 20,
        "security_status_cs": "Za posledních 24h nebyly zachyceny žádné nové zásadní události v regionu (Izrael/Gaza, Írán, Sýrie, Libanon, Irák).",
        "security_status_en": "No significant new developments were detected in the region (Israel/Gaza, Iran, Syria, Lebanon, Iraq) in the last 24 hours.",
        "recommendations": [
            {"sector_cs": "Obranný průmysl (Elbit Systems, RTX, Lockheed Martin)", "sector_en": "Defense Industry (Elbit Systems, RTX, Lockheed Martin)", "action": "HOLD",
             "reason_cs": "Bez nových impulzů zůstávají zakázky stabilní.", "reason_en": "Without new triggers, order volume remains stable."},
            {"sector_cs": "Ropa a plyn (Chevron, ExxonMobil)", "sector_en": "Oil & Gas (Chevron, ExxonMobil)", "action": "HOLD",
             "reason_cs": "Ceny ropy jsou bez výrazných výkyvů.", "reason_en": "Oil prices show no major swings."},
            {"sector_cs": "Izraelské akcie (Tel Aviv 35)", "sector_en": "Israeli Equities (Tel Aviv 35)", "action": "HOLD",
             "reason_cs": "Trh je bez nových geopolitických impulzů stabilní.", "reason_en": "The market remains stable without new geopolitical triggers."},
            {"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "HOLD",
             "reason_cs": "Bez přímého dopadu z regionu zůstávají české tituly stabilní.", "reason_en": "Without direct regional spillover, Czech equities remain stable."}
        ],
        "forecast_cs": "Bez nových dat nelze aktualizovat výhled.",
        "forecast_en": "No updated outlook without new data.",
        "forecast_review_cs": "Žádná předchozí předpověď k vyhodnocení.",
        "forecast_review_en": "No previous forecast to evaluate."
    }


def analyze_with_ai(articles, previous_forecast_cs, previous_forecast_en):
    if not articles:
        return fallback_assessment()

    news_text = "\n".join([f"- {a['title']}: {a['summary']}" for a in articles])
    prev_cs = previous_forecast_cs or "Žádná předchozí předpověď."
    prev_en = previous_forecast_en or "No previous forecast."

    prompt = f"""
    You are a top-tier portfolio manager and security analyst covering the Middle East, specifically Israel/Gaza, Iran, Syria, Lebanon, and Iraq. Do NOT cover Yemen, the Houthis, or the Red Sea/Bab-el-Mandeb shipping situation - that is tracked by a separate dedicated monitor. Based on the following news from the last 24 hours, produce an analytical overview and investment recommendations in BOTH Czech and English.

    News:
    {news_text}

    Previous forecast, Czech (from the last run, for review purposes):
    "{prev_cs}"

    Previous forecast, English (from the last run, for review purposes):
    "{prev_en}"

    Return the response STRICTLY AS VALID JSON with no introductory text or markdown formatting. Provide every text field in both languages using the _cs and _en suffixes as shown. Keep threat_level and action as the exact English enum values shown (do not translate them):
    {{
        "threat_level": "CRITICAL / HIGH / MEDIUM / STABLE",
        "sentiment_score": <integer 0-100, where 0 = completely calm situation, 100 = extreme crisis>,
        "security_status_cs": "2-3 věty o aktuálním bezpečnostním vývoji v regionu (Izrael/Gaza, Írán, Sýrie, Libanon, Irák), česky.",
        "security_status_en": "2-3 sentences on the current security developments in the region (Israel/Gaza, Iran, Syria, Lebanon, Iraq), in English.",
        "recommendations": [
            {{"sector_cs": "Obranný průmysl (Elbit Systems, RTX, Lockheed Martin)", "sector_en": "Defense Industry (Elbit Systems, RTX, Lockheed Martin)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění.", "reason_en": "1-2 sentences of reasoning."}},
            {{"sector_cs": "Ropa a plyn (Chevron, ExxonMobil)", "sector_en": "Oil & Gas (Chevron, ExxonMobil)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně cen ropy.", "reason_en": "1-2 sentences regarding oil prices."}},
            {{"sector_cs": "Izraelské akcie (Tel Aviv 35)", "sector_en": "Israeli Equities (Tel Aviv 35)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně bezpečnostní situace a ekonomiky.", "reason_en": "1-2 sentences regarding the security situation and economy."}},
            {{"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění dopadu regionálního dění na tyto tři tituly.", "reason_en": "1-2 sentences on how regional developments affect these three stocks."}}
        ],
        "forecast_cs": "1-2 věty odhadu vývoje na nejbližší dny, česky.",
        "forecast_en": "1-2 sentences forecasting developments over the coming days, in English.",
        "forecast_review_cs": "1 věta česky - potvrdila se, nebo vyvrátila předchozí předpověď na základě dnešních zpráv? Pokud žádná nebyla, napiš 'Žádná předchozí předpověď k vyhodnocení.'",
        "forecast_review_en": "1 sentence in English - did today's news confirm or contradict the previous forecast? If there was none, write 'No previous forecast to evaluate.'"
    }}
    """

    response = client.models.generate_content(model='gemini-3.5-flash-lite', contents=prompt)

    try:
        clean_json = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean_json)
        parsed["threat_level"] = str(parsed.get("threat_level", "HIGH")).split(" ")[0].split("/")[0].strip().upper()
        for rec in parsed.get("recommendations", []):
            rec["action"] = str(rec.get("action", "HOLD")).split(" ")[0].split("/")[0].strip().upper()
        return parsed
    except Exception as e:
        print("Error processing AI response:", e)
        return {
            "threat_level": "HIGH",
            "sentiment_score": 70,
            "security_status_cs": "Chyba při automatické analýze AI.",
            "security_status_en": "Error during automated AI analysis.",
            "recommendations": [],
            "forecast_cs": "Nepodařilo se vygenerovat předpověď.",
            "forecast_en": "Failed to generate forecast.",
            "forecast_review_cs": "N/A",
            "forecast_review_en": "N/A"
        }


def send_ntfy_alert(threat_level, status_text):
    if not NTFY_TOPIC:
        return
    try:
        req = urllib.request.Request(
            url=f"https://ntfy.sh/{NTFY_TOPIC}",
            data=status_text.encode("utf-8"),
            headers={
                "Title": f"Middle East Monitor: {threat_level}".encode("utf-8"),
                "Priority": "urgent",
                "Tags": "warning"
            },
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("Error sending ntfy notification:", e)


def build_rss(articles):
    items = ""
    for a in articles:
        items += f"""
        <item>
            <title>{escape(a['title'])}</title>
            <link>{escape(a['link'])}</link>
            <description>{escape(a['summary'])}</description>
            <pubDate>{escape(a['published'])}</pubDate>
        </item>"""
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>Middle East AI Monitor</title>
    <link>https://matesva.github.io/Redsea-monitor/middle-east/</link>
    <description>AI monitoring of Israel/Gaza, Iran, Syria, Lebanon and Iraq developments</description>
    {items}
</channel>
</rss>"""
    os.makedirs("middle-east", exist_ok=True)
    with open("middle-east/rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)


def build_weekly_summary(archive):
    if not archive:
        return {
            "cs": "Zatím není dostatek dat pro týdenní shrnutí.",
            "en": "Not enough data yet for a weekly summary."
        }
    last7 = archive[-7:]
    counts = {}
    for entry in last7:
        lvl = entry.get("threat_level", "UNKNOWN")
        counts[lvl] = counts.get(lvl, 0) + 1
    parts = [f"{v}× {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    days = len(last7)
    joined = ", ".join(parts)
    return {
        "cs": f"Za posledních {days} zaznamenaných analýz: {joined}.",
        "en": f"Over the last {days} recorded analyses: {joined}."
    }


def update_location_counts(previous_counts, locations):
    counts = dict(previous_counts or {})
    for loc in locations:
        key = loc["key"]
        counts[key] = counts.get(key, 0) + 1
    return counts


def top_location(location_counts):
    if not location_counts:
        return None
    top_key = max(location_counts, key=location_counts.get)
    loc_info = LOCATIONS.get(top_key, {})
    return {
        "key": top_key,
        "name_cs": loc_info.get("name_cs", top_key),
        "name_en": loc_info.get("name_en", top_key),
        "count": location_counts[top_key]
    }


def run():
    old_data = load_previous_data()
    previous_forecast_cs = old_data.get("assessment", {}).get("forecast_cs", "")
    previous_forecast_en = old_data.get("assessment", {}).get("forecast_en", "")
    previous_market = old_data.get("market_data")
    previous_location_counts = old_data.get("location_counts", {})

    articles = fetch_articles()
    ai_assessment = analyze_with_ai(articles, previous_forecast_cs, previous_forecast_en)
    locations = extract_locations(articles)
    market_data = fetch_market_data(previous_market)
    usd_czk = fetch_usd_czk()
    location_counts = update_location_counts(previous_location_counts, locations)

    history = old_data.get("history", [])
    threat_key = ai_assessment.get("threat_level", "HIGH")
    threat_value = THREAT_MAP.get(threat_key, 1)
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%d %H:%M")

    history.append({
        "date": now_str,
        "threat_level": threat_key,
        "value": threat_value,
        "sentiment_score": ai_assessment.get("sentiment_score", 0),
        "incidents": len(articles),
        "brent": market_data.get("brent", {}).get("value") if market_data.get("brent") else None,
        "usd_czk": usd_czk.get("value") if usd_czk else None
    })
    history = history[-30:]

    archive = old_data.get("archive", [])
    archive.append({
        "date": now_str,
        "threat_level": threat_key,
        "security_status_cs": ai_assessment.get("security_status_cs", ""),
        "security_status_en": ai_assessment.get("security_status_en", ""),
        "forecast_cs": ai_assessment.get("forecast_cs", ""),
        "forecast_en": ai_assessment.get("forecast_en", "")
    })
    archive = archive[-14:]

    weekly_summary = build_weekly_summary(archive)
    top_loc = top_location(location_counts)

    data = {
        "last_updated": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assessment": ai_assessment,
        "articles": articles,
        "history": history,
        "locations": locations,
        "location_counts": location_counts,
        "top_location": top_loc,
        "archive": archive,
        "weekly_summary_cs": weekly_summary["cs"],
        "weekly_summary_en": weekly_summary["en"],
        "market_data": market_data,
        "usd_czk": usd_czk
    }

    os.makedirs("middle-east", exist_ok=True)
    with open("middle-east/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_rss(articles)

    if threat_key == "CRITICAL":
        status_for_alert = ai_assessment.get("security_status_en", "")
        send_ntfy_alert(threat_key, status_for_alert)


if __name__ == "__main__":
    run()

