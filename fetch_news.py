import feedparser
import json
import os
from datetime import datetime
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://search.cnbc.com/rs/search/combinedrenderer.view?query=red%20sea%20houthi&partnerId=2000&target=all"
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
    return articles[:10]

def extract_locations(articles):
    found = {}
    text_blob = " ".join([a['title'] + " " + a['summary'] for a in articles])
    for key, loc in LOCATIONS.items():
        if key.lower() in text_blob.lower():
            found[key] = loc
    return list(found.values())

def analyze_with_ai(articles):
    if not articles:
        return {
            "threat_level": "STABILNÍ / BEZ ZMĚN",
            "security_status": "Za posledních 24h nebyly zachyceny žádné nové zásadní události.",
            "recommendations": [
                {"sector": "Námořní doprava", "action": "DRŽET", "reason": "Ceny přepravy jsou stabilizované."},
                {"sector": "Obranný průmysl", "action": "KOUPIT", "reason": "Trvalé geopolitické napětí udrží zakázky."},
                {"sector": "Energetika a Ropa", "action": "DRŽET", "reason": "Ropné trhy vykazují vyrovnanou nabídku a poptávku."},
                {"sector": "Spotřební sektor & Auto", "action": "PRODAT", "reason": "Riziko zpoždění v dodavatelských řetězcích trvá."}
            ],
            "forecast": "Bez nových dat nelze aktualizovat výhled."
        }

    news_text = "\n".join([f"- {a['title']}: {a['summary']}" for a in articles])

    prompt = f"""
    Jsi špičkový portfoliový manažer a bezpečnostní analytik. Na základě následujících zpráv za posledních 24 hodin o Húthíích a Rudém moři vytvoř analytický přehled a investiční doporučení v češtině.

    Zprávy:
    {news_text}

    Vrať ODPOVĚĎ VÝHRADNĚ JAKO PLATNÝ JSON kód bez jakýchkoliv úvodních textů nebo markdownových značek:
    {{
        "threat_level": "KRITICKÁ / VYSOKÁ / STŘEDNÍ",
        "security_status": "2-3 věty o aktuálním bezpečnostním vývoji v Rudém moři.",
        "recommendations": [
            {{
                "sector": "Námořní doprava (např. Maersk, Hapag-Lloyd, ZIM)",
                "action": "KOUPIT / PRODAT / DRŽET",
                "reason": "1-2 věty zdůvodnění na základě sazeb a rizik."
            }},
            {{
                "sector": "Obranný průmysl (např. RTX, Lockheed Martin, BAE Systems)",
                "action": "KOUPIT / PRODAT / DRŽET",
                "reason": "1-2 věty zdůvodnění na základě zakázek."
            }},
            {{
                "sector": "Ropa a Plyn (např. Shell, BP, Chevron)",
                "action": "KOUPIT / PRODAT / DRŽET",
                "reason": "1-2 věty zdůvodnění ohledně cen ropy."
            }},
            {{
                "sector": "Evropský Spotřební sektor & Autoprůmysl (např. Volvo, BMW)",
                "action": "KOUPIT / PRODAT / DRŽET",
                "reason": "1-2 věty zdůvodnění k logistice."
            }}
        ],
        "forecast": "1-2 věty odhadu vývoje na nejbližší dny."
    }}
    """

    response = client.models.generate_content(
        model='gemini-3.5-flash-lite',
        contents=prompt,
    )

    try:
        clean_json = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean_json)
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
    locations = extract_locations(articles)

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
        "history": history,
        "locations": locations
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
