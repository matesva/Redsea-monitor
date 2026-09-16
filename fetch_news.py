import feedparser
import json
import os
from datetime import datetime
from google import genai
from google.genai import types
from pydantic import BaseModel

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Extrémně rozšířený seznam RSS feedů rozdělený podle kategorií
RSS_FEEDS = [
    # --- Globální zpravodajské agentury a deníky ---
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://search.cnbc.com/rs/search/combinedrenderer.view?query=red%20sea%20houthi&partnerId=2000&target=all",
    "https://www.theguardian.com/world/middleeast/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
    "https://www.france24.com/en/middle-east/rss",
    "https://www.dw.com/rdf/rss-en-mid",
    "https://feeds.washingtonpost.com/rss/world",
    "https://abcnews.go.com/abcnews/internationalheadlines",
    "https://cbsnews1.cbsistatic.com/feeds/rss/world.xml",
    "https://www.independent.co.uk/news/world/middle-east/rss",

    # --- Blízkovýchodní a regionální média ---
    "https://www.arabnews.com/cat/1/rss.xml",
    "https://www.timesofisrael.com/feed/",
    "https://www.jpost.com/rss/rssfeedsfrontpage.aspx",
    "https://www.thenationalnews.com/arc/outboundfeeds/rss/",
    "https://www.middleeasteye.net/rss",
    "https://www.egypttoday.com/RSS/1",

    # --- Námořní doprava, Logistika & Přístavy ---
    "https://maritime-executive.com/rss",
    "https://gcaptain.com/feed/",
    "https://www.shippingwatch.com/rss",
    "https://www.loadstar.co.uk/feed/",
    "https://www.porttechnology.org/feed/",
    "https://www.marinelink.com/news/rss",

    # --- Vojenství, Obrana & Geopolitika ---
    "https://www.defensenews.com/arc/outboundfeeds/rss/",
    "https://www.militarytimes.com/arc/outboundfeeds/rss/",
    "https://www.naval-technology.com/feed/",
    "https://www.longwarjournal.org/feed",
    "https://www.uawire.org/rss",

    # --- Ekonomika, Komodity & Ropa ---
    "https://www.ft.com/world/middle-east?format=rss",
    "https://www.oilprice.com/rss/main",
    "https://www.rigzone.com/news/rss/rigzone_latest.aspx"
]

# Vyšperkovaný seznam klíčových slov pro filtraci
KEYWORDS = [
    "Houthi", "Húthí", "Houthis", "Red Sea", "RedSea", 
    "Yemen", "Jemen", "Bab-el-Mandeb", "Bab el Mandeb", "Bab al-Mandab",
    "shipping", "oil", "tanker", "Suez", "drone", "missile", "UAV",
    "CENTCOM", "Gulf of Aden", "Adenský záliv", "vessel", "cargo"
]

THREAT_MAP = {"STABILNÍ": 1, "STŘEDNÍ": 2, "VYSOKÁ": 3, "KRITICKÁ": 4}

# Pydantic schéma pro výstup Gemini
class Recommendation(BaseModel):
    sector: str
    action: str
    reason: str

class SecurityAnalysis(BaseModel):
    threat_level: str
    security_status: str
    recommendations: list[Recommendation]
    forecast: str

def fetch_articles():
    articles = []
    seen_links = set()

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                link = entry.get("link", "#")
                
                # Deduplikace
                if link in seen_links:
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                full_text = f"{title} {summary}"

                if any(kw.lower() in full_text.lower() for kw in KEYWORDS):
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "published": entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "source": feed.feed.get("title", "Zpravodajství")
                    })
                    seen_links.add(link)
        except Exception as e:
            # Tichá chyba nebo logování při problému s konkrétním RSS
            print(f"Chyba při načítání RSS {feed_url}: {e}")
            
    return articles[:20]  # Posíláme do AI top 20 nejnovějších zpráv

def analyze_with_ai(articles):
    if not articles:
        return {
            "threat_level": "STABILNÍ",
            "security_status": "Za posledních 24h nebyly zachyceny žádné nové zásadní události.",
            "recommendations": [
                {"sector": "Námořní doprava", "action": "DRŽET", "reason": "Ceny přepravy jsou stabilizované."},
                {"sector": "Obranný průmysl", "action": "KOUPIT", "reason": "Trvalé geopolitické napětí udrží zakázky."},
                {"sector": "Energetika a Ropa", "action": "DRŽET", "reason": "Ropné trhy vykazují vyrovnanou nabídku a poptávku."},
                {"sector": "Spotřební sektor & Auto", "action": "PRODAT", "reason": "Riziko zpoždění v dodavatelských řetězcích trvá."}
            ],
            "forecast": "Bez nových dat nelze aktualizovat výhled."
        }

    news_text = "\n".join([f"- [{a['source']}] {a['title']}: {a['summary']}" for a in articles])

    prompt = f"""
    Jsi špičkový portfoliový manažer a bezpečnostní analytik. Na základě následujících zpráv za posledních 24 hodin o Húthíích a Rudém moři vytvoř analytický přehled a investiční doporučení v češtině.

    Zprávy:
    {news_text}

    Pravidla:
    - threat_level musí mít hodnotu pouze: "KRITICKÁ", "VYSOKÁ", nebo "STŘEDNÍ".
    - action v recommendations musí být výhradně "KOUPIT", "PRODAT" nebo "DRŽET".
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SecurityAnalysis,
                temperature=0.2,
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print("Chyba při zpracování AI odpovědi:", e)
        return {
            "threat_level": "VYSOKÁ",
            "security_status": "Chyba při automatické analýze AI.",
            "recommendations": [],
            "forecast": "Nepodařilo se vygenerovat předpověď."
        }

def run():
    articles = fetch_articles()
    ai_assessment = analyze_with_ai(articles)

    history = []
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                history = old_data.get("history", [])
        except Exception:
            history = []

    threat_key = ai_assessment.get("threat_level", "").split(" ")[0].split("/")[0].strip()
    threat_value = THREAT_MAP.get(threat_key, 1)

    history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "threat_level": threat_key,
        "value": threat_value
    })
    history = history[-30:]

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "assessment": ai_assessment,
        "articles": articles,
        "history": history
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
