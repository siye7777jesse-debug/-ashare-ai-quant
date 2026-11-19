"""Update the current listed A-share symbol/name directory from public market data.

No private API keys; never replace a valid directory with a partial fetch.
This is a CURRENT listed universe, not a point-in-time historical universe.
"""
import datetime as dt
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://push2.eastmoney.com/api/qt/clist/get"
MARKETS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
OUT = Path(__file__).resolve().parent / "data" / "stocks.json"


def parse_page(payload):
    data = (payload or {}).get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    if not isinstance(diff, list):
        raise ValueError("Unexpected stock list format")
    items = []
    for row in diff:
        if not isinstance(row, dict):
            continue
        code = str(row.get("f12") or "").strip()
        name = str(row.get("f14") or "").strip()
        if len(code) == 6 and code.isdigit() and name and name != "-" and len(name) <= 40:
            items.append({"code": code, "name": name})
    return items, int(data.get("total") or 0)


def fetch_page(page, page_size=1000):
    args = urllib.parse.urlencode({
        "pn": page, "pz": page_size, "po": 1, "np": 1,
        "fltt": 2, "invt": 2, "fid": "f12",
        "fs": MARKETS, "fields": "f12,f14",
    })
    req = urllib.request.Request(
        ENDPOINT + "?" + args,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return parse_page(json.load(resp))


def collect(fetcher=fetch_page, min_count=1000):
    stocks, total = [], None
    for page in range(1, 25):
        entries, count = fetcher(page)
        if page == 1:
            total = count
            if total < min_count or total > 15000:
                raise ValueError(f"Suspicious public market stock count: {total}")
        if not entries:
            raise ValueError(f"Empty stock directory page {page}")
        stocks.extend(entries)
        if len(stocks) >= total:
            break
        time.sleep(0.25)
    seen = {}
    for item in stocks:
        seen[item["code"]] = item["name"]
    if len(seen) < min_count or len(seen) < total * 0.95:
        raise ValueError(f"Incomplete symbol directory: {len(seen)} of {total}")
    return {
        "source": "Eastmoney public A-share listing",
        "scope": "currently-listed",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stocks": [{"code": code, "name": seen[code]} for code in sorted(seen)],
    }



def collect_from_akshare():
    """Use AKShare's exchange disclosures if Eastmoney's all-stock list is blocked."""
    import akshare as ak
    frame = ak.stock_info_a_code_name()
    if not {"code", "name"}.issubset(set(frame.columns)):
        raise ValueError("AKShare stock directory schema changed")
    seen = {}
    for row in frame[["code", "name"]].to_dict(orient="records"):
        code = str(row["code"]).split(".")[0].strip().zfill(6)
        name = str(row["name"]).strip()
        if len(code) == 6 and code.isdigit() and name and name.lower() != "nan":
            seen[code] = name
    if len(seen) < 3500:
        raise ValueError(f"AKShare exchange directory too small: {len(seen)}")
    return {
        "source": "AKShare / Shanghai, Shenzhen and Beijing exchange listings",
        "scope": "currently-listed",
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stocks": [{"code": code, "name": seen[code]} for code in sorted(seen)],
    }


def main():
    try:
        payload = collect()
    except Exception as primary_error:
        print("Primary public symbol listing unavailable:", primary_error)
        payload = collect_from_akshare()
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Updated {OUT} with {len(payload['stocks'])} current listed A-shares.")


if __name__ == "__main__":
    main()
