import os, json, re, hashlib, datetime, html, urllib.parse, urllib.request
from collections import Counter
from email.utils import parsedate_to_datetime
import feedparser
from google import genai

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
OUT = "czechia/articles.json"
PARTIES_OUT = "czechia/parties.json"
POLLS_OUT = "czechia/polls.json"
MAX_NEW = 120
BATCH = 10
MAX_FETCH_TEXT = 15   # kolik článků o průzkumech za běh stáhnout celých
MIN_STRAN = 3         # minimum stran v průzkumu, aby se uložil

PARTY_LIST = [
    "ANO", "ODS", "STAN", "Piráti", "SPD", "TOP 09", "KDU-ČSL", "Motoristé",
    "Stačilo", "ČSSD", "KSČM", "Zelení", "Přísaha", "Svobodní", "Trikolora",
    "Prague Together", "Praha Sobě", "Spojené síly pro Prahu", "Naše Praha",
]

def gnews(q, days=3):
    qq = urllib.parse.quote_plus(f"{q} when:{days}d")
    return f"https://news.google.com/rss/search?q={qq}&hl=cs&gl=CZ&ceid=CZ:cs"

FEEDS = [
    "https://ct24.ceskatelevize.cz/rss/hlavni-zpravy",
    "https://www.irozhlas.cz/rss/irozhlas",
    "https://www.irozhlas.cz/rss/irozhlas/section/zpravy-domov",
    "https://www.ceskenoviny.cz/sluzby/rss/zpravy.php",
    "https://www.novinky.cz/rss",
    "https://www.aktualne.cz/rss/",
    "https://www.seznamzpravy.cz/rss",
    "https://servis.idnes.cz/rss.aspx?c=zpravodaj",
    "https://servis.idnes.cz/rss.aspx?c=praha",
    "https://servis.lidovky.cz/rss.aspx?r=ln_domov",
    "https://www.blesk.cz/rss",
    "https://www.denik.cz/rss/",
    "https://hn.cz/rss/",
    "https://www.info.cz/rss",
    "https://denikn.cz/feed/",
    "https://echo24.cz/rss",
    "https://www.reflex.cz/rss",
    "https://www.forum24.cz/feed/",
    "https://www.parlamentnilisty.cz/export/rss.aspx",
    "https://www.respekt.cz/rss",
    "https://demagog.cz/rss",
]

PARTIES = [
    "ANO Babiš", "ODS Fiala", "STAN Rakušan", "Piráti Hřib", "SPD Okamura",
    "TOP 09", "KDU-ČSL Výborný", "Motoristé sobě", "Stačilo", "ČSSD",
    "KSČM", "Zelení", "Přísaha", "Svobodní", "Trikolora", "Prague Together",
    "Praha Sobě", "Spojené síly pro Prahu", "Naše Praha",
]
PRAHA_QUERIES = [
    "volby Praha", "komunální volby Praha kandidáti", "kandidátka Praha volby",
    "primátor Praha", "Praha zastupitelstvo koalice", "Praha rozpočet magistrát",
    "Praha MHD doprava politika", "Praha bydlení metropolitní plán",
    "Praha městské části volby", "lídr kandidátky Praha",
    "předvolební debata Praha", "průzkum volební preference Praha",
    "předvolební slib Praha", "volební program Praha",
    "volební model Praha průzkum",
]
CR_QUERIES = [
    "česká politika", "volební průzkum preference", "vláda koalice krize",
    "Poslanecká sněmovna hlasování", "Senát volby", "prezident Pavel politika",
    "předvolební kampaň", "komentář politika", "názor volby",
    "rozpočet státní dluh vláda", "Ústavní soud politika", "krajské volby",
    "volby do zastupitelstev obcí", "průzkum STEM Median Kantar",
    "politický spor", "volební program slibuje", "předvolební slib",
    "Demagog ověřil výrok politik", "průzkum STEM preference",
    "průzkum Kantar preference", "průzkum Median preference",
    "průzkum NMS preference", "průzkum Ipsos preference", "volební model",
]
FEEDS += [gnews(q) for q in PARTIES + PRAHA_QUERIES + CR_QUERIES]

KEYWORDS = re.compile(
    r"vol[bby]|politi|kandid|strana|hnutí|koalic|opozic|vláda|parlament|"
    r"senát|primátor|zastupitel|slib|program|průzkum|preferenc|ANO|ODS|"
    r"STAN|Piráti|SPD|TOP 09|KDU|ČSSD|Praha",
    re.I,
)
POLL_RE = re.compile(r"průzkum|preferenc|volební model|odhad", re.I)

PROMPT = """Jsi věcný analytik české politiky. Pro každý článek vrať JSON pole objektů
se stejným pořadím a těmito klíči:
- "id": beze změny
- "shrnuti": 1–2 věcné české věty, vlastními slovy, bez hodnocení
- "region": "Praha" | "ČR" | "Jiný"
- "temata": pole 1–3 krátkých témat (např. "doprava", "bydlení", "rozpočet")
- "strany": pole zmíněných stran, POUZE z tohoto seznamu: {PARTIES}. Ostatní vynech.
- "ton": "neutrální" | "kritický" | "pozitivní" (tón článku vůči hlavnímu aktérovi)
- "sliby": pole objektů {"strana": <ze seznamu>, "slib": "jedna krátká česká věta",
  "tema": "krátké téma"}. Uveď jen tehdy, když článek VÝSLOVNĚ uvádí slib, program
  nebo konkrétní návrh strany či jejího kandidáta. Nic si nedomýšlej. Jinak [].
- "overeni": null, nebo jedna z hodnot "pravda" | "nepravda" | "zavádějící" |
  "nelze určit", jen pokud jde o fact-checking politického výroku.
- "pruzkum": null, nebo objekt {"agentura": "název agentury", "region": "ČR" | "Praha",
  "vysledky": {"
