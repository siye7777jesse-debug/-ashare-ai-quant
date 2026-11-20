"""Offline tests for current listed-symbol directory."""
import unittest
import update_stocks as s


class TestDirectory(unittest.TestCase):
    def test_parse_fields_and_names(self):
        rows, count = s.parse_page({"data": {"total": 2, "diff": [
            {"f12": "000759", "f14": "中百集团"},
            {"f12": "600838", "f14": "上海九百"},
            {"f12": "ABC", "f14": "Bad"},
        ]}})
        self.assertEqual(count, 2)
        self.assertEqual(rows, [
            {"code": "000759", "name": "中百集团"},
            {"code": "600838", "name": "上海九百"},
        ])

    def test_paged_directory_and_sort(self):
        def fake(page):
            return (([{"code": "600838", "name": "上海九百"}, {"code": "000759", "name": "中百集团"}], 4)
                    if page == 1 else ([{"code": "300308", "name": "中际旭创"}, {"code": "601138", "name": "工业富联"}], 4))
        result = s.collect(fake, min_count=2)
        self.assertEqual([r["code"] for r in result["stocks"]],
                         ["000759", "300308", "600838", "601138"])
        self.assertEqual(result["scope"], "currently-listed")

    def test_incomplete_list_rejected(self):
        with self.assertRaises(ValueError):
            s.collect(lambda p: ([{"code": "600838", "name": "上海九百"}], 2000), min_count=2)

    def test_invalid_payload(self):
        with self.assertRaises(ValueError):
            s.parse_page({"data": {"diff": "oops", "total": 10}})

    def test_committed_directory(self):
        import json
        d=json.loads(s.OUT.read_text())
        rows=d["stocks"]
        self.assertIn(d["scope"],("currently-listed","disclosure-index"))
        self.assertGreaterEqual(len(rows),3500)
        self.assertEqual(len(rows),len({r["code"] for r in rows}))
        self.assertTrue(all(s.entry(r["code"],r["name"]) for r in rows))
        self.assertIn("600519",{r["code"] for r in rows})

    def test_inconsistent_total_rejected(self):
        with self.assertRaises(ValueError):
            s.collect(lambda p: ([{"code": str(p).zfill(6), "name":"样本"}], 3 if p==1 else 4), min_count=2)

    def test_fallback_filters_asset_class_and_labels_scope(self):
        rows=[{"category":"A股","code":str(i).zfill(6),"zwjc":"名称"+str(i)} for i in range(3500)]
        rows += [dict(category="A股",code="600838",zwjc="上海九百"),dict(category="A股",code="920001",zwjc="样本"),
                 dict(category="B股",code="900901",zwjc="B股")]
        result=s.from_cninfo({"stockList":rows})
        self.assertEqual(result["scope"],"disclosure-index")
        self.assertEqual(len(result["stocks"]),3502)
        with self.assertRaises(ValueError): s.from_cninfo({"stockList":rows+rows[:1]})

if __name__ == "__main__":
    unittest.main()
