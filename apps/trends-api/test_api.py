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

    def test_news_requires_topic_and_never_returns_trending(self):
        for params in ({}, {"q": ""}, {"q": "   "}):
            self.assertEqual(self.client.get("/api/news", params=params).status_code, 422)
        response = httpx.Response(200, content=b'<rss><channel><item><title>News</title><link>https://news.google.com/example</link></item></channel></rss>', request=httpx.Request("GET", "https://news.google.com"))
        with patch.object(httpx.AsyncClient, "get", return_value=response):
            result = self.client.get("/api/news", params={"q": "Python"}).json()
        self.assertEqual(result["mode"], "news")
        self.assertNotIn("traffic", result["items"][0])

    def test_topic_search_uses_news_and_keeps_caches_separate(self):
        content = b'<rss><channel><item><title>Python news</title><link>https://news.google.com/articles/example</link><source>Publisher</source></item></channel></rss>'
        async def get(url, **kwargs):
            return httpx.Response(200, content=content, request=httpx.Request("GET", url, params=kwargs["params"]))
        with patch.object(httpx.AsyncClient, "get", side_effect=get) as upstream:
            news = self.client.get("/api/trends", params={"q": "  Python  ", "geo": "US"}).json()
            cached = self.client.get("/api/trends", params={"q": "PYTHON", "geo": "US"}).json()
            different = self.client.get("/api/trends", params={"q": "Go", "geo": "US"}).json()
            trending = self.client.get("/api/trends", params={"geo": "US"}).json()
        self.assertEqual(news["mode"], "news")
        self.assertEqual(news["query"], "Python")
        self.assertEqual(cached["query"], "PYTHON")
        self.assertEqual(news["items"][0]["publisher"], "Publisher")
        self.assertIn("news.google.com/rss/search", news["source"])
        self.assertTrue(cached["cached"])
        self.assertFalse(different["cached"])
        self.assertEqual(trending["mode"], "trending")
        self.assertEqual(upstream.call_count, 3)
        self.assertEqual(upstream.call_args_list[0].kwargs["params"]["hl"], "en-US")

    def test_topic_validation_and_no_results(self):
        self.assertEqual(self.client.get("/api/trends", params={"q": "x" * 101}).status_code, 422)
        self.assertEqual(self.client.get("/api/trends", params={"q": "bad\x00text"}).status_code, 422)
        response = httpx.Response(200, content=b'<rss><channel/></rss>', request=httpx.Request("GET", "https://news.google.com"))
        with patch.object(httpx.AsyncClient, "get", return_value=response):
            result = self.client.get("/api/trends", params={"q": "unusual topic"}).json()
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
