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
NTFY_TOPIC = os.environ.get("NTFY_TOPIC_ASIA") or os.environ.get("NTFY_TOPIC")

RSS_FEEDS = [
    "https://www.scmp.com/rss/91/feed",
    "https://asia.nikkei.com/rss/feed/nar",
    "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://apnews.com/hub/asia-pacific?output=rss",
    "https://en.yna.co.kr/RSS/news.xml",
    "https://www.taiwannews.com.tw/en/rss/all",
    "https://www.channelnewsasia.com/rssfeeds/8395986",
    "https://www.reuters.com/world/asia-pacific/rss",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.cnbc.com/id/19832390/device/rss/rss.html",
    "https://www.koreaherald.com/rss/020000000000.xml",
    "https://www.japantimes.co.jp/feed/",
]

KEYWORDS = [
    "China", "Beijing", "Taiwan", "Xi Jinping", "South China Sea",
    "Japan", "Korea", "North Korea", "Kim Jong", "semiconductor", "chip",
    "PLA", "military drill", "ASEAN", "Philippines", "Pyongyang",
    "trade war", "tariff", "export controls", "Hong Kong", "Shanghai"
]

THREAT_MAP = {"STABLE": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

LOCATIONS = {
    "Beijing": {"lat": 39.9042, "lon": 116.4074, "name_cs": "Peking", "name_en": "Beijing"},
    "Taipei": {"lat": 25.0330, "lon": 121.5654, "name_cs": "Tchaj-pej", "name_en": "Taipei"},
    "Tokyo": {"lat": 35.6762, "lon": 139.6503, "name_cs": "Tokio", "name_en": "Tokyo"},
    "Seoul": {"lat": 37.5665, "lon": 126.9780, "name_cs": "Soul", "name_en": "Seoul"},
    "Pyongyang": {"lat": 39.0392, "lon": 125.7625, "name_cs": "Pchjongjang", "name_en": "Pyongyang"},
    "South China Sea": {"lat": 12.0, "lon": 114.0, "name_cs": "Jihočínské moře", "name_en": "South China Sea"},
    "Shanghai": {"lat": 31.2304, "lon": 121.4737, "name_cs": "Šanghaj", "name_en": "Shanghai"},
    "Hong Kong": {"lat": 22.3193, "lon": 114.1694, "name_cs": "Hongkong", "name_en": "Hong Kong"},
    "Manila": {"lat": 14.5995, "lon": 120.9842, "name_cs": "Manila", "name_en": "Manila"},
}



# --- Rozšíření (víc zdrojů, víc lokalit) ---
PER_FEED_MAX = 4
MAX_ARTICLES = 40

RSS_FEEDS += ["https://www.straitstimes.com/news/asia/rss.xml", "https://thediplomat.com/feed/", "https://www.thehindu.com/news/international/feeder/default.rss"]
KEYWORDS += ["India", "Pakistan", "Vietnam", "Indonesia", "Thailand", "Singapore", "Malaysia", "Myanmar", "Australia", "Modi", "Nikkei", "yuan", "rupee", "Bangladesh", "Afghanistan", "Beijing", "Kospi"]
LOCATIONS.update({
 "Delhi": {
  "lat": 28.6139,
  "lon": 77.209,
  "name_cs": "Dillí",
  "name_en": "New Delhi"
 },
 "Islamabad": {
  "lat": 33.6844,
  "lon": 73.0479,
  "name_cs": "Islámábád",
  "name_en": "Islamabad"
 },
 "Bangkok": {
  "lat": 13.7563,
  "lon": 100.5018,
  "name_cs": "Bangkok",
  "name_en": "Bangkok"
 },
 "Hanoi": {
  "lat": 21.0285,
  "lon": 105.8542,
  "name_cs": "Hanoj",
  "name_en": "Hanoi"
 },
 "Jakarta": {
  "lat": -6.2088,
  "lon": 106.8456,
  "name_cs": "Jakarta",
  "name_en": "Jakarta"
 },
 "Singapore": {
  "lat": 1.3521,
  "lon": 103.8198,
  "name_cs": "Singapur",
  "name_en": "Singapore"
 },
 "Kuala Lumpur": {
  "lat": 3.139,
  "lon": 101.6869,
  "name_cs": "Kuala Lumpur",
  "name_en": "Kuala Lumpur"
 },
 "Canberra": {
  "lat": -35.2809,
  "lon": 149.13,
  "name_cs": "Canberra",
  "name_en": "Canberra"
 },
 "Kabul": {
  "lat": 34.5553,
  "lon": 69.2075,
  "name_cs": "Kábul",
  "name_en": "Kabul"
 },
 "Dhaka": {
  "lat": 23.8103,
  "lon": 90.4125,
  "name_cs": "Dháka",
  "name_en": "Dhaka"
 },
 "Yangon": {
  "lat": 16.8409,
  "lon": 96.1735,
  "name_cs": "Rangún",
  "name_en": "Yangon"
 },
 "Taiwan Strait": {
  "lat": 24.5,
  "lon": 119.5,
  "name_cs": "Tchajwanský průliv",
  "name_en": "Taiwan Strait"
 }
})
LOCATION_TERMS = {
 "Beijing": [
  "beijing",
  "china",
  "chinese",
  "xi jinping"
 ],
 "Taipei": [
  "taipei",
  "taiwan"
 ],
 "Tokyo": [
  "tokyo",
  "japan",
  "japanese"
 ],
 "Seoul": [
  "seoul",
  "south korea",
  "south korean"
 ],
 "Pyongyang": [
  "pyongyang",
  "north korea",
  "kim jong"
 ],
 "South China Sea": [
  "south china sea"
 ],
 "Shanghai": [
  "shanghai"
 ],
 "Hong Kong": [
  "hong kong"
 ],
 "Manila": [
  "manila",
  "philippines",
  "philippine"
 ],
 "Delhi": [
  "delhi",
  "india$",
  "indian$",
  "modi"
 ],
 "Islamabad": [
  "islamabad",
  "pakistan",
  "imran khan"
 ],
 "Bangkok": [
  "bangkok",
  "thailand",
  "thai$"
 ],
 "Hanoi": [
  "hanoi",
  "vietnam"
 ],
 "Jakarta": [
  "jakarta",
  "indonesia",
  "borneo",
  "sumatra"
 ],
 "Singapore": [
  "singapore"
 ],
 "Kuala Lumpur": [
  "kuala lumpur",
  "malaysia"
 ],
 "Canberra": [
  "canberra",
  "australia",
  "sydney"
 ],
 "Kabul": [
  "kabul",
  "afghanistan",
  "taliban"
 ],
 "Dhaka": [
  "dhaka",
  "bangladesh"
 ],
 "Yangon": [
  "yangon",
  "myanmar",
  "burma"
 ],
 "Taiwan Strait": [
  "taiwan strait"
 ]
}

SOURCE_NAMES = {
 "bbci.co.uk": "BBC News",
 "bbc.co.uk": "BBC News",
 "aljazeera.com": "Al Jazeera",
 "theguardian.com": "The Guardian",
 "cnbc.com": "CNBC",
 "skynews.com": "Sky News",
 "alarabiya.net": "Al Arabiya",
 "middleeasteye.net": "Middle East Eye",
 "gcaptain.com": "gCaptain",
 "splash247.com": "Splash247",
 "oilprice.com": "OilPrice",
 "reuters.com": "Reuters",
 "apnews.com": "AP News",
 "timesofisrael.com": "Times of Israel",
 "jpost.com": "Jerusalem Post",
 "haaretz.com": "Haaretz",
 "iranintl.com": "Iran International",
 "naharnet.com": "Naharnet",
 "rudaw.net": "Rudaw",
 "navalnews.com": "Naval News",
 "defensenews.com": "Defense News",
 "maritime-executive.com": "Maritime Executive",
 "hellenicshippingnews.com": "Hellenic Shipping News",
 "zawya.com": "Zawya",
 "marketwatch.com": "MarketWatch",
 "dj.com": "WSJ Markets",
 "scmp.com": "SCMP",
 "nikkei.com": "Nikkei Asia",
 "yna.co.kr": "Yonhap",
 "taiwannews.com.tw": "Taiwan News",
 "channelnewsasia.com": "CNA",
 "koreaherald.com": "Korea Herald",
 "japantimes.co.jp": "Japan Times",
 "nhk.or.jp": "NHK World",
 "kyodonews.net": "Kyodo News",
 "mainichi.jp": "Mainichi",
 "asahi.com": "Asahi Shimbun",
 "thenationalnews.com": "The National",
 "arabnews.com": "Arab News",
 "middleeastmonitor.com": "Middle East Monitor",
 "straitstimes.com": "Straits Times",
 "thediplomat.com": "The Diplomat",
 "thehindu.com": "The Hindu"
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


def term_regex(t):
    exact = t.endswith("$")
    t = t.rstrip("$")
    return re.compile(r"(?<![a-z])" + re.escape(t) + (r"(?![a-z])" if exact else ""))


def fetch_articles():
    excludes = [e.lower() for e in globals().get("EXCLUDE_KEYWORDS", [])]
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
                combined = (title + summary).lower()
                if any(ex in combined for ex in excludes):
                    continue
                if any(kw.lower() in combined for kw in KEYWORDS):
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
        terms = LOCATION_TERMS.get(key) or [key.lower()]
        if any(term_regex(t).search(text_blob) for t in terms):
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
    data = {"hangseng": None, "nikkei": None, "usdcny": None}
    symbols = {"hangseng": ("^HSI", 1), "nikkei": ("^N225", 1), "usdcny": ("CNY=X", 1)}

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
    if os.path.exists("asia/data.json"):
        try:
            with open("asia/data.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def fallback_assessment():
    return {
        "threat_level": "STABLE",
        "sentiment_score": 20,
        "security_status_cs": "Za posledních 24h nebyly zachyceny žádné nové zásadní události v Číně a Asii.",
        "security_status_en": "No significant new developments in China and Asia were detected in the last 24 hours.",
        "recommendations": [
            {"sector_cs": "Polovodiče (TSMC, Samsung, ASML)", "sector_en": "Semiconductors (TSMC, Samsung, ASML)", "action": "HOLD",
             "reason_cs": "Bez nových exportních omezení zůstává sektor stabilní.", "reason_en": "Without new export restrictions, the sector remains stable."},
            {"sector_cs": "Čínské akcie (ETF FXI, MCHI)", "sector_en": "Chinese Equities (FXI, MCHI ETFs)", "action": "HOLD",
             "reason_cs": "Trh je bez výrazných impulzů stabilní.", "reason_en": "The market remains stable without major triggers."},
            {"sector_cs": "Japonské akcie (Nikkei 225 ETF)", "sector_en": "Japanese Equities (Nikkei 225 ETFs)", "action": "HOLD",
             "reason_cs": "Bez nových impulzů zůstává trh stabilní.", "reason_en": "Without new triggers, the market remains stable."},
            {"sector_cs": "Obranný průmysl (Lockheed Martin, RTX)", "sector_en": "Defense Industry (Lockheed Martin, RTX)", "action": "HOLD",
             "reason_cs": "Bez eskalace napětí kolem Tchaj-wanu zůstávají zakázky stabilní.", "reason_en": "Without escalation around Taiwan, order volume remains stable."},
            {"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "HOLD",
             "reason_cs": "Bez přímého dopadu z regionu zůstávají české tituly stabilní.", "reason_en": "Without direct regional spillover, Czech equities remain stable."}
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
    You are a top-tier portfolio manager and security analyst covering China and wider Asia-Pacific. Based on the following news from the last 24 hours, produce an analytical overview and investment recommendations in BOTH Czech and English. Consider the full breadth of developments: China's domestic politics and economy, Taiwan strait tensions, the South China Sea, Japan and South Korea, North Korea, semiconductor and trade policy, and any acute security incidents in the region.

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
        "security_status_cs": "2-3 věty o aktuálním politickém, ekonomickém a bezpečnostním vývoji v Číně a Asii, česky.",
        "security_status_en": "2-3 sentences on the current political, economic and security developments in China and Asia, in English.",
        "recommendations": [
            {{"sector_cs": "Polovodiče (TSMC, Samsung, ASML)", "sector_en": "Semiconductors (TSMC, Samsung, ASML)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění na základě exportních omezení a poptávky.", "reason_en": "1-2 sentences based on export controls and demand."}},
            {{"sector_cs": "Čínské akcie (ETF FXI, MCHI)", "sector_en": "Chinese Equities (FXI, MCHI ETFs)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění ohledně čínské ekonomiky a regulace.", "reason_en": "1-2 sentences regarding the Chinese economy and regulation."}},
            {{"sector_cs": "Japonské akcie (Nikkei 225 ETF)", "sector_en": "Japanese Equities (Nikkei 225 ETFs)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění.", "reason_en": "1-2 sentences of reasoning."}},
            {{"sector_cs": "Obranný průmysl (Lockheed Martin, RTX, Mitsubishi Heavy)", "sector_en": "Defense Industry (Lockheed Martin, RTX, Mitsubishi Heavy)", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění na základě napětí kolem Tchaj-wanu a regionálních zakázek.", "reason_en": "1-2 sentences based on Taiwan tensions and regional orders."}},
            {{"sector_cs": "Pražská burza: ČEZ, Komerční banka, Erste Group", "sector_en": "Prague Stock Exchange: ČEZ, Komerční banka, Erste Group", "action": "BUY / SELL / HOLD", "reason_cs": "1-2 věty zdůvodnění dopadu asijského dění na tyto tři tituly.", "reason_en": "1-2 sentences on how Asian developments affect these three stocks."}}
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
                "Title": f"China & Asia Monitor: {threat_level}".encode("utf-8"),
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
    <title>China &amp; Asia AI Monitor</title>
    <link>https://matesva.github.io/Redsea-monitor/asia/</link>
    <description>AI monitoring of China and Asia-Pacific political, economic and security developments</description>
    {items}
</channel>
</rss>"""
    os.makedirs("asia", exist_ok=True)
    with open("asia/rss.xml", "w", encoding="utf-8") as f:
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
        "hangseng": market_data.get("hangseng", {}).get("value") if market_data.get("hangseng") else None,
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

    os.makedirs("asia", exist_ok=True)
    with open("asia/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    build_rss(articles)

    if threat_key == "CRITICAL":
        status_for_alert = ai_assessment.get("security_status_en", "")
        send_ntfy_alert(threat_key, status_for_alert)


if __name__ == "__main__":
    run()

