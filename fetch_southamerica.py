import feedparser
import json
import os
import re
import calendar
import urllib.request
import html
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
NTFY_TOPIC = os.environ.get("NTFY_TOPIC_SOUTHAMERICA") or os.environ.get("NTFY_TOPIC")

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml",
    "https://www.theguardian.com/world/americas/rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.france24.com/en/americas/rss",
    "https://apnews.com/hub/latin-america?output=rss",
    "https://en.mercopress.com/rss",
    "https://www.batimes.com.ar/feed",
    "https://www.riotimesonline.com/feed/",
    "https://www.americasquarterly.org/feed/",
    "https://insightcrime.org/feed/",
    "https://www.latinamericareports.com/feed/",
    "https://feeds.npr.org/1004/rss.xml",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",
]

# Kolik nejnovějších článků se bere z jednoho feedu a kolik jich je celkem.
# Články se vybírají střídavě z každého feedu, aby nepřevážily první zdroje.
PER_FEED_MAX = 4
MAX_ARTICLES = 40

SOURCE_NAMES = {
    "bbci.co.uk": "BBC News",
    "bbc.co.uk": "BBC News",
    "theguardian.com": "The Guardian",
    "aljazeera.com": "Al Jazeera",
    "france24.com": "France 24",
    "apnews.com": "AP News",
    "mercopress.com": "MercoPress",
    "batimes.com.ar": "Buenos Aires Times",
    "riotimesonline.com": "The Rio Times",
    "americasquarterly.org": "Americas Quarterly",
    "insightcrime.org": "InSight Crime",
    "latinamericareports.com": "Latin America Reports",
    "npr.org": "NPR",
    "marketwatch.com": "MarketWatch",
    "dj.com": "WSJ Markets",
    "cnbc.com": "CNBC",
}

KEYWORDS = [
    "Brazil", "Brazilian", "Lula", "Bolsonaro", "Argentina", "Milei", "Chile",
    "Colombia", "Petro", "Venezuela", "Maduro", "Peru", "Ecuador", "Bolivia",
    "Paraguay", "Uruguay", "Guyana", "Suriname", "Mercosur", "Amazon",
    "Latin America", "South America", "lithium", "copper", "Petrobras", "Vale ",
    "peso", "election", "runoff", "protest", "coup", "cartel", "gang", "drug",
    "inflation", "central bank", "tariff", "oil", "mining", "wildfire",
    "drought", "Falkland", "Andes", "soy", "coffee", "beef", "currency"
]

THREAT_MAP = {"STABLE": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

def _loc(lat, lon, cs, en=None, terms=None):
    return {"lat": lat, "lon": lon, "name_cs": cs, "name_en": en or cs, "terms": terms}

LOCATIONS = {
    "Brasilia": _loc(-15.7939, -47.8828, "Brasília", "Brasília", ["brasilia", "brasília", "brazil", "brazilian", "lula", "bolsonaro", "planalto"]),
    "Sao Paulo": _loc(-23.5505, -46.6333, "São Paulo", "São Paulo", ["sao paulo", "são paulo", "bovespa", "b3", "petrobras", "itau", "itaú"]),
    "Rio de Janeiro": _loc(-22.9068, -43.1729, "Rio de Janeiro", "Rio de Janeiro", ["rio de janeiro"]),
    "Buenos Aires": _loc(-34.6037, -58.3816, "Buenos Aires", "Buenos Aires", ["buenos aires", "argentina", "argentine", "argentinian", "milei", "merval"]),
    "Santiago": _loc(-33.4489, -70.6693, "Santiago", "Santiago", ["santiago", "chile", "chilean", "boric", "kast"]),
    "Lima": _loc(-12.0464, -77.0428, "Lima", "Lima", ["lima", "peru", "peruvian"]),
    "Bogota": _loc(4.7110, -74.0721, "Bogotá", "Bogotá", ["bogota", "bogotá", "colombia", "colombian", "petro"]),
    "Caracas": _loc(10.4806, -66.9036, "Caracas", "Caracas", ["caracas", "venezuela", "venezuelan", "maduro"]),
    "Quito": _loc(-0.1807, -78.4678, "Quito", "Quito", ["quito", "ecuador", "ecuadorian", "noboa", "guayaquil"]),
    "La Paz": _loc(-16.4897, -68.1193, "La Paz", "La Paz", ["la paz", "bolivia", "bolivian", "santa cruz"]),
    "Asuncion": _loc(-25.2637, -57.5759, "Asunción", "Asunción", ["asuncion", "asunción", "paraguay", "paraguayan"]),
    "Montevideo": _loc(-34.9011, -56.1645, "Montevideo", "Montevideo", ["montevideo", "uruguay", "uruguayan"]),
    "Georgetown": _loc(6.8013, -58.1551, "Georgetown", "Georgetown", ["georgetown", "guyana", "guyanese", "essequibo"]),
    "Paramaribo": _loc(5.8520, -55.2038, "Paramaribo", "Paramaribo", ["paramaribo", "suriname"]),
    "Medellin": _loc(6.2442, -75.5812, "Medellín", "Medellín", ["medellin", "medellín"]),
    "Amazon": _loc(-3.4653, -62.2159, "Amazonie", "Amazon", ["amazon", "amazonia", "manaus", "rainforest"]),
    "Atacama": _loc(-23.65, -68.2, "Poušť Atacama (lithium)", "Atacama (lithium)", ["atacama", "lithium triangle", "lithium"]),
    "Patagonia": _loc(-41.8, -68.9, "Patagonie", "Patagonia", ["patagonia", "vaca muerta", "neuquen", "neuquén"]),
    "Falklands": _loc(-51.7963, -59.5236, "Falklandy", "Falkland Islands", ["falkland", "malvinas"]),
    "Panama": _loc(8.9824, -79.5199, "Panama", "Panama", ["panama"]),
    "Cuba": _loc(23.1136, -82.3666, "Havana", "Havana", ["cuba", "cuban", "havana"]),
    "Washington": _loc(38.9072, -77.0369, "Washington, D.C.", "Washington, D.C.", ["washington", "white house", "trump", "imf"]),
    "Beijing": _loc(39.9042, 116.4074, "Peking", "Beijing", ["beijing", "china", "chinese"]),
}


def source_name(feed_url, fallback):
    host = re.sub(r"^https?://", "", feed_url).split("/")[0].lower()
    for domain, name in SOURCE_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return fallback


def entry_ts(entry):
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    try:
        return calendar.timegm(t) if t else 0
    except Exception:
        return 0


def fetch_articles():
    per_feed = []
    for feed_url in RSS_FEEDS:
        items = []
        name = source_name(feed_url, "News")
        try:
            feed = feedparser.parse(feed_url)
            name = source_name(feed_url, feed.feed.get("title", "News"))
            for entry in sorted(feed.entries, key=entry_ts, reverse=True):
                title = html.unescape(entry.get("title", ""))
                summary = html.unescape(entry.get("summary", ""))
                if any(kw.lower() in (title + summary).lower() for kw in KEYWORDS):
                    items.append({
                        "title": title,
                        "summary": summary,
                        "link": entry.get("link", "#"),
                        "published": entry.get("published", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
                        "source": name,
                        "_ts": entry_ts(entry)
                    })
                    if len(items) >= PER_FEED_MAX:
                        break
        except Exception as e:
            print(f"Error processing feed {feed_url}: {e}")
        print(f"Feed {name}: {len(items)} článků")
        per_feed.append(items)

    # Střídavý výběr: z každého feedu 1. článek, pak 2. atd., bez duplicit.
    result, seen_links, seen_titles = [], set(), set()
    idx = 0
    while len(result) < MAX_ARTICLES and any(idx < len(x) for x in per_feed):
        for items in per_feed:
            if idx >= len(items) or len(result) >= MAX_ARTICLES:
                continue
            a = items[idx]
            tkey = re.sub(r"\W+", " ", a["title"].lower()).strip()
            if a["link"] in seen_links or tkey in seen_titles:
                continue
            seen_links.add(a["link"])
            seen_titles.add(tkey)
            result.append(a)
        idx += 1

    result.sort(key=lambda a: a["_ts"], reverse=True)
    for a in result:
        a.pop("_ts", None)
    return result


def extract_locations(articles):
    found = {}
    text_blob = " ".join([a['title'] + " " + a['summary'] for a in articles]).lower()
    for key, loc in LOCATIONS.items():
        terms = loc.get("terms") or [key.lower()]
        if any(re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", text_blob) for t in terms):
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

    return {"value": round(float(price) / divisor, 4 if divisor == 1 and price < 10 else 2), "date": date_str, "cached": False}


def fetch_market_data(previous):
    data = {"bovespa": None, "merval": None, "usdbrl": None}
    symbols = {"bovespa": ("^BVSP", 1), "merval": ("^MERV", 1), "usdbrl": ("BRL=X", 1)}

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


def fetch_brl_czk():
    try:
        url = "https://api.frankfurter.app/latest?from=BRL&to=CZK"
        with urllib.request.urlopen(url, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            rate = result.get("rates", {}).get("CZK")
            date = result.get("date")
            if rate:
                return {"value": round(rate, 3), "date": date}
    except Exception as e:
        print(f"Error fetching BRL/CZK rate: {e}")
    return None


def load_previous_data():
    if os.path.exists("south-america/data.json"):
        try:
            with open("south-america/data.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def fallback_assessment():
    return {
        "threat_level": "STABLE",
        "sentiment_score": 20,
        "security_status_cs": "Za posledních 24h nebyly zachyceny žádné nové zásadní události v Jižní Americe.",
        "security_status_en": "No significant new developments in South America were detected in the last 24 hours.",
        "recommendations": [
            {"sector_cs": "Brazilský akciový trh (Bovespa, ETF EWZ)", "sector_en": "Brazilian Equities (Bovespa, EWZ ETF)", "action": "HOLD",
             "reason_cs": "Trhy jsou bez výrazných impulzů stabilní.", "reason_en": "Markets remain stable without major triggers."},
            {"sector_cs": "Argentina (Merval, YPF, MercadoLibre)", "sector_en": "Argentina (Merval, YPF, MercadoLibre)", "action": "HOLD",
             "reason_cs": "Bez nových politických impulzů zůstává trh stabilní.", "reason_en": "Without new political triggers, the market remains stable."},
            {"sector_cs": "Těžba kovů: měď a lithium (Southern Copper, SQM, Freeport)", "sector_en": "Mining: Copper & Lithium (Southern Copper, SQM, Freeport)", "action": "HOLD",
             "reason_cs": "Ceny komodit jsou bez výrazných výkyvů.", "reason_en": "Commodity prices show no major swings."},
            {"sector_cs": "Ropa a energetika (Petrobras, Ecopetrol, Chevron)", "sector_en": "Oil & Energy (Petrobras, Ecopetrol, Chevron)", "action": "HOLD",
             "reason_cs": "Ceny energií jsou bez výrazných výkyvů.", "reason_en": "Energy prices show no major swings."},
            {"sector_cs": "Zemědělství a potraviny (JBS, Bunge, Cosan)", "sector_en": "Agriculture & Food (JBS, Bunge, Cosan)", "action": "HOLD",
             "reason_cs": "Sektor je bez nových rizik stabilní.", "reason_en": "Without new risks, the sector remains stable."},
            {"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "HOLD",
             "reason_cs": "Bez přímého dopadu z Jižní Ameriky zůstávají české tituly stabilní.", "reason_en": "Without direct spillover from South America, Czech equities remain stable."}
        ],
        "forecast_cs": "Bez nových dat nelze aktualizovat výhled.",
        "forecast_en": "No updated outlook without new data.",
        "forecast_review_cs": "Žádná předchozí předpověď k vyhodnocení.",
        "forecast_review_en": "No previous forecast to evaluate."
    }


def prompt_summary(text, limit=300):
    s = re.sub(r"<[^>]*>", " ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def analyze_with_ai(articles, previous_forecast_cs, previous_forecast_en):
    if not articles:
        return fallback_assessment()

    news_text = "\n".join([f"- {a['title']}: {prompt_summary(a['summary'])}" for a in articles])
    prev_cs = previous_forecast_cs or "Žádná předchozí předpověď."
    prev_en = previous_forecast_en or "No previous forecast."

    prompt = f"""
    You are a top-tier portfolio manager and political/security analyst covering South America. Based on the following news from the last 24 hours about South American politics and elections, economies, currencies, commodities (copper, lithium, oil, soy, coffee) and security (organized crime, unrest), produce an analytical overview and investment recommendations in BOTH Czech and English. Consider the full breadth of developments: national elections and political stability (including Brazil's presidential race), central banks, inflation and currencies, trade policy and US tariffs, commodity exports, organized crime and drug trafficking, civil unrest, deforestation and climate events, and any acute security incidents.

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
        "security_status_cs": "2-3 věty o aktuálním politickém, ekonomickém a bezpečnostním vývoji v Jižní Americe, česky.",
        "security_status_en": "2-3 sentences on the current political, economic and security developments in South America, in English.",
        "recommendations": [
            {{"sector_cs": "Brazilský akciový trh (Bovespa, ETF EWZ)", "sector_en": "Brazilian Equities (Bovespa, EWZ ETF)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění.", "reason_en": "1-2 sentences of reasoning."}},
            {{"sector_cs": "Argentina (Merval, YPF, MercadoLibre)", "sector_en": "Argentina (Merval, YPF, MercadoLibre)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně reforem a inflace.", "reason_en": "1-2 sentences regarding reforms and inflation."}},
            {{"sector_cs": "Těžba kovů: měď a lithium (Southern Copper, SQM, Freeport)", "sector_en": "Mining: Copper & Lithium (Southern Copper, SQM, Freeport)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně cen kovů a politiky v Chile a Peru.", "reason_en": "1-2 sentences regarding metal prices and policy in Chile and Peru."}},
            {{"sector_cs": "Ropa a energetika (Petrobras, Ecopetrol, Chevron)", "sector_en": "Oil & Energy (Petrobras, Ecopetrol, Chevron)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně cen ropy a politiky v Brazílii, Kolumbii a Guyaně.", "reason_en": "1-2 sentences regarding oil prices and policy in Brazil, Colombia and Guyana."}},
            {{"sector_cs": "Zemědělství a potraviny (JBS, Bunge, Cosan)", "sector_en": "Agriculture & Food (JBS, Bunge, Cosan)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně sóji, kávy, hovězího a cel.", "reason_en": "1-2 sentences regarding soy, coffee, beef and tariffs."}},
            {{"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění dopadu dění v Jižní Americe na tyto tři tituly.", "reason_en": "1-2 sentences on how South American developments affect these three stocks."}}
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
                "Title": f"South America Monitor: {threat_level}".encode("utf-8"),
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
    <title>South America AI Monitor</title>
    <link>https://matesva.github.io/Redsea-monitor/south-america/</link>
    <description>AI monitoring of South American political, economic and security developments</description>
    {items}
</channel>
</rss>"""
    os.makedirs("south-america", exist_ok=True)
    with open("south-america/rss.xml", "w", encoding="utf-8") as f:
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
    brl_czk = fetch_brl_czk()
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
        "bovespa": market_data.get("bovespa", {}).get("value") if market_data.get("bovespa") else None,
        "brl_czk": brl_czk.get("value") if brl_czk else None
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
        "brl_czk": brl_czk
    }

    os.makedirs("south-america", exist_ok=True)
    with open("south-america/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_rss(articles)

    if threat_key == "CRITICAL":
        status_for_alert = ai_assessment.get("security_status_en", "")
        send_ntfy_alert(threat_key, status_for_alert)


if __name__ == "__main__":
    run()

