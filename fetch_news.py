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
        model='gemini-3.6-flash',
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

    data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "assessment": ai_assessment,
        "articles": articles
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
