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

    def test_exchange_fallback_normalizes_codes(self):
        from unittest.mock import patch
        import types
        import sys

        class FakeFrame:
            columns = ["code", "name"]
            def __getitem__(self, names): return self
            def to_dict(self, orient):
                self_as_rows = [{"code": i, "name": "示例股票" + str(i)}
                                for i in range(3500)]
                return self_as_rows

        fake_module = types.SimpleNamespace(stock_info_a_code_name=lambda: FakeFrame())
        with patch.dict(sys.modules, {"akshare": fake_module}):
            data = s.collect_from_akshare()
        self.assertEqual(len(data["stocks"]), 3500)
        self.assertEqual(data["stocks"][0]["code"], "000000")
        self.assertEqual(data["scope"], "currently-listed")


if __name__ == "__main__":
    unittest.main()
