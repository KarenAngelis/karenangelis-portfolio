import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
import main


class TrendsTests(unittest.TestCase):
    def setUp(self):
        main._cache.clear()
        self.client = TestClient(main.app)

    def test_country_and_limit_validation(self):
        for query in ("geo=ZZ", "limit=0", "limit=21"):
            self.assertEqual(self.client.get(f"/api/trends?{query}").status_code, 422)

    def test_feed_transformation_and_cache(self):
        content = b'<rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item><title>Python</title><ht:approx_traffic>200+</ht:approx_traffic><pubDate>today</pubDate></item><item><title>Go</title></item></channel></rss>'
        async def get(*args, **kwargs):
            return httpx.Response(200, content=content, request=httpx.Request("GET", "https://trends.google.com"))
        with patch.object(httpx.AsyncClient, "get", side_effect=get) as upstream:
            first = self.client.get("/api/trends?limit=1").json()
            second = self.client.get("/api/trends?limit=2").json()
        self.assertEqual(first["items"][0]["traffic"], "200+")
        self.assertFalse(first["cached"])
        self.assertEqual(len(second["items"]), 2)
        self.assertTrue(second["cached"])
        self.assertEqual(upstream.call_count, 1)

    def test_upstream_failure_is_explained(self):
        with patch.object(httpx.AsyncClient, "get", side_effect=httpx.ConnectError("offline")):
            response = self.client.get("/api/trends")
        self.assertEqual(response.status_code, 502)

    def test_allowed_origin(self):
        response = self.client.get("/health", headers={"Origin": "http://localhost:4173"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:4173")


if __name__ == "__main__":
    unittest.main()
