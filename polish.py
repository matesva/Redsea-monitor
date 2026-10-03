import os, re, json, html

SITE = "https://matesva.github.io/Redsea-monitor/"
BASE = "/Redsea-monitor/"
PAGES = [
    ("index.html", ""), ("redsea/index.html", "redsea/"), ("usa/index.html", "usa/"),
    ("europe/index.html", "europe/"), ("middle-east/index.html", "middle-east/"),
    ("asia/index.html", "asia/"), ("japan/index.html", "japan/"),
    ("czechia/index.html", "czechia/"), ("uspesnost/index.html", "uspesnost/"),
    ("hledani/index.html", "hledani/"), ("navstevnost/index.html", "navstevnost/"),
]
INK, BRASS, PAPER, DIM = (11, 29, 38), (184, 134, 59), (231, 224, 205), (154, 168, 172)

FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" rx="12" fill="#0b1d26"/>'
           '<circle cx="32" cy="32" r="22" fill="none" stroke="#b8863b" stroke-width="3"/>'
           '<path d="M32 12 L37 32 L32 52 L27 32 Z" fill="#b8863b"/>'
           '<circle cx="32" cy="32" r="3" fill="#0b1d26"/></svg>')

SW = """const V="monitory-v1";
self.addEventListener("install",e=>{self.skipWaiting()});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener("fetch",e=>{
  const r=e.request;
  if(r.method!=="GET"||!r.url.startsWith(self.location.origin))return;
  e.respondWith(fetch(r).then(res=>{const c=res.clone();caches.open(V).then(ch=>ch.put(r,c));return res}).catch(()=>caches.match(r)));
});
"""


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def font(size, bold=True):
    from PIL import ImageFont
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for p in ("/usr/share/fonts/truetype/dejavu/" + name, name):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make_images():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow chybí, obrázky přeskakuji")
        return
    os.makedirs("icons", exist_ok=True)
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        im = Image.new("RGB", (size, size), INK)
        d = ImageDraw.Draw(im)
        m = size * 0.12
        d.ellipse([m, m, size - m, size - m], outline=BRASS, width=max(2, int(size * 0.035)))
        c, r = size / 2, size * 0.30
        d.polygon([(c, c - r), (c + size * 0.07, c), (c, c + r), (c - size * 0.07, c)], fill=BRASS)
        d.ellipse([c - size * 0.03, c - size * 0.03, c + size * 0.03, c + size * 0.03], fill=INK)
        im.save("icons/" + name)
    im = Image.new("RGB", (1200, 630), INK)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1200, 10], fill=BRASS)
    d.text((80, 190), "AI MONITORY", font=font(96), fill=PAPER)
    d.text((80, 330), "Rudé moře · USA · Evropa · Asie · Japonsko · Česko", font=font(38, False), fill=DIM)
    d.text((80, 500), "Automaticky aktualizované AI přehledy", font=font(32, False), fill=BRASS)
    im.save("og.png")
    print("obrázky vytvořeny")


def og_tags(s, rel):
    t = re.search(r"<title>(.*?)</title>", s, re.S)
    title = html.unescape(t.group(1).strip()) if t else "AI Monitory"
    d = re.search(r'<meta name="description" content="([^"]*)"', s)
    desc = html.unescape(d.group(1)) if d else "Automaticky aktualizované AI přehledy zpráv a situace"
    c = re.search(r'<link rel="canonical" href="([^"]*)"', s)
    url = c.group(1) if c else SITE + rel
    e = lambda x: html.escape(x, quote=True)
    return [
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="cs_CZ">',
        '<meta property="og:title" content="%s">' % e(title),
        '<meta property="og:description" content="%s">' % e(desc),
        '<meta property="og:url" content="%s">' % e(url),
        '<meta property="og:image" content="%sog.png">' % SITE,
        '<meta name="twitter:card" content="summary_large_image">',
    ]


def inject(path, rel):
    if not os.path.exists(path):
        print("chybí:", path)
        return
    s = open(path, encoding="utf-8").read()
    if "</head>" not in s:
        print("bez </head>:", path)
        return
    add = []
    if 'rel="icon"' not in s:
        add.append('<link rel="icon" type="image/svg+xml" href="%sfavicon.svg">' % BASE)
    if 'rel="apple-touch-icon"' not in s:
        add.append('<link rel="apple-touch-icon" href="%sicons/apple-touch-icon.png">' % BASE)
    if 'rel="manifest"' not in s:
        add.append('<link rel="manifest" href="%sapp.webmanifest">' % BASE)
    if 'property="og:title"' not in s:
        add += og_tags(s, rel)
    if not add:
        print("už má:", path)
        return
    s = s.replace("</head>", "\n".join(add) + "\n</head>", 1)
    open(path, "w", encoding="utf-8").write(s)
    print("upraveno:", path)


def main():
    write("favicon.svg", FAVICON)
    write("sw.js", SW)
    write("app.webmanifest", json.dumps({
        "name": "AI Monitory", "short_name": "Monitory", "lang": "cs",
        "start_url": BASE, "scope": BASE, "display": "standalone",
        "background_color": "#0b1d26", "theme_color": "#0b1d26",
        "icons": [
            {"src": BASE + "icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": BASE + "icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        ],
    }, ensure_ascii=False, indent=1))
    make_images()
    for path, rel in PAGES:
        inject(path, rel)


if __name__ == "__main__":
    main()
