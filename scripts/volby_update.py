#!/usr/bin/env python3
"""ČSÚ komunální volby 2026 -> volby.json (Praha, krajská města, ČR) + obce.json (všechny obce).

Použití:  python volby_update.py <adresář větve data> [--debug]
"""
import json
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

BASE = "https://volby.gov.cz/appdata/kv2026/20261009/odata"
URL_RZCOCO_JSON = "https://volby.gov.cz/opendata/kv2026/json/kvrzcoco.json"
URL_RZCOCO_XML = "https://volby.gov.cz/opendata/kv2026/xml/kvrzcoco.xml"
OUT = next((a for a in sys.argv[1:] if not a.startswith("--")), ".")
DEBUG = "--debug" in sys.argv
UA = {"User-Agent": "Redsea-monitor/1.0 (+https://matesva.github.io/Redsea-monitor/)"}
MAX_SECONDS = 420
TOP_ROWS = 10

# krajská města: název -> kód obce (stejný kód jako v datech ČSÚ)
CITY_CODES = {
    "Praha": "554782", "Brno": "582786", "Ostrava": "554821", "Plzeň": "554791",
    "Liberec": "563889", "Olomouc": "552003", "České Budějovice": "544256",
    "Hradec Králové": "569810", "Ústí nad Labem": "554804", "Pardubice": "555134",
    "Zlín": "585068", "Jihlava": "586846", "Karlovy Vary": "554961",
}

# Praha: štítek v tabulce průzkumů -> část názvu kandidátky v datech ČSÚ
PRAGUE_MAP = {
    "STAN": "STAROSTOVÉ A NEZÁVISLÍ",
    "SPOLU (ODS+TOP)": "SPOLU pro Prahu",
    "Praha sobě": "PRAHA SOBĚ",
    "ANO": "ANO 2011",
    "Piráti": "pirátská",
    "SPD": "SPD pro Prahu",
    "AUTO": "Motoristé",
}

DEFAULT_VOLBY = {
    "meta": {
        "region": "Praha – zastupitelstvo hl. m. Prahy",
        "status": "",
        "updated": None,
        "polls": {
            "median": "Median pro Praha In, sběr 31.8.–3.9.2026",
            "ipsos": "Ipsos pro SPOLU, srpen 2026",
        },
    },
    "data": [
        {"n": "STAN", "res": None, "median": 22.6, "ipsos": 22},
        {"n": "SPOLU (ODS+TOP)", "res": None, "median": 13.9, "ipsos": 20},
        {"n": "Praha sobě", "res": None, "median": 12.9, "ipsos": 9},
        {"n": "ANO", "res": None, "median": 23.3, "ipsos": 20},
        {"n": "Piráti", "res": None, "median": 10.8, "ipsos": 12},
        {"n": "SPD", "res": None, "median": 5.4, "ipsos": 5},
        {"n": "AUTO", "res": None, "median": 5.0, "ipsos": 4},
    ],
}


def get(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == 2:
                raise
        except Exception:
            if attempt == 2:
                raise
        time.sleep(2)


def ln(tag):
    return tag.rsplit("}", 1)[-1]


def attr(el, *names):
    up = {k.upper(): v for k, v in el.attrib.items()}
    for n in names:
        if n in up and up[n] not in (None, ""):
            return up[n]
    return None


def num(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


def fmt(p):
    return f"{p:.2f}".replace(".", ",")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def strip_volatile(o):
    return {k: v for k, v in o.items() if k not in ("updated", "generated")}


def save_if_changed(path, obj, indent=None):
    old = load_json(path, None)
    if old is not None and json.dumps(strip_volatile(old), sort_keys=True) == \
            json.dumps(strip_volatile(obj), sort_keys=True):
        print("beze změny:", path)
        return
    with open(path, "w", encoding="utf-8") as f:
        if indent:
            json.dump(obj, f, ensure_ascii=False, indent=indent)
        else:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("zapsáno:", path)


# ---------- názvy obcí z registru ČSÚ (kvrzcoco) ----------
CODE_KEYS = ("KODZASTUP", "CIS_OBEC", "KOD_OBEC")
NAME_KEYS = ("NAZEVZAST", "NAZEV_ZAST", "NAZEVOBCE", "NAZEV_OBCE", "NAZ_OBEC", "NAZEVZASTUP", "NAZEV")


def extract_pairs(obj, out):
    if isinstance(obj, dict):
        up = {str(k).upper(): v for k, v in obj.items()}
        code = next((str(up[k]) for k in CODE_KEYS if up.get(k) not in (None, "")), None)
        name = next((up[k] for k in NAME_KEYS if isinstance(up.get(k), str) and up[k].strip()), None)
        if code and name:
            out[code.strip()] = name.strip()
        for v in obj.values():
            extract_pairs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            extract_pairs(v, out)


def extract_pairs_xml(root, out):
    for el in root.iter():
        d = dict(el.attrib)
        for c in el:
            if len(c) == 0 and c.text and c.text.strip():
                d[ln(c.tag)] = c.text.strip()
        extract_pairs(d, out)


def load_names():
    path = f"{OUT}/obce_nazvy.json"
    names = load_json(path, {})
    if len(names) < 1000:
        names = {}
        try:
            raw = get(URL_RZCOCO_JSON)
            if raw:
                extract_pairs(json.loads(raw.decode("utf-8-sig")), names)
        except Exception as e:
            print("kvrzcoco.json nelze načíst:", e)
        if len(names) < 1000:
            try:
                raw = get(URL_RZCOCO_XML)
                if raw:
                    extract_pairs_xml(ET.fromstring(raw), names)
            except Exception as e:
                print("kvrzcoco.xml nelze načíst:", e)
        print("názvů z registru RZCOCO:", len(names))
        if len(names) >= 1000:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(names, f, ensure_ascii=False, separators=(",", ":"))
    for city, code in CITY_CODES.items():
        names[code] = city
    return names


# ---------- celá ČR ----------
def parse_national():
    raw = get(BASE + "/vysledky.xml")
    if not raw:
        return None
    root = ET.fromstring(raw)
    for typ in root.iter():
        if ln(typ.tag) == "TYP_ZASTUP" and typ.get("OZNAC_TYPU") == "OBEC":
            u = next((c for c in typ if ln(c.tag) == "UCAST"), None)
            z = next((c for c in typ if ln(c.tag) == "ZASTUPIT_INFO"), None)
            rows = []
            for c in typ:
                if ln(c.tag) == "VOLEBNI_STRANA":
                    seats = int(num(c.get("ZASTUPITELE_POCET")) or 0)
                    if seats > 0:
                        rows.append({"n": c.get("NAZEV_STRANY"), "seats": seats})
            rows.sort(key=lambda r: -r["seats"])
            total = int(num(z.get("ZASTUPITELE_ZVOLENI")) or 0) if z is not None else 0
            zv = int(num(z.get("ZASTUPITELSTVA_ZVOLENA")) or 0) if z is not None else 0
            cel = int(num(z.get("ZASTUPITELSTVA_CELKEM")) or 0) if z is not None else 0
            proc = num(u.get("OKRSKY_ZPRAC_PROC")) if u is not None else None
            done = u is not None and u.get("OKRSKY_ZPRAC") == u.get("OKRSKY_CELKEM")
            status = ("konečné" if done else "průběžné") + \
                f", sečteno {fmt(proc or 0)} % okrsků (zastupitelstev zvoleno {zv} z {cel})"
            return {
                "status": status,
                "turnout": num(u.get("UCAST_PROC")) if u is not None else None,
                "total": total,
                "rows": rows[:TOP_ROWS],
            }
    return None


# ---------- obce po dávkách ----------
def find_attr_anywhere(el, name):
    for e in el.iter():
        v = attr(e, name)
        if v is not None:
            return v
    return None


def handle_obec(el, typ, obce):
    if typ == "MCMO":
        return
    kod = attr(el, "CIS_OBEC", "KODZASTUP", "KOD_OBEC", "KOD")
    if not kod:
        return
    name = attr(el, "NAZ_OBEC", "NAZEV_OBCE", "NAZEV_OBEC", "NAZ_ZASTUP", "NAZEV")
    parties = []
    for c in el.iter():
        if ln(c.tag) != "VOLEBNI_STRANA":
            continue
        nm = attr(c, "NAZEV_STRANY", "NAZ_STR", "NAZEV") or f"strana {attr(c, 'VSTRANA') or '?'}"
        parties.append({
            "n": nm,
            "h": num(attr(c, "HLASY")) or 0,
            "p": num(attr(c, "HLASY_PROC")),
            "s": int(num(attr(c, "ZASTUPITELE_POCET")) or 0),
        })
    if not parties:
        return
    tot = sum(p["h"] for p in parties) or 1
    for p in parties:
        if p["p"] is None:
            p["p"] = p["h"] / tot * 100
    parties.sort(key=lambda p: -p["h"])
    size = sum(p["s"] for p in parties)
    prev = obce.get(kod, {})
    ucast = num(find_attr_anywhere(el, "UCAST_PROC"))
    sec = num(find_attr_anywhere(el, "OKRSKY_ZPRAC_PROC"))
    if size > 0:
        sec = 100.0  # mandáty se dělí až po sečtení všech okrsků
    obce[kod] = {
        "n": name or prev.get("n") or f"obec {kod}",
        "ucast": ucast if ucast is not None else prev.get("ucast"),
        "sec": sec if sec is not None else prev.get("sec"),
        "size": size or prev.get("size") or 0,
        "rows": [[p["n"], round(p["p"], 2), p["s"] if size else None]
                 for p in parties[:TOP_ROWS]],
    }


def walk(el, typ, obce):
    t = ln(el.tag)
    if t == "TYP_ZASTUP":
        typ = el.get("OZNAC_TYPU") or typ
    if t == "OBEC":
        if DEBUG and not getattr(walk, "shown", False):
            walk.shown = True
            print("--- první OBEC (debug) ---")
            print(ET.tostring(el, encoding="unicode")[:2500])
        handle_obec(el, typ, obce)
        return
    for c in el:
        walk(c, typ, obce)


def has_error(root):
    for e in root.iter():
        if "CHYBA" in ln(e.tag).upper() or "CHYBA" in "".join(k.upper() for k in e.attrib):
            return True
    return False


def update_obce():
    path = f"{OUT}/obce.json"
    state = load_json(path, {"last_batch": 0, "obce": {}})
    obce = state.get("obce", {})
    n = state.get("last_batch", 0) + 1
    t0 = time.time()
    got = 0
    while time.time() - t0 < MAX_SECONDS:
        url = f"{BASE}/obce_d/vysledky_obce_{n:05d}.xml"
        raw = get(url)
        if raw is None:
            break
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            print("chybné XML:", url)
            break
        if has_error(root):
            print("ČSÚ vrací chybu:", url)
            break
        walk(root, None, obce)
        state["last_batch"] = n
        got += 1
        n += 1
    print(f"dávek načteno: {got}, obcí celkem: {len(obce)}")

    names = load_names()
    for kod, o in obce.items():
        if str(o.get("n", "")).startswith("obec ") and kod in names:
            o["n"] = names[kod]
        if kod in CITY_CODES.values():
            o["n"] = names[kod]
    unnamed = sum(1 for o in obce.values() if str(o["n"]).startswith("obec "))
    print("obcí bez názvu:", unnamed)

    state["obce"] = obce
    state["generated"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    save_if_changed(path, state)
    return obce


# ---------- volby.json ----------
def status_txt(sec):
    if sec is None:
        return "průběžné"
    if sec >= 99.995:
        return "konečné, sečteno 100 %"
    return f"průběžné, sečteno {fmt(sec)} % okrsků"


def build_city(name, obce):
    code = CITY_CODES[name]
    o = obce.get(code)
    if not o:
        print("město nenalezeno:", name, code)
        return None
    return {
        "name": name,
        "code": code,
        "size": o.get("size") or None,
        "status": status_txt(o.get("sec")),
        "turnout": o.get("ucast"),
        "rows": [{"n": r[0], "pct": r[1], **({"seats": r[2]} if r[2] else {})} for r in o["rows"]],
    }


def update_volby(obce, national):
    path = f"{OUT}/volby.json"
    v = load_json(path, DEFAULT_VOLBY)
    cities = [c for c in (build_city(n, obce) for n in CITY_CODES) if c]
    v["cities"] = cities
    if national:
        v["national"] = national
    prague = next((c for c in cities if c["name"] == "Praha"), None)
    if prague:
        for d in v.get("data", []):
            key = PRAGUE_MAP.get(d["n"])
            row = next((r for r in prague["rows"] if key and key.lower() in r["n"].lower()), None)
            if row:
                d["res"] = row["pct"]
        st = prague["status"]
        if st.startswith("konečné"):
            label = "KONEČNÉ VÝSLEDKY – sečteno 100 % okrsků"
        elif "sečteno" in st:
            label = "PRŮBĚŽNÉ VÝSLEDKY – " + st.split(", ", 1)[-1]
        else:
            label = "PRŮBĚŽNÉ VÝSLEDKY"
        v["meta"]["status"] = label + " (volby 9.–10. 10. 2026)"
    tz = timezone(timedelta(hours=2))
    v["meta"]["updated"] = datetime.now(tz).isoformat(timespec="seconds")
    save_if_changed(path, v, indent=2)


def main():
    national = parse_national()
    obce = update_obce()
    update_volby(obce, national)
    print("obcí:", len(obce))


if __name__ == "__main__":
    main()
