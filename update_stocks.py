"""Build a searchable directory from a complete listing or a labelled disclosure index."""
import datetime as dt
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://push2.eastmoney.com/api/qt/clist/get"
CNINFO = "https://www.cninfo.com.cn/new/data/szse_stock.json"
MARKETS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
OUT = Path(__file__).resolve().parent / "data" / "stocks.json"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def entry(code, name):
    if isinstance(code, str) and re.fullmatch(r"[0-9]{6}", code) and isinstance(name, str):
        if name.strip() not in ("", "-") and len(name) <= 40:
            return {"code": code, "name": name.strip()}
    return None


def parse_page(payload):
    data = payload.get("data") or {}
    diff = data.get("diff")
    if isinstance(diff, dict):
        diff = list(diff.values())
    if not isinstance(diff, list):
        raise ValueError("Unexpected stock list format")
    rows = [entry(row.get("f12"), row.get("f14")) for row in diff]
    return [row for row in rows if row], int(data["total"])


def fetch_page(page):
    args = urllib.parse.urlencode(dict(pn=page, pz=100, po=1, np=1, fltt=2,
                                       invt=2, fid="f12", fs=MARKETS, fields="f12,f14"))
    return parse_page(get(ENDPOINT + "?" + args))


def directory(rows, source, scope):
    return {"source": source, "scope": scope,
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "stocks": sorted(rows, key=lambda item: item["code"])}


def collect(fetcher=fetch_page, min_count=3500):
    stocks, total = {}, None
    for page in range(1, 151):
        entries, count = fetcher(page)
        if total is None:
            total = count
        if not min_count <= total <= 15000 or count != total or not entries:
            raise ValueError(f"Inconsistent listing size at page {page}")
        for row in entries:
            if row["code"] in stocks:
                raise ValueError(f"Duplicate stock on page {page}")
            stocks[row["code"]] = row
        if len(stocks) == total:
            return directory(stocks.values(), "东方财富 A股行情检索目录", "quote-search-index")
        if len(stocks) > total:
            break
        time.sleep(0.1)
    raise ValueError(f"Incomplete symbol directory: {len(stocks)} of {total}")


def from_cninfo(payload):
    # Includes former codes and some delisted issuers. Never label this a live universe.
    rows = [entry(x["code"], x["zwjc"]) for x in payload["stockList"] if x["category"] == "A股"]
    if None in rows or len({x["code"] for x in rows}) != len(rows):
        raise ValueError("Invalid or duplicate CNINFO A-share record")
    if not all(any(x["code"].startswith(prefix) for x in rows) for prefix in ("60", "00", "92")) or len(rows) < 3500:
        raise ValueError("Incomplete CNINFO disclosure directory")
    return directory(rows, "巨潮资讯 A股信息披露检索目录", "disclosure-index")


def main():
    try:
        payload = collect()
    except Exception as exc:
        print(f"Eastmoney directory unavailable: {exc}. Trying CNINFO.", flush=True)
        payload = from_cninfo(get(CNINFO))
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    print(f"{payload['scope']}: {len(payload['stocks'])} symbols", flush=True)


if __name__ == "__main__":
    main()
