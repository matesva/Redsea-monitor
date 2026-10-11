#!/usr/bin/env python3
"""Zvolení zastupitelé z registrů ČSÚ (kvrk + kvros) -> <data>/zast/<prefix>.json

Použití:  python zastupitele.py <adresář větve data> [--force]
"""
import io
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

BASE = "https://volby.gov.cz/opendata/kv2026/"
URL_KVRK = BASE + "xml/kvrk.zip"
URL_ROS_JSON = BASE + "json/kvros.json"
URL_ROS_XML = BASE + "xml/kvros.xml"
OUT = next((a for a in sys.argv[1:] if not a.startswith("--")), ".")
FORCE = "--force" in sys.argv
UA = {"User-Agent": "Redsea-monitor/1.0 (+https://matesva.github.io/Redsea-monitor/)"}
ZDIR = os.path.join(OUT, "zast")


def fetch(url, method="GET", timeout=300):
    req = urllib.request.Request(url, headers=UA, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if method == "HEAD":
            return dict(r.headers)
        return r.read()


def ln(tag):
    return tag.rsplit("}", 1)[-1]


def row_dict(el):
    d = {k.upper(): v for k, v in el.attrib.items()}
    for c in el:
        if c.text is not None:
            d[ln(c.tag).upper()] = c.text.strip()
    return d


def num(s, default=0):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return default


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ---------- volební strany: (KODZASTUP, OSTRANA) -> zkrácený název ----------
def load_parties():
    parties = {}

    def add(d):
        up = {str(k).upper(): v for k, v in d.items()}
        kod, ost = up.get("KODZASTUP"), up.get("OSTRANA")
        nm = up.get("ZKRATKAO30") or up.get("NAZEVCELK") or up.get("ZKRATKAO8")
        if kod not in (None, "") and ost not in (None, "") and nm:
            parties[(str(kod).strip(), str(ost).strip())] = str(nm).strip()

    def walk(o):
        if isinstance(o, dict):
            add(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    try:
        walk(json.loads(fetch(URL_ROS_JSON).decode("utf-8-sig")))
    except Exception as e:
        print("kvros.json nelze načíst:", e)
    if not parties:
        try:
            raw = fetch(URL_ROS_XML)
            for _, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
                if ln(el.tag).upper().endswith("_ROW"):
                    add(row_dict(el))
                    el.clear()
        except Exception as e:
            print("kvros.xml nelze načíst:", e)
    print("volebních stran v registru:", len(parties))
    return parties


# ---------- kandidáti ----------
def read_elected(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    print("soubory v kvrk.zip:", names)
    member = next((m for m in names if m.lower().endswith(".xml")), None)
    if not member:
        return [], 0
    elected, total = [], 0
    with z.open(member) as f:
        for _, el in ET.iterparse(f, events=("end",)):
            if not ln(el.tag).upper().endswith("_ROW"):
                continue
            total += 1
            d = row_dict(el)
            el.clear()
            if str(d.get("MANDAT", "")).upper() in ("A", "1"):
                elected.append(d)
    return elected, total


def full_name(d):
    parts = [d.get("TITULPRED"), d.get("JMENO"), d.get("PRIJMENI")]
    s = " ".join(p for p in parts if p)
    if d.get("TITULZA"):
        s += ", " + d["TITULZA"]
    return s.strip()


def main():
    os.makedirs(ZDIR, exist_ok=True)
    meta_path = os.path.join(ZDIR, "_meta.json")
    old = load_json(meta_path, {})

    sig = None
    try:
        h = {k.lower(): v for k, v in fetch(URL_KVRK, "HEAD").items()}
        sig = {"lm": h.get("last-modified"), "len": h.get("content-length")}
    except Exception as e:
        print("HEAD selhal:", e)
        if old.get("sig") and not FORCE:
            print("přeskakuji (nelze ověřit změnu)")
            return
    if sig and old.get("sig") == sig and not FORCE:
        print("registr kandidátů beze změny, přeskakuji")
        return

    raw = fetch(URL_KVRK)
    print("staženo MB:", round(len(raw) / 1e6, 1))
    elected, total = read_elected(raw)
    print("kandidátů celkem:", total, "· zvolených (MANDAT=A):", len(elected))
    if not elected:
        print("Registr zatím neobsahuje zvolené (pole MANDAT se plní po zpracování výsledků).")
        return
    print("ukázka řádku:", json.dumps(elected[0], ensure_ascii=False)[:600])

    parties = load_parties()
    shards = {}
    for d in elected:
        kod = str(d.get("KODZASTUP", "")).strip()
        if not kod:
            continue
        ost = str(d.get("OSTRANA", "")).strip()
        order = int(num(d.get("PORADIMAND"), 999)) or 999
        votes = int(num(d.get("POCHLASU"), 0))
        rec = [
            full_name(d),
            int(num(d.get("VEK"), 0)) or None,
            d.get("POVOLANI") or "",
            parties.get((kod, ost), ""),
            votes,
            order,
            d.get("BYDLISTEN") or "",
        ]
        shards.setdefault(kod[:3], {}).setdefault(kod, []).append(rec)

    written = 0
    for sh, councils in shards.items():
        for kod in councils:
            councils[kod].sort(key=lambda r: (r[5], -r[4]))
        text = json.dumps(councils, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        path = os.path.join(ZDIR, sh + ".json")
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    continue
        except FileNotFoundError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        written += 1

    meta = {
        "sig": sig,
        "generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "elected": len(elected),
        "councils": sum(len(c) for c in shards.values()),
        "shards": len(shards),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print(f"zastupitelstev: {meta['councils']}, souborů: {len(shards)}, přepsáno: {written}")


if __name__ == "__main__":
    main()
