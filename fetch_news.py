import feedparser
import json
import os
import urllib.request
import html
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://search.cnbc.com/rs/search/combinedrenderer.view?query=red%20sea%20houthi&partnerId=2000&target=all",
    "https://www.theguardian.com/world/rss",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://english.alarabiya.net/.mrss/en.xml",
    "https://www.middleeasteye.net/rss",
    "https://gcaptain.com/feed/",
    "https://splash247.com/feed/",
    "https://oilprice.com/rss/main",
    "https://www.reuters.com/world/middle-east/rss",
    "https://apnews.com/hub/middle-east?output=rss",
    "https://www.timesofisrael.com/feed/",
    "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
    "https://www.navalnews.com/feed/",
    "https://www.defensenews.com/arc/outboundfeeds/rss/",
    "https://www.maritime-executive.com/rss/all",
    "https://www.hellenicshippingnews.com/feed/",
    "https://www.zawya.com/en/rss",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
]

KEYWORDS = ["Houthi", "Red Sea", "Yemen", "Bab-el-Mandeb", "Húthí", "shipping", "oil"]
THREAT_MAP = {"STABLE": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

LOCATIONS = {
    "Yemen": {"lat": 15.5527, "lon": 48.5164, "name_cs": "Jemen", "name_en": "Yemen"},
    "Red Sea": {"lat": 20.5, "lon": 38.0, "name_cs": "Rudé moře", "name_en": "Red Sea"},
    "Bab-el-Mandeb": {"lat": 12.5964, "lon": 43.3311, "name_cs": "Bab-el-Mandeb", "name_en": "Bab-el-Mandeb"},
    "Hormuz": {"lat": 26.5667, "lon": 56.25, "name_cs": "Hormuzský průliv", "name_en": "Strait of Hormuz"},
    "Suez": {"lat": 30.5852, "lon": 32.2654, "name_cs": "Suezský průplav", "name_en": "Suez Canal"},
    "Mecca": {"lat": 21.3891, "lon": 39.8579, "name_cs": "Mekka", "name_en": "Mecca"},
    "Saudi Arabia": {"lat": 23.8859, "lon": 45.0792, "name_cs": "Saúdská Arábie", "name_en": "Saudi Arabia"},
    "Oman": {"lat": 21.4735, "lon": 55.9754, "name_cs": "Omán", "name_en": "Oman"},
    "Mokha": {"lat": 13.3167, "lon": 43.25, "name_cs": "Mokha", "name_en": "Mokha"},
    "Iraq": {"lat": 33.2232, "lon": 43.6793, "name_cs": "Irák", "name_en": "Iraq"},
}


def fetch_articles():
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                title = html.unescape(entry.get("title", ""))
                summary = html.unescape(entry.get("summary", ""))
                if any(kw.lower() in (title + summary).lower() for kw in KEYWORDS):
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


def fetch_yahoo_price(symbol):
    """Stáhne poslední cenu futures kontraktu z Yahoo Finance (BZ=F pro Brent, CL=F pro WTI)."""
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
        raise ValueError(f"Yahoo Finance nevrátil data pro {symbol}")

    result_data = chart_result[0]
    meta = result_data.get("meta", {})

    price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
    timestamp = meta.get("regularMarketTime")

    if price is None:
        raise ValueError(f"Chybí cena v odpovědi pro {symbol}")

    if timestamp:
        date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {"value": round(float(price), 2), "date": date_str, "cached": False}


def fetch_oil_prices(previous_prices):
    prices = {"brent": None, "wti": None}
    symbols = {"brent": "BZ=F", "wti": "CL=F"}

    for label, symbol in symbols.items():
        try:
            prices[label] = fetch_yahoo_price(symbol)
        except Exception as e:
            print(f"Chyba při stahování ceny {label} (Yahoo Finance): {e}")

    if previous_prices:
        for label in ["brent", "wti"]:
            if not prices.get(label) and previous_prices.get(label):
                cached = dict(previous_prices[label])
                cached["cached"] = True
                prices[label] = cached

    return prices


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
        print(f"Chyba při stahování kurzu USD/CZK: {e}")
    return None


def load_previous_data():
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def fallback_assessment():
    return {
        "threat_level": "STABLE",
        "sentiment_score": 20,
        "security_status_cs": "Za posledních 24h nebyly zachyceny žádné nové zásadní události.",
        "security_status_en": "No significant new developments were detected in the last 24 hours.",
        "recommendations": [
            {"sector_cs": "Námořní doprava", "sector_en": "Maritime Shipping", "action": "HOLD",
             "reason_cs": "Ceny přepravy jsou stabilizované.", "reason_en": "Freight rates remain stable."},
            {"sector_cs": "Obranný průmysl", "sector_en": "Defense Industry", "action": "BUY",
             "reason_cs": "Trvalé geopolitické napětí udrží zakázky.", "reason_en": "Persistent geopolitical tension will sustain orders."},
            {"sector_cs": "Energetika a Ropa", "sector_en": "Energy & Oil", "action": "HOLD",
             "reason_cs": "Ropné trhy vykazují vyrovnanou nabídku a poptávku.", "reason_en": "Oil markets show balanced supply and demand."},
            {"sector_cs": "Spotřební sektor & Auto", "sector_en": "Consumer Sector & Automotive", "action": "SELL",
             "reason_cs": "Riziko zpoždění v dodavatelských řetězcích trvá.", "reason_en": "Supply chain delay risk persists."},
            {"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "HOLD",
             "reason_cs": "Bez nových geopolitických impulzů zůstávají české tituly stabilní.", "reason_en": "Without new geopolitical triggers, Czech equities remain stable."},
            {"sector_cs": "Evropské blue-chips (např. Airbus, TotalEnergies, Allianz, Rheinmetall)", "sector_en": "European blue-chips (e.g. Airbus, TotalEnergies, Allianz, Rheinmetall)", "action": "HOLD",
             "reason_cs": "Bez nových impulzů zůstávají evropské tituly stabilní.", "reason_en": "Without new triggers, European equities remain stable."}
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
    You are a top-tier portfolio manager and security analyst. Based on the following news from the last 24 hours about the Houthis and the Red Sea, produce an analytical overview and investment recommendations in BOTH Czech and English.

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
        "security_status_cs": "2-3 věty o aktuálním bezpečnostním vývoji v Rudém moři, česky.",
        "security_status_en": "2-3 sentences on the current security developments in the Red Sea, in English.",
        "recommendations": [
            {{"sector_cs": "Námořní doprava (např. Maersk, Hapag-Lloyd, ZIM)", "sector_en": "Maritime Shipping (e.g. Maersk, Hapag-Lloyd, ZIM)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty česky.", "reason_en": "1-2 sentences in English."}},
            {{"sector_cs": "Obranný průmysl (např. RTX, Lockheed Martin, BAE Systems)", "sector_en": "Defense Industry (e.g. RTX, Lockheed Martin, BAE Systems)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty česky.", "reason_en": "1-2 sentences in English."}},
            {{"sector_cs": "Ropa a Plyn (např. Shell, BP, Chevron)", "sector_en": "Oil & Gas (e.g. Shell, BP, Chevron)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty česky.", "reason_en": "1-2 sentences in English."}},
            {{"sector_cs": "Evropský Spotřební sektor & Autoprůmysl (např. Volvo, BMW)", "sector_en": "European Consumer & Automotive (e.g. Volvo, BMW)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty česky.", "reason_en": "1-2 sentences in English."}},
            {{"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty česky.", "reason_en": "1-2 sentences in English."}},
            {{"sector_cs": "Evropské blue-chips (např. Airbus, TotalEnergies, Allianz, Rheinmetall)", "sector_en": "European blue-chips (e.g. Airbus, TotalEnergies, Allianz, Rheinmetall)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty česky.", "reason_en": "1-2 sentences in English."}}
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
                "Title": f"Red Sea Monitor: {threat_level}".encode("utf-8"),
                "Priority": "urgent",
                "Tags": "warning"
            },
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print("Chyba při odesílání ntfy notifikace:", e)


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
    <title>Red Sea AI Monitor</title>
    <link>https://matesva.github.io/Redsea-monitor/</link>
    <description>AI monitoring of the security situation in the Red Sea</description>
    {items}
</channel>
</rss>"""
    with open("rss.xml", "w", encoding="utf-8") as f:
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
    previous_oil = old_data.get("oil_prices")
    previous_location_counts = old_data.get("location_counts", {})

    articles = fetch_articles()
    ai_assessment = analyze_with_ai(articles, previous_forecast_cs, previous_forecast_en)
    locations = extract_locations(articles)
    oil_prices = fetch_oil_prices(previous_oil)
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
        "brent": oil_prices.get("brent", {}).get("value") if oil_prices.get("brent") else None,
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
        "oil_prices": oil_prices,
        "usd_czk": usd_czk
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_rss(articles)

    if threat_key == "CRITICAL":
        status_for_alert = ai_assessment.get("security_status_en", "")
        send_ntfy_alert(threat_key, status_for_alert)


if __name__ == "__main__":
    run()
