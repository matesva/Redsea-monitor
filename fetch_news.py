import feedparser
import json
import os
import urllib.request
import html
from datetime import datetime
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
THREAT_MAP = {"STABILNÍ": 1, "STŘEDNÍ": 2, "VYSOKÁ": 3, "KRITICKÁ": 4}

LOCATIONS = {
    "Yemen": {"lat": 15.5527, "lon": 48.5164, "name": "Jemen"},
    "Red Sea": {"lat": 20.5, "lon": 38.0, "name": "Rudé moře"},
    "Bab-el-Mandeb": {"lat": 12.5964, "lon": 43.3311, "name": "Bab-el-Mandeb"},
    "Hormuz": {"lat": 26.5667, "lon": 56.25, "name": "Hormuzský průliv"},
    "Suez": {"lat": 30.5852, "lon": 32.2654, "name": "Suezský průplav"},
    "Mecca": {"lat": 21.3891, "lon": 39.8579, "name": "Mekka"},
    "Saudi Arabia": {"lat": 23.8859, "lon": 45.0792, "name": "Saúdská Arábie"},
    "Oman": {"lat": 21.4735, "lon": 55.9754, "name": "Omán"},
    "Mokha": {"lat": 13.3167, "lon": 43.25, "name": "Mokha"},
    "Iraq": {"lat": 33.2232, "lon": 43.6793, "name": "Irák"},
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
                        "published": entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "source": feed.feed.get("title", "Zpravodajství")
                    })
        except Exception as e:
            print(f"Chyba při zpracování feedu {feed_url}: {e}")
            continue
    return articles[:20]


def extract_locations(articles):
    found = {}
    text_blob = " ".join([a['title'] + " " + a['summary'] for a in articles])
    for key, loc in LOCATIONS.items():
        if key.lower() in text_blob.lower():
            found[key] = loc
    return list(found.values())


def fetch_yahoo_price(symbol):
    """Stáhne poslední cenu futures kontraktu z Yahoo Finance (bez API klíče)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())

    chart_result = result.get("chart", {}).get("result")
    if not chart_result:
        raise ValueError(f"Yahoo Finance nevrátil data pro {symbol}")

    result_data = chart_result[0]
    meta = result_data.get("meta", {})
    price = meta.get("regularMarketPrice")
    timestamp = meta.get("regularMarketTime")

    if price is None:
        raise ValueError(f"Chybí cena v odpovědi pro {symbol}")

    if timestamp:
        date_str = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    return {"value": round(float(price), 2), "date": date_str, "cached": False}


def fetch_oil_prices(previous_prices):
    prices = {"brent": None, "wti": None}
    symbols = {"brent": "BZ=F", "wti": "CL=F"}

    for label, symbol in symbols.items():
        try:
            prices[label] = fetch_yahoo_price(symbol)
        except Exception as e:
            print(f"Chyba při stahování ceny {label} (Yahoo Finance): {e}")

    # Fallback na poslední známou hodnotu, pokud aktuální dotaz selhal
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
            result = json.loads(resp.read().decode())
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


def analyze_with_ai(articles, previous_forecast):
    if not articles:
        return {
            "threat_level": "STABILNÍ / BEZ ZMĚN",
            "sentiment_score": 20,
            "security_status": "Za posledních 24h nebyly zachyceny žádné nové zásadní události.",
            "recommendations": [
                {"sector": "Námořní doprava", "action": "DRŽET", "reason": "Ceny přepravy jsou stabilizované."},
                {"sector": "Obranný průmysl", "action": "KOUPIT", "reason": "Trvalé geopolitické napětí udrží zakázky."},
                {"sector": "Energetika a Ropa", "action": "DRŽET", "reason": "Ropné trhy vykazují vyrovnanou nabídku a poptávku."},
                {"sector": "Spotřební sektor & Auto", "action": "PRODAT", "reason": "Riziko zpoždění v dodavatelských řetězcích trvá."},
                {"sector": "Pražská burza: ČEZ, Komerční banka, Erste Group", "action": "DRŽET", "reason": "Bez nových geopolitických impulzů zůstávají české tituly stabilní."},
                {"sector": "Evropské blue-chips (např. Airbus, TotalEnergies, Allianz, Rheinmetall)", "action": "DRŽET", "reason": "Bez nových impulzů zůstávají evropské tituly stabilní."}
            ],
            "forecast": "Bez nových dat nelze aktualizovat výhled.",
            "forecast_review": "Žádná předchozí předpověď k vyhodnocení."
        }

    news_text = "\n".join([f"- {a['title']}: {a['summary']}" for a in articles])
    prev_forecast_text = previous_forecast or "Žádná předchozí předpověď."

    prompt = f"""
    Jsi špičkový portfoliový manažer a bezpečnostní analytik. Na základě následujících zpráv za posledních 24 hodin o Húthíích a Rudém moři vytvoř analytický přehled a investiční doporučení v češtině.

    Zprávy:
    {news_text}

    Předchozí předpověď (z minulého běhu, pro zpětné vyhodnocení):
    "{prev_forecast_text}"

    Vrať ODPOVĚĎ VÝHRADNĚ JAKO PLATNÝ JSON kód bez jakýchkoliv úvodních textů nebo markdownových značek:
    {{
        "threat_level": "KRITICKÁ / VYSOKÁ / STŘEDNÍ",
        "sentiment_score": <celé číslo 0-100, kde 0 = naprosto klidná situace, 100 = extrémní krize>,
        "security_status": "2-3 věty o aktuálním bezpečnostním vývoji v Rudém moři.",
        "recommendations": [
            {{"sector": "Námořní doprava (např. Maersk, Hapag-Lloyd, ZIM)", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění na základě sazeb a rizik."}},
            {{"sector": "Obranný průmysl (např. RTX, Lockheed Martin, BAE Systems)", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění na základě zakázek."}},
            {{"sector": "Ropa a Plyn (např. Shell, BP, Chevron)", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění ohledně cen ropy."}},
            {{"sector": "Evropský Spotřební sektor & Autoprůmysl (např. Volvo, BMW)", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění k logistice."}},
            {{"sector": "Pražská burza: ČEZ, Komerční banka, Erste Group", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění pro tyto tři tituly."}},
            {{"sector": "Evropské blue-chips (např. Airbus, TotalEnergies, Allianz, Rheinmetall)", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění dopadu na širší evropské tituly - obrana, energetika, pojišťovnictví."}}
        ],
        "forecast": "1-2 věty odhadu vývoje na nejbližší dny.",
        "forecast_review": "1 věta - potvrdila se, nebo vyvrátila předchozí předpověď na základě dnešních zpráv? Pokud žádná nebyla, napiš 'Žádná předchozí předpověď k vyhodnocení.'"
    }}
    """

    response = client.models.generate_content(model='gemini-3.5-flash-lite', contents=prompt)

    try:
        clean_json = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean_json)
    except Exception as e:
        print("Chyba při zpracování AI odpovědi:", e)
        return {
            "threat_level": "VYSOKÁ",
            "sentiment_score": 70,
            "security_status": "Chyba při automatické analýze AI.",
            "recommendations": [],
            "forecast": "Nepodařilo se vygenerovat předpověď.",
            "forecast_review": "N/A"
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
    <description>AI monitoring bezpečnostní situace v Rudém moři</description>
    {items}
</channel>
</rss>"""
    with open("rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)


def build_weekly_summary(archive):
    if not archive:
        return "Zatím není dostatek dat pro týdenní shrnutí."
    last7 = archive[-7:]
    counts = {}
    for entry in last7:
        lvl = entry.get("threat_level", "NEZNÁMÁ")
        counts[lvl] = counts.get(lvl, 0) + 1
    parts = [f"{v}× {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    days = len(last7)
    return f"Za posledních {days} zaznamenaných analýz: " + ", ".join(parts) + "."


def update_location_counts(previous_counts, locations):
    counts = dict(previous_counts or {})
    for loc in locations:
        name = loc["name"]
        counts[name] = counts.get(name, 0) + 1
    return counts


def top_location(location_counts):
    if not location_counts:
        return None
    top_name = max(location_counts, key=location_counts.get)
    return {"name": top_name, "count": location_counts[top_name]}


def run():
    old_data = load_previous_data()
    previous_forecast = old_data.get("assessment", {}).get("forecast", "")
    previous_oil = old_data.get("oil_prices")
    previous_location_counts = old_data.get("location_counts", {})

    articles = fetch_articles()
    ai_assessment = analyze_with_ai(articles, previous_forecast)
    locations = extract_locations(articles)
    oil_prices = fetch_oil_prices(previous_oil)
    usd_czk = fetch_usd_czk()
    location_counts = update_location_counts(previous_location_counts, locations)

    history = old_data.get("history", [])
    threat_key = ai_assessment.get("threat_level", "").split(" ")[0].split("/")[0].strip()
    threat_value = THREAT_MAP.get(threat_key, 1)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

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
        "security_status": ai_assessment.get("security_status", ""),
        "forecast": ai_assessment.get("forecast", "")
    })
    archive = archive[-14:]

    weekly_summary = build_weekly_summary(archive)
    top_loc = top_location(location_counts)

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "assessment": ai_assessment,
        "articles": articles,
        "history": history,
        "locations": locations,
        "location_counts": location_counts,
        "top_location": top_loc,
        "archive": archive,
        "weekly_summary": weekly_summary,
        "oil_prices": oil_prices,
        "usd_czk": usd_czk
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_rss(articles)

    if threat_key == "KRITICKÁ":
        send_ntfy_alert(threat_key, ai_assessment.get("security_status", ""))


if __name__ == "__main__":
    run()
