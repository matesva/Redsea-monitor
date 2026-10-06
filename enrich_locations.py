#!/usr/bin/env python3
"""Doplní do data.json monitorů pole "locations" (souřadnice) podle článků.
Spouštět PO fetch skriptech, před commitem. Seznam míst je v gazetteer.json.
Výraz končící "$" musí být celé slovo. Existující místa monitoru se nemění;
dříve doplněná (auto) se při každém běhu přepočítají."""
import json, re, sys, os

FILES = ["data.json", "usa/data.json", "europe/data.json",
         "middle-east/data.json", "asia/data.json", "japan/data.json",
         "south-america/data.json"]
NEAR = 2.5  # stupně: bližší místo se bere jako stejné

def compile_terms(terms):
    out = []
    for t in terms:
        exact = t.endswith("$")
        t = t.rstrip("$")
        out.append(re.compile(r"(^|[^a-z])" + re.escape(t) + (r"([^a-z]|$)" if exact else "")))
    return out

def plain(s):
    return re.sub(r"<[^>]*>", " ", s or "")

def enrich(path, gaz):
    if not os.path.exists(path):
        return "chybí"
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    arts = d.get("articles") or []
    base = [l for l in (d.get("locations") or []) if not l.get("auto")]
    texts = [((a.get("title") or "") + " " + plain(a.get("summary"))).lower() for a in arts]
    added = []
    counts = d.get("location_counts") or {}
    for g in gaz:
        n = sum(1 for t in texts if any(r.search(t) for r in g["re"]))
        if not n:
            continue
        en = g["terms"][0].rstrip("$").title()
        if any(abs(l["lat"] - g["lat"]) < NEAR and abs(l["lon"] - g["lon"]) < NEAR
               or str(l.get("key", "")).lower() == en.lower()
               for l in base + added if "lat" in l):
            continue
        added.append({"key": en, "lat": g["lat"], "lon": g["lon"],
                      "name_cs": g["name_cs"], "name_en": en, "auto": True})
        counts[g["name_cs"]] = n
    d["locations"] = base + added
    d["location_counts"] = counts
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return "+%d míst (celkem %d)" % (len(added), len(d["locations"]))

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "gazetteer.json"), encoding="utf-8") as f:
        gaz = json.load(f)
    for g in gaz:
        g["re"] = compile_terms(g["terms"])
    root = sys.argv[1] if len(sys.argv) > 1 else here
    for rel in FILES:
        try:
            print(rel, enrich(os.path.join(root, rel), gaz))
        except Exception as e:  # jeden monitor nesmí shodit celý běh
            print(rel, "CHYBA:", e)

if __name__ == "__main__":
    main()
