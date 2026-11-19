"""Download free public daily A-share bars for the static website."""
import datetime as dt
import json
import pathlib
import time
import urllib.parse
import urllib.request

OUT = pathlib.Path(__file__).parent / "data"
SYMBOLS = ("600865", "600838", "000759", "300308", "601138", "600519")
ENDPOINT = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

def fetch(symbol):
    market = "1" if symbol[0] in "56" else "0"
    params = urllib.parse.urlencode({
        "secid": f"{market}.{symbol}", "klt": "101", "fqt": "0",
        "beg": "20180101", "end": dt.date.today().strftime("%Y%m%d"),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56",
    })
    request = urllib.request.Request(ENDPOINT + "?" + params,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    klines = (payload.get("data") or {}).get("klines") or []
    rows = []
    for line in klines:
        fields = line.split(",")
        if len(fields) < 6:
            continue
        try:
            date = fields[0]
            op, close, high, low, volume = map(float, fields[1:6])
            if min(op, close, high, low) <= 0 or volume < 0 or high < max(op, close, low) or low > min(op, close, high):
                continue
            rows.append({"date": date, "open": op, "high": high, "low": low,
                         "close": close, "volume": volume})
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r["date"])
    if len(rows) < 25:
        raise ValueError(f"{symbol}: fewer than 25 valid daily bars")
    return {"symbol": symbol, "source": "Eastmoney public daily K-line",
            "adjustment": "none",
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "bars": rows}

def main():
    OUT.mkdir(exist_ok=True)
    success = 0
    for symbol in SYMBOLS:
        try:
            dataset = fetch(symbol)
            (OUT / f"{symbol}.json").write_text(
                json.dumps(dataset, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
            print(symbol, len(dataset["bars"]))
            success += 1
        except Exception as exc:
            print(f"WARNING {symbol}: {exc}")
        time.sleep(1)
    if not success and not any(OUT.glob("*.json")):
        raise SystemExit("No real data available; refusing to fabricate data")

if __name__ == "__main__":
    main()
