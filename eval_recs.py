import os, re, json, bisect, time, subprocess, datetime, urllib.parse, urllib.request

DAYS_BACK = 120
HORIZONS = (7, 30)
BAND = {7: 2.0, 30: 5.0}  # HOLD = úspěch, když se cena pohnula o méně (v %)
OUT = "uspesnost/results.json"

MONITORS = [
    ("Rudé moře", "data.json"),
    ("USA", "usa/data.json"),
    ("Evropa", "europe/data.json"),
    ("Blízký východ", "middle-east/data.json"),
    ("Čína a Asie", "asia/data.json"),
    ("Japonsko", "japan/data.json"),
]

# název v textu sektoru -> symbol na Yahoo Finance (doplňuj podle potřeby)
SYMBOLS = {
    "TSMC": "TSM", "Samsung": "005930.KS", "ASML": "ASML",
    "FXI": "FXI", "MCHI": "MCHI", "Nikkei 225": "^N225", "Nikkei": "^N225",
    "Hang Seng": "^HSI", "S&P 500": "^GSPC", "Nasdaq": "^IXIC", "DAX": "^GDAXI",
    "Lockheed Martin": "LMT", "RTX": "RTX", "Mitsubishi Heavy": "7011.T",
    "BAE Systems": "BA.L", "Rheinmetall": "RHM.DE", "Northrop Grumman": "NOC",
    "ČEZ": "CEZ.PR", "Komerční banka": "KOMB.PR", "Erste Group": "EBS.VI",
    "Maersk": "MAERSK-B.CO", "Hapag-Lloyd": "HLAG.DE", "ZIM": "ZIM",
    "Shell": "SHEL", "BP": "BP", "Chevron": "CVX", "Exxon": "XOM",
    "TotalEnergies": "TTE.PA", "Volvo": "VOLV-B.ST", "BMW": "BMW.DE",
    "Airbus": "AIR.PA", "Allianz": "ALV.DE",
    "Brent": "BZ=F", "WTI": "CL=F", "Zlato": "GC=F",
    "Toyota": "7203.T", "Sony": "6758.T", "SoftBank": "9984.T",
    "Alibaba": "BABA", "Tencent": "0700.HK",
    "Nvidia": "NVDA", "Apple": "AAPL", "Microsoft": "MSFT",
}

CACHE = {}


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True, text=True).stdout


def history(path):
    shas = git("log", "--since=%d days ago" % DAYS_BACK, "--format=%H", "--", path).split()
    for sha in shas:
        raw = git("show", "%s:%s" % (sha, path))
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if isinstance(d, dict):
            yield d


def recs_from(d):
    date = str(d.get("last_updated", ""))[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return []
    out = []
    for r in (d.get("assessment") or {}).get("recommendations") or []:
        sector = r.get("sector_cs") or r.get("sector") or r.get("sector_en") or ""
        act = str(r.get("action", "")).split(" ")[0].split("/")[0].strip().upper()
        if sector and act in ("BUY", "SELL", "HOLD"):
            out.append((date, sector, act))
    return out


def tickers_of(sector):
    found = []
    for name, sym in SYMBOLS.items():
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(name), sector) and sym not in found:
            found.append(sym)
    return found


def prices(sym):
    if sym in CACHE:
        return CACHE[sym]
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1y&interval=1d"
           % urllib.parse.quote(sym))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept": "application/json"})
    series = {}
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        res = d["chart"]["result"][0]
        for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
            if c is not None:
                series[datetime.datetime.utcfromtimestamp(t).date().isoformat()] = float(c)
    except Exception as ex:
        print("cena nelze stáhnout:", sym, str(ex)[:80])
    time.sleep(0.4)
    CACHE[sym] = (sorted(series), series)
    return CACHE[sym]


def px(dates, series, day):
    i = bisect.bisect_left(dates, day)
    if i >= len(dates):
        return None
    return dates[i], series[dates[i]]


def sector_return(tickers, date, h, today):
    d0 = datetime.date.fromisoformat(date)
    target = d0 + datetime.timedelta(days=h)
    if target > today:
        return None
    rets = []
    for sym in tickers:
        dates, series = prices(sym)
        a = px(dates, series, d0.isoformat())
        b = px(dates, series, target.isoformat())
        if not a or not b:
            continue
        if (datetime.date.fromisoformat(a[0]) - d0).days > 5:
            continue
        if (datetime.date.fromisoformat(b[0]) - target).days > 5:
            continue
        rets.append((b[1] / a[1] - 1) * 100)
    return round(sum(rets) / len(rets), 2) if rets else None


def verdict(action, ret, h):
    if ret is None:
        return None
    if action == "BUY":
        return ret > 0
    if action == "SELL":
        return ret < 0
    return abs(ret) <= BAND[h]


def agg(pairs):
    n = len(pairs)
    ok = sum(1 for o, _ in pairs if o)
    avg = round(sum(r for _, r in pairs) / n, 2) if n else None
    return {"n": n, "ok": ok, "avg": avg}


def main():
    today = datetime.date.today()
    signals, unknown = [], set()

    for mon, path in MONITORS:
        per = {}
        for d in history(path):
            for date, sector, act in recs_from(d):
                per.setdefault(sector, {}).setdefault(date, act)
        for sector, days in per.items():
            tick = tickers_of(sector)
            if not tick:
                unknown.add("%s: %s" % (mon, sector))
                continue
            prev_act, prev_date = None, None
            for date in sorted(days):
                act = days[date]
                gap = (datetime.date.fromisoformat(date) - prev_date).days if prev_date else 99
                if act != prev_act or gap > 3:
                    signals.append({"monitor": mon, "sector": sector, "action": act,
                                    "date": date, "tickers": tick})
                prev_act, prev_date = act, datetime.date.fromisoformat(date)

    for s in signals:
        for h in HORIZONS:
            ret = sector_return(s["tickers"], s["date"], h, today)
            s["ret%d" % h] = ret
            s["ok%d" % h] = verdict(s["action"], ret, h)

    summary, by_mon = {}, {}
    for h in HORIZONS:
        k = str(h)
        buckets = {"ALL": [], "BUY": [], "SELL": [], "HOLD": []}
        for s in signals:
            o, r = s.get("ok%d" % h), s.get("ret%d" % h)
            if o is None:
                continue
            buckets["ALL"].append((o, r))
            buckets[s["action"]].append((o, r))
            by_mon.setdefault(s["monitor"], {}).setdefault(k, []).append((o, r))
        summary[k] = {name: agg(v) for name, v in buckets.items()}
    by_monitor = {m: {k: agg(v) for k, v in d.items()} for m, d in by_mon.items()}

    signals.sort(key=lambda s: s["date"], reverse=True)
    out = {
        "updated": datetime.datetime.utcnow().isoformat(timespec="minutes"),
        "band": BAND,
        "signals_total": len(signals),
        "summary": summary,
        "by_monitor": by_monitor,
        "signals": signals[:80],
        "unknown": sorted(unknown),
    }
    os.makedirs("uspesnost", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("Signálů:", len(signals), "| bez rozpoznaných titulů:", len(unknown))
    for h in HORIZONS:
        a = summary[str(h)]["ALL"]
        print("%d dní: %d/%d úspěšných, ø %s %%" % (h, a["ok"], a["n"], a["avg"]))
    for u in sorted(unknown):
        print("  neznámý sektor ->", u)


if __name__ == "__main__":
    main()
