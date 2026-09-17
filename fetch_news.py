import feedparser
import json
import os
import urllib.request
from datetime import datetime
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY")

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
                title = entry.get("title", "")
                summary = entry.get("summary", "")
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


def fetch_oil_prices():
    prices = {"brent": None, "wti": None}
    if not ALPHA_VANTAGE_KEY:
        return prices
    for label, function in [("brent", "BRENT"), ("wti", "WTI")]:
        try:
            url = f"https://www.alphavantage.co/query?function={function}&interval=daily&apikey={ALPHA_VANTAGE_KEY}"
            with urllib.request.urlopen(url, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                data_points = result.get("data", [])
                if data_points:
                    prices[label] = {
                        "value": float(data_points[0]["value"]),
                        "date": data_points[0]["date"]
                    }
        except Exception as e:
            print(f"Chyba při stahování ceny {label}: {e}")
    return prices


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
                {"sector": "Pražská burza: ČEZ, Komerční banka, Erste Group", "action": "DRŽET", "reason": "Bez nových geopolitických impulzů zůstávají české tituly stabilní."}
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
            {{"sector": "Pražská burza: ČEZ, Komerční banka, Erste Group", "action": "KOUPIT / PRODAT / DRŽET", "reason": "1-2 věty zdůvodnění pro tyto tři tituly."}}
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
            <title>{a['title']}</title>
            <link>{a['link']}</link>
            <description>{a['summary']}</description>
            <pubDate>{a['published']}</pubDate>
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


def run():
    old_data = load_previous_data()
    previous_forecast = old_data.get("assessment", {}).get("forecast", "")

    articles = fetch_articles()
    ai_assessment = analyze_with_ai(articles, previous_forecast)
    locations = extract_locations(articles)
    oil_prices = fetch_oil_prices()

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
        "brent": oil_prices.get("brent", {}).get("value") if oil_prices.get("brent") else None
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

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "assessment": ai_assessment,
        "articles": articles,
        "history": history,
        "locations": locations,
        "archive": archive,
        "oil_prices": oil_prices
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_rss(articles)

    if threat_key == "KRITICKÁ":
        send_ntfy_alert(threat_key, ai_assessment.get("security_status", ""))


if __name__ == "__main__":
    run()
