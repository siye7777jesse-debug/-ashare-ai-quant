import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_data as d


class DataTests(unittest.TestCase):
    def setUp(self):
        self.lines = [f"2024-01-{n:02d},10,10.5,11,9.5,1000" for n in range(1,27)]

    def fetch(self, code="600865"):
        payload = dict(data=dict(code=code, klines=self.lines))
        with patch.object(d, "request", return_value=payload) as request:
            data = d.fetch(code, "2024-01-31")
            self.assertEqual(request.call_args.args[1]["secid"], ("1." if code.startswith("6") else "0.") + code)
        return data

    def test_public_schema_and_market(self):
        for code in ("600865","920001"):
            value = self.fetch(code)
            self.assertEqual(len(value["bars"]),26)
            self.assertEqual(value["adjustment"],"none")

    def test_reject_corrupt_responses(self):
        for code, lines in [("999999",self.lines),("600865",[]),("600865",self.lines[::-1]),
                            ("600865",self.lines+[self.lines[-1]])]:
            with self.subTest(code=code, count=len(lines)), self.assertRaises(ValueError):
                d.parse_bars(dict(code=code,klines=lines),"600865","2024-01-31")
        for last in ["2024-02-30,1,1,1,1,1","2024-01-27,NaN,1,1,1,1","2024-01-27,1,1,1,1,inf",
                     "2025-01-27,1,1,1,1,1","2024-01-27,1,2,1,1,1"]:
            with self.subTest(last=last), self.assertRaises(ValueError):
                d.parse_bars(dict(code="600865",klines=self.lines+[last]),"600865","2024-01-31")

    def test_failure_with_existing_cache_and_shorter_overlap(self):
        dataset=self.fetch()
        with tempfile.TemporaryDirectory() as tmp, patch.object(d,"OUT",Path(tmp)):
            path=d.OUT/"600865.json"
            d.write_json(path,dataset)
            original=path.read_bytes()
            shortened=copy.deepcopy(dataset)
            del shortened["bars"][12]
            with patch.object(d,"fetch",return_value=shortened), self.assertRaisesRegex(ValueError,"truncate"):
                d.refresh("600865","2024-01-31")
            with patch.object(d,"latest_market_session",return_value="2024-01-26"), patch.object(d,"refresh",side_effect=OSError("offline")), self.assertRaises(SystemExit):
                d.main()
            self.assertEqual(original,path.read_bytes())

    def test_closed_session_boundary(self):
        for utc, expected in [(7,"2024-01-01"),(8,"2024-01-02")]:
            t=dt.datetime(2024,1,2,utc,tzinfo=dt.timezone.utc)
            self.assertEqual(d.closed_through(t),expected)

    def test_only_implemented_dated_events(self):
        row=dict(SECURITY_CODE="300308",ASSIGN_PROGRESS="实施分配",EX_DIVIDEND_DATE="2024-06-06",
                 PRETAX_BONUS_RMB=4.5,BONUS_IT_RATIO=4)
        payload=dict(success=True,result=dict(pages=1,data=[row,{**row,"ASSIGN_PROGRESS":"预披露"}]))
        def parse(): return d.parse_actions(payload,"300308","2024-01-01","2024-12-31")
        self.assertEqual(parse()["events"],[dict(date="2024-06-06",cashPerShare=.45,bonusPerShare=.4)])
        payload["result"]["data"].append(row)
        with self.assertRaises(ValueError): parse()
        payload["result"]["pages"]=2
        with self.assertRaises(ValueError): parse()

    def test_real_committed_bundles(self):
        for symbol in d.SYMBOLS:
            ds=json.loads((d.OUT/f"{symbol}.json").read_text())
            act=json.loads((d.OUT/"actions"/f"{symbol}.json").read_text())
            self.assertEqual((ds["symbol"],ds["adjustment"],act["symbol"]),(symbol,"none",symbol))
            dates=[b["date"] for b in ds["bars"]]
            self.assertEqual(dates,sorted(set(dates)))
            self.assertGreaterEqual(act["end"],dates[-1])
            self.assertTrue(all(e["date"] in dates for e in act["events"]))

if __name__ == "__main__":
    unittest.main()
