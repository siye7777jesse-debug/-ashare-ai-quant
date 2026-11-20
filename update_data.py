"""Fetch closed, unadjusted daily bars and implemented distribution disclosures."""
import datetime as dt
import json
import math
import re
from decimal import Decimal
from pathlib import Path
import tempfile
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent / "data"
SYMBOLS = ("600865", "600838", "000759", "300308", "601138", "600519")
START = "2018-01-01"
ENDPOINT = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
DISTRIBUTIONS = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def closed_through(now=None):
    local = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("Asia/Shanghai"))
    return (local.date() - dt.timedelta(days=int(local.hour < 16))).isoformat()


def request(endpoint, params):
    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                              "Referer": "https://quote.eastmoney.com/"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=18) as response:
                return json.load(response)
        except OSError:
            if attempt:
                raise
            time.sleep(1)


def day(value):
    if not isinstance(value, str) or dt.date.fromisoformat(value).isoformat() != value:
        raise ValueError(f"Invalid ISO date: {value}")
    return value


def parse_bars(data, symbol, end):
    if data.get("code") != symbol or not isinstance(data.get("klines"), list):
        raise ValueError(f"Missing or mismatched response for {symbol}")
    rows, previous = [], ""
    for line in data["klines"]:
        date, op, close, high, low, volume = line.split(",")
        if not START <= day(date) <= end or date <= previous:
            raise ValueError(f"Out-of-range or unordered date {date}")
        op, close, high, low, volume = map(float, (op, close, high, low, volume))
        if (not all(map(math.isfinite, (op, close, high, low, volume))) or low <= 0
                or low > min(op, close) or high < max(op, close) or volume < 0):
            raise ValueError(f"Invalid OHLCV on {date}")
        rows.append(dict(date=date, open=op, high=high, low=low, close=close, volume=volume))
        previous = date
    if len(rows) < 25:
        raise ValueError(f"{symbol}: fewer than 25 daily bars")
    return rows


def fetch(symbol, end=None):
    end = end or closed_through()
    market = "1" if symbol.startswith("6") else "0"
    payload = request(ENDPOINT, dict(secid=f"{market}.{symbol}", klt="101", fqt="0",
                      beg=START.replace("-", ""), end=end.replace("-", ""),
                      fields1="f1,f2,f3,f4,f5,f6", fields2="f51,f52,f53,f54,f55,f56"))
    data = payload.get("data") or {}
    if data.get("market") != int(market):
        raise ValueError("Wrong exchange in history response")
    return dict(symbol=symbol, source="Eastmoney public daily K-line", adjustment="none",
                fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                bars=parse_bars(data, symbol, end))


def parse_actions(payload, symbol, begin, end):
    result = payload.get("result") or {}
    if payload.get("success") is not True or result.get("pages") != 1 or not isinstance(result.get("data"), list) or not result["data"]:
        raise ValueError("Distribution history unavailable or paginated")
    events = {}
    for row in result["data"]:
        if row["SECURITY_CODE"] != symbol:
            raise ValueError("Wrong symbol in distributions")
        if row["ASSIGN_PROGRESS"] != "实施分配":
            continue
        ex_date = day((row.get("EX_DIVIDEND_DATE") or "")[:10])
        if not begin <= ex_date <= end:
            continue
        cash = float(Decimal(str(row.get("PRETAX_BONUS_RMB") or 0)) / 10)
        bonus = float(Decimal(str(row.get("BONUS_IT_RATIO") or 0)) / 10)
        if ex_date in events or not all(math.isfinite(x) and x >= 0 for x in (cash, bonus)) or cash + bonus <= 0:
            raise ValueError(f"Ambiguous distribution on {ex_date}")
        events[ex_date] = dict(date=ex_date, cashPerShare=cash, bonusPerShare=bonus)
    return dict(symbol=symbol, source="Eastmoney RPT_SHAREBONUS_DET", start=begin, end=end,
                events=[events[k] for k in sorted(events)])


def fetch_actions(symbol, begin, end):
    payload = request(DISTRIBUTIONS, dict(reportName="RPT_SHAREBONUS_DET", columns="ALL",
                      filter=f'(SECURITY_CODE="{symbol}")', pageSize=100,
                      sortColumns="EX_DIVIDEND_DATE", sortTypes="-1"))
    history = parse_actions(payload, symbol, begin, end)
    notices = {str(r.get("EX_DIVIDEND_DATE"))[:10]: str(r.get("NOTICE_DATE"))[:10]
               for r in payload["result"]["data"] if r.get("ASSIGN_PROGRESS") == "实施分配"}
    for event in history["events"]:
        if not event["bonusPerShare"]:
            continue
        notice = day(notices[event["date"]])
        url = ("https://vip.stock.finance.sina.com.cn/corp/view/vISSUE_ShareBonusDetail.php?"
               + urllib.parse.urlencode(dict(end_date=notice, stockid=symbol, type=1)))
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                html = response.read().decode("gb18030", errors="replace")
            listing = listing_date(html, event)
        except (OSError, ValueError) as exc:
            print(f"{symbol} {event['date']}: listing detail unavailable: {exc}", flush=True)
            continue
        event.update(listingDate=listing, listingSource=url)
    return history


def listing_date(html, event):
    fields = dict(re.findall(r"<strong>([^<>]+)</strong></td>\s*<td>([^<>]+)</td>", html))
    if fields.get("除息日") != event["date"]:
        raise ValueError("Mismatched ex-date in listing detail")
    def ratio(key):
        val = fields.get(key)
        if val is None:
            raise ValueError("Missing share distribution field")
        return 0 if val == "--" else float(val)
    ratio_sum = ratio("送股比例（10送）") + ratio("转增比例（10转增）")
    if not math.isclose(ratio_sum / 10, event["bonusPerShare"]):
        raise ValueError("Mismatched stock distribution")
    listing = day(fields.get("上市日"))
    if listing < event["date"]:
        raise ValueError("Listing before ex-date")
    return listing


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    Path(tmp.name).replace(path)


def latest_market_session(end):
    # The six scheduled SH/SZ names share the mainland trading calendar.
    begin = dt.date.fromisoformat(end) - dt.timedelta(days=70)
    payload = request(ENDPOINT, dict(secid="1.000001", klt="101", fqt="0",
                      beg=begin.strftime("%Y%m%d"), end=end.replace("-", ""),
                      fields1="f1,f2,f3,f4,f5,f6", fields2="f51,f52,f53,f54,f55,f56"))
    data = payload.get("data") or {}
    if data.get("market") != 1 or data.get("code") != "000001":
        raise ValueError("Invalid Shanghai Composite reference")
    rows = parse_bars(data, "000001", end)
    session = rows[-1]["date"]
    if (dt.date.fromisoformat(end) - dt.date.fromisoformat(session)).days > 12:
        raise ValueError("Market reference is stale")
    return session


def refresh(symbol, end, session=None):
    dataset = fetch(symbol, end)
    if session and dataset["bars"][-1]["date"] != session:
        raise ValueError(f"Last bar differs from market session {session}; verify suspension or stale source")
    path = OUT / f"{symbol}.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    dates = {bar["date"] for bar in dataset["bars"]}
    if any(bar["date"] not in dates for bar in old.get("bars", [])):
        raise ValueError("New response would truncate the previous history")
    actions = fetch_actions(symbol, START, end)
    if any(x["date"] not in dates for x in actions["events"]):
        raise ValueError("Ex-date missing from daily history")
    # Keep the original market-data vintage when the bars are identical.
    old_time = old.get("fetched_at")
    checked = closed_through(dt.datetime.fromisoformat(old_time)) if old_time else ""
    if old.get("bars") != dataset["bars"] or checked < end:
        write_json(path, dataset)
    write_json(OUT / "actions" / path.name, actions)
    print(f"{symbol}: {len(dates)} bars to {max(dates)}, {len(actions['events'])} disclosures", flush=True)


def main():
    end = closed_through()
    session = latest_market_session(end)
    print(f"Latest completed market session: {session}", flush=True)
    failures = []
    for symbol in SYMBOLS:
        try:
            refresh(symbol, end, session)
        except Exception as exc:
            print(f"{symbol}: {exc}", flush=True)
            failures.append(symbol)
    if failures:
        raise SystemExit("Incomplete refresh: " + ", ".join(failures))


if __name__ == "__main__":
    main()
