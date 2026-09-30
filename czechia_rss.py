
import os
from xml.sax.saxutils import escape

BASE = "https://matesva.github.io/Redsea-monitor/czechia/"

def build_rss(data, limit=30):
    items = ""
    for a in data[:limit]:
        items += f"""
    <item>
      <title>{escape(a.get("title", ""))}</title>
      <link>{escape(a.get("link", ""))}</link>
      <description>{escape(a.get("shrnuti") or "")}</description>
      <pubDate>{escape(a.get("published") or "")}</pubDate>
    </item>"""
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Czech Politics Monitor</title>
  <link>{BASE}</link>
  <description>Česká politika a volby: automatický přehled zpráv</description>{items}
</channel>
</rss>"""
    os.makedirs("czechia", exist_ok=True)
    with open("czechia/rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print("RSS: hotovo")
