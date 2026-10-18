#!/usr/bin/env python3
"""ČSÚ volby do Senátu 2026 (1. i 2. kolo) -> senat.json

Použití:  python senat_update.py <adresář větve data> [--debug]

Zdroj: https://volby.gov.cz/appdata/senat/<RRRRMMDD>/odata/vysledky.xml
(RRRRMMDD = první den voleb). Názvy elementů a atributů se hledají tolerantně,
protože struktura XML pro rok 2026 nebyla při psaní skriptu ověřena.
Když se nic nenajde, skript skončí chybou a stávající senat.json nepřepíše.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

OUT = next((a for a in sys.argv[1:] if not a.startswith("--")), ".")
DEBUG = "--debug" in sys.argv
UA = {"User-Agent": "Redsea-monitor/1.0 (+https://matesva.github.io/Redsea-monitor/)"}

HOSTS = ["https://volby.gov.cz", "https://www.volby.cz"]
DATES = ["20261009", "20261010"]          # první den voleb (zkouší se popořadě)
SECOND_ROUND = "16.–17. 10. 2026"


def get(url):
    last = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 404):
                break
        except Exception as e:
            last = e
        time.sleep(2 + 3 * i)
    raise last


def ln(el):
    t = el.tag if isinstance(el.tag, str) else ""
    return t.split("}")[-1].lower()


def attrs(el):
    """Atributy + textové potomky bez dětí, vše s malými písmeny."""
    d = {k.split("}")[-1].lower(): v for k, v in el.attrib.items()}
    for ch in el:
        if len(ch) == 0 and not ch.attrib and (ch.text or "").strip():
            d.setdefault(ln(ch), ch.text.strip())
    return d


def pick(d, *names):
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return None


def fuzzy(d, *parts):
    for k, v in d.items():
        if all(p in k for p in parts) and v not in (None, ""):
            return v
    return None


def num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(",", ".").replace("\xa0", "").replace(" ", ""))
    except ValueError:
        return None


def is_cand(el):
    k = attrs(el)
    return any(x in k for x in ("zvolen_1kolo", "hlasy_1kolo", "hlasy_2kolo", "zvolen_2kolo"))


def cand_name(k):
    full = pick(k, "jmeno_kandidata", "kandidat", "cele_jmeno")
    if full:
        return full
    parts = [pick(k, "titulpred", "titul_pred"), pick(k, "jmeno"), pick(k, "prijmeni"),
             pick(k, "titulza", "titul_za")]
    return " ".join(p for p in parts if p).strip() or "?"


def cand_party(k):
    return (pick(k, "nazev_strany", "naz_str", "nazev_vs", "nazev_strany_kand", "zkratka_strany",
                 "zkratka", "naz_strany")
            or fuzzy(k, "naz", "str") or "")


def find_obvody(root):
    """Nejvnitřnější elementy s 'obvod' v názvu, které obsahují kandidáty."""
    res = []
    for el in root.iter():
        if "obvod" not in ln(el):
            continue
        cands = [d for d in el.iter() if d is not el and is_cand(d)]
        if not cands:
            continue
        inner = any("obvod" in ln(d) and d is not el and any(is_cand(x) for x in d.iter() if x is not d)
                    for d in el.iter())
        if inner:
            continue
        res.append((el, cands))
    return res


def parse_obvod(el, cands):
    k = attrs(el)
    code = pick(k, "cis_obvod", "cislo_obvodu", "cislo", "obvod", "kod") or fuzzy(k, "cis", "obvod")
    name = pick(k, "naz_obvod", "nazev_obvodu", "nazev", "naz") or fuzzy(k, "naz", "obvod") or ""
    uc = next((d for d in el.iter() if ln(d) == "ucast"), None)
    uk = attrs(uc) if uc is not None else {}
    turnout = num(pick(uk, "ucast_proc") or fuzzy(uk, "ucast", "proc"))
    sec = num(pick(uk, "okrsky_zprac_proc") or fuzzy(uk, "zprac", "proc"))
    turnout2 = num(fuzzy(uk, "ucast", "proc", "2"))

    rows = []
    for c in cands:
        ck = attrs(c)
        rows.append({
            "n": cand_name(ck), "party": cand_party(ck),
            "v1": num(pick(ck, "hlasy_1kolo")), "p1": num(pick(ck, "hlasy_proc_1kolo")),
            "z1": (pick(ck, "zvolen_1kolo") or "").upper(),
            "v2": num(pick(ck, "hlasy_2kolo")), "p2": num(pick(ck, "hlasy_proc_2kolo")),
            "z2": (pick(ck, "zvolen_2kolo") or "").upper(),
        })

    def fill_pct(key_v, key_p):
        tot = sum(r[key_v] or 0 for r in rows)
        for r in rows:
            if r[key_p] is None and r[key_v] is not None and tot > 0:
                r[key_p] = round(r[key_v] / tot * 100, 2)

    fill_pct("v1", "p1")
    c1 = []
    for r in rows:
        if r["v1"] is None and r["p1"] is None:
            continue
        o = {"n": r["n"], "party": r["party"], "votes": int(r["v1"]) if r["v1"] is not None else None,
             "pct": r["p1"]}
        if r["z1"].startswith("ZVOLEN"):
            o["elected"] = True
        elif r["z1"].startswith("2"):
            o["runoff"] = True
        c1.append(o)

    obv = {"c": int(num(code)) if num(code) is not None else code, "n": name, "turnout": turnout,
           "sec": sec, "cand": c1}

    r2rows = [r for r in rows if r["v2"] is not None or r["z2"]]
    if r2rows:
        fill_pct("v2", "p2")
        c2 = []
        for r in r2rows:
            o = {"n": r["n"], "party": r["party"],
                 "votes": int(r["v2"]) if r["v2"] is not None else None, "pct": r["p2"]}
            if r["z2"].startswith("ZVOLEN"):
                o["elected"] = True
            c2.append(o)
        signed = any(o.get("elected") for o in c2)
        obv["r2"] = {"turnout": turnout2, "sec": 100.0 if signed else None, "cand": c2}
    return obv


def fetch_xml():
    errs = []
    for d in DATES:
        for h in HOSTS:
            url = f"{h}/appdata/senat/{d}/odata/vysledky.xml"
            try:
                raw = get(url)
                root = ET.fromstring(raw)
                if DEBUG:
                    print("OK:", url, "kořen:", ln(root), "bytů:", len(raw))
                return root, raw, url
            except Exception as e:
                errs.append(f"{url}: {e}")
    raise RuntimeError("Nepodařilo se stáhnout vysledky.xml:\n" + "\n".join(errs))


def stable(o):
    o = json.loads(json.dumps(o))
    o.get("meta", {}).pop("updated", None)
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def main():
    root, raw, url = fetch_xml()
    found = find_obvody(root)
    if DEBUG:
        print("nalezeno obvodů:", len(found))
        if not found:
            print(raw[:3000].decode("utf-8", "replace"))
        else:
            el, cands = found[0]
            print("první obvod:", ln(el), dict(el.attrib))
            print("první kandidát:", ln(cands[0]), dict(cands[0].attrib))
    if not found:
        print("CHYBA: v XML nebyly nalezeny žádné obvody s kandidáty – senat.json se nemění.")
        sys.exit(1)

    obvody = [parse_obvod(el, c) for el, c in found]
    obvody.sort(key=lambda o: (isinstance(o["c"], str), o["c"]))

    n1 = sum(1 for o in obvody if any(c.get("elected") for c in o["cand"]))
    n2 = sum(1 for o in obvody if "r2" in o and any(c.get("elected") for c in o["r2"]["cand"]))
    nr = sum(1 for o in obvody if any(c.get("runoff") for c in o["cand"])
             and not ("r2" in o and any(c.get("elected") for c in o["r2"]["cand"])))
    tz = timezone(timedelta(hours=2))
    data = {
        "meta": {
            "status": f"Zvoleno {n1 + n2} z {len(obvody)} obvodů (1. kolo: {n1}, 2. kolo: {n2}), čeká na 2. kolo: {nr}",
            "updated": datetime.now(tz).isoformat(timespec="seconds"),
            "second_round": SECOND_ROUND,
            "source": url,
        },
        "obvody": obvody,
    }

    path = f"{OUT}/senat.json"
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        if stable(old) == stable(data):
            print("senat.json beze změny")
            return
    except Exception:
        pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("senat.json uložen:", len(obvody), "obvodů, zvoleno", n1 + n2, ", 2. kolo čeká:", nr)


if __name__ == "__main__":
    main()
