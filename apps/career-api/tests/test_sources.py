"""Public-source adapter contracts; all HTTP traffic uses MockTransport."""
import base64
import unittest

import httpx

from career.sources import fetch_jobs, github_projects, plain, source_spec


class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_greenhouse_normalizes_description_and_uses_public_get_without_credentials(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={"jobs": [{"id": 123, "title": "Python Developer",
                "absolute_url": "https://boards.greenhouse.io/example/jobs/123", "location": {"name": "Remote Brazil"},
                "content": "&lt;p&gt;Python &amp;amp; APIs&lt;/p&gt;&lt;p&gt;Apply: jobs@example.org&lt;/p&gt;"}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            jobs = await fetch_jobs({"kind": "greenhouse", "identifier": "example"}, client=client)
            self.assertFalse(client.is_closed)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["external_id"], "123")
        self.assertEqual(job["source"], "greenhouse:example")
        self.assertEqual(job["location"], "Remote Brazil")
        self.assertEqual(job["description"], "Python & APIs Apply: jobs@example.org")
        self.assertEqual(job["apply_email"], "jobs@example.org")
        self.assertEqual(job["contact_source"], "official_job_description")
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(requests[0].url.host, "boards-api.greenhouse.io")
        self.assertEqual(requests[0].url.path, "/v1/boards/example/jobs")
        self.assertEqual(requests[0].url.params["content"], "true")
        self.assertNotIn("authorization", requests[0].headers)
        self.assertNotIn("cookie", requests[0].headers)
        self.assertNotIn("key", requests[0].url.params)

    async def test_lever_preserves_apply_url_modality_and_refuses_ambiguous_contact(self):
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(200, json=[{"id": "lever-1", "text": "React Developer",
                "hostedUrl": "https://jobs.lever.co/example/lever-1", "applyUrl": "https://jobs.lever.co/example/lever-1/apply",
                "categories": {"location": "Worldwide"}, "workplaceType": "remote",
                "descriptionPlain": "Build React apps. Contact jobs@example.org or team@example.org.",
                "lists": [{"text": "Requirements", "content": "<ul><li>TypeScript</li></ul>"}],
                "additionalPlain": "<p>Remote worldwide.</p>"}])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            jobs = await fetch_jobs({"kind": "lever", "identifier": "example"}, client=client)
        job = jobs[0]
        self.assertEqual(job["title"], "React Developer")
        self.assertEqual(job["workplace_type"], "remote")
        self.assertTrue(job["apply_url"].endswith("/apply"))
        self.assertIn("TypeScript", job["description"])
        self.assertNotIn("<li>", job["description"])
        self.assertNotIn("'content':", job["description"])
        self.assertNotIn("'text':", job["description"])
        self.assertIn("Remote worldwide.", job["description"])
        self.assertIsNone(job["apply_email"])
        self.assertIsNone(job["contact_source"])
        self.assertEqual(requests[0].url.host, "api.lever.co")
        self.assertEqual(requests[0].method, "GET")
        self.assertNotIn("authorization", requests[0].headers)
        self.assertNotIn("cookie", requests[0].headers)
        self.assertEqual(dict(requests[0].url.params), {"mode": "json"})

    async def test_source_identifiers_cannot_redirect_requests_or_traverse_paths(self):
        calls = []
        def handle(request):
            calls.append(request)
            raise AssertionError("An invalid source must be rejected before any request.")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            for identifier in ["../private", "%2e%2e", "example/../../private", "example?key=secret", "https://internal", "example.com", "name#fragment", ""]:
                with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                    await fetch_jobs({"kind": "greenhouse", "identifier": identifier}, client=client)
            with self.assertRaises(ValueError):
                await fetch_jobs({"kind": "arbitrary-http", "identifier": "example"}, client=client)
            with self.assertRaises(ValueError):
                await github_projects("../../private", client=client)
        self.assertEqual(calls, [])
        self.assertEqual(source_spec({"kind": "lever", "identifier": "valid-company_1"}),
                         {"kind": "lever", "identifier": "valid-company_1"})

    async def test_http_errors_and_invalid_collections_are_not_reported_as_jobs(self):
        for response in [httpx.Response(503, json={"error": "unavailable"}),
                         httpx.Response(200, json={"jobs": {"not": "a list"}})]:
            with self.subTest(status=response.status_code):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
                    with self.assertRaises((httpx.HTTPStatusError, ValueError)):
                        await fetch_jobs({"kind": "greenhouse", "identifier": "example"}, client=client)

    async def test_github_metadata_and_readme_are_provenance_not_a_code_audit(self):
        requests = []
        readme = "# Example\nA portfolio prototype; production behavior not verified."
        def handle(request):
            requests.append(request)
            self.assertNotIn("authorization", request.headers)
            self.assertNotIn("cookie", request.headers)
            if request.url.path == "/users/KarenAngelis/repos":
                self.assertEqual(dict(request.url.params), {"per_page": "100", "page": "1", "sort": "updated"})
                return httpx.Response(200, json=[
                    {"name": "example", "html_url": "https://github.com/KarenAngelis/example",
                     "description": "Portfolio project", "language": "Python", "pushed_at": "2026-10-20T10:00:00Z", "fork": False, "archived": False},
                    {"name": "forked", "fork": True, "archived": False},
                    {"name": "archived", "fork": False, "archived": True},
                ])
            self.assertEqual(request.url.path, "/repos/KarenAngelis/example/readme")
            return httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode(readme.encode()).decode()})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            projects = await github_projects("KarenAngelis", client=client)
        self.assertEqual(len(requests), 2)
        self.assertEqual(projects, [{"name": "example", "url": "https://github.com/KarenAngelis/example",
            "description": "Portfolio project", "language": "Python", "updated_at": "2026-10-20T10:00:00Z",
            "source": "github_public_metadata", "readme": readme}])
        for field in ["audited", "production_verified", "tests_passed", "years_experience"]:
            self.assertNotIn(field, projects[0])

    def test_plain_description_has_no_markup_and_is_bounded(self):
        self.assertEqual(plain("<p>Python &amp; SQL</p><ul><li>APIs</li></ul>"), "Python & SQL APIs")
        self.assertEqual(len(plain("x" * 50000)), 40000)


if __name__ == "__main__":
    unittest.main()
