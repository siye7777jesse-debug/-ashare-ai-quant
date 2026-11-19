"""Offline tests: never substitute fabricated prices for production data."""
import unittest
from unittest.mock import patch
import io
import json
import update_data

class DataTests(unittest.TestCase):
    def test_parse_public_kline(self):
        payload = {"data": {"klines": [
            f"2024-01-{day:02d},10,10.5,11,9.5,1000" for day in range(1, 27)
        ]}}
        class Response:
            def __enter__(self): return io.BytesIO(json.dumps(payload).encode())
            def __exit__(self, *args): return False
        with patch("urllib.request.urlopen", return_value=Response()):
            data = update_data.fetch("600865")
        self.assertEqual(len(data["bars"]), 26)
        self.assertEqual(data["bars"][0]["open"], 10.0)
        self.assertEqual(data["adjustment"], "none")

    def test_empty_response_rejected(self):
        class Response:
            def __enter__(self): return io.BytesIO(b'{"data":{"klines":[]}}')
            def __exit__(self, *args): return False
        with patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(ValueError):
                update_data.fetch("600865")


    def test_beijing_stock_uses_market_zero(self):
        payload = {"data": {"klines": [
            f"2024-01-{day:02d},10,10.5,11,9.5,1000" for day in range(1, 27)
        ]}}
        class Response:
            def __enter__(self): return io.BytesIO(json.dumps(payload).encode())
            def __exit__(self, *args): return False
        with patch("urllib.request.urlopen", return_value=Response()) as mock:
            update_data.fetch("920001")
        request = mock.call_args.args[0]
        self.assertIn("secid=0.920001", request.full_url)

if __name__ == "__main__":
    unittest.main()
