"""Critical workflow tests: real SQLite state, mocked external services only."""
import base64
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from career.pipeline import Pipeline
from career.store import Store


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.directory.name) / "career.sqlite3"))
        self.profile = self.store.save_profile({
            "name": "Candidate", "skills": ["Python"],
            "facts": {"residence_country": "BR"},
            "preferences": {"roles": ["Python Developer"], "countries": [], "remote_only": True,
                            "min_score": 70, "auto_apply": True},
        })
        self.job = self.store.upsert_job({
            "source": "test:official", "external_id": "job-1", "company": "Example",
            "title": "Python Developer", "url": "https://example.com/jobs/1",
            "description": "Python. Remote worldwide. Apply at jobs@example.com.",
            "location": "Worldwide", "apply_email": "jobs@example.com", "contact_source": "official_job_description",
        })
        self.application = self.store.create_application(self.job["id"], {
            "status": "ready", "company": "Example", "title": "Python Developer",
            "contact_email": "jobs@example.com", "email_subject": "Python Developer",
            "email_body": "My application based on my verified experience.",
        })
        self.google = SimpleNamespace(
            status=AsyncMock(return_value={"gmail_connected": True, "calendar_connected": True}),
            search_messages=AsyncMock(return_value=[]),
            send_application=AsyncMock(return_value={"message_id": "sent-1", "thread_id": "thread-1"}),
            create_interview=AsyncMock(return_value={"id": "event-1", "htmlLink": "https://calendar.google.com/event/1"}),
        )
        self.codex = SimpleNamespace(status=AsyncMock(return_value={"connected": True}), run_json=AsyncMock())
        self.pipeline = Pipeline(self.store, self.google, self.codex, SimpleNamespace(worker_enabled=False, worker_interval=300))

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    def change_policy(self, **changes):
        profile = self.store.get_profile()
        profile["preferences"].update(changes)
        self.store.save_profile(profile)

    def mail(self, text="Confirmed interview from 2026-10-26T10:00:00-03:00 to 2026-10-26T11:00:00-03:00 America/Sao_Paulo."):
        self.store.update_application(self.application["id"], {"status": "sent", "gmail_thread_id": "thread-1", "gmail_message_id": "sent-1"})
        return {"id": "reply-1", "threadId": "thread-1", "snippet": text,
                "payload": {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")}}}

    def decision(self, **changes):
        value = {"application_id": self.application["id"], "kind": "interview", "summary": "Interview confirmed.",
                 "interview_confirmed": True, "start": "2026-10-26T10:00:00-03:00",
                 "end": "2026-10-26T11:00:00-03:00", "time_zone": "America/Sao_Paulo",
                 "evidence": "Confirmed interview from 2026-10-26T10:00:00-03:00 to 2026-10-26T11:00:00-03:00 America/Sao_Paulo.", "meeting_url": ""}
        value.update(changes)
        return value

    async def test_auto_apply_false_does_not_send_in_worker_or_direct_method(self):
        self.change_policy(auto_apply=False)
        result = await self.pipeline.run()
        self.assertEqual(result["sent"], 0)
        self.assertFalse(await self.pipeline.send(self.application))
        self.google.send_application.assert_not_awaited()
        self.google.search_messages.assert_not_awaited()
        self.assertEqual(self.store.get_application(self.application["id"])["status"], "ready")

    async def test_shared_gmail_hourly_quota_prevents_send(self):
        self.google.search_messages.return_value = [{"id": str(i)} for i in range(20)]
        self.assertFalse(await self.pipeline.send(self.application))
        self.google.send_application.assert_not_awaited()
        self.assertIn("cota", self.store.get_application(self.application["id"])["next_action"])
        query = self.google.search_messages.await_args.args[0]
        self.assertRegex(query, r"^in:sent after:\d+$")

    async def test_previous_contact_prevents_equivalent_new_application(self):
        async def messages(query, **kwargs):
            return [] if query.startswith("in:sent after:") else [{"id": "older-contact"}]
        self.google.search_messages.side_effect = messages
        self.assertFalse(await self.pipeline.send(self.application))
        self.google.send_application.assert_not_awaited()
        self.assertEqual(self.store.get_application(self.application["id"])["status"], "existing_contact")

    async def test_timeout_is_uncertain_and_next_worker_run_does_not_resend(self):
        self.google.send_application.side_effect = TimeoutError("uncertain upstream result")
        with self.assertRaises(TimeoutError):
            await self.pipeline.send(self.application)
        self.assertEqual(self.store.get_application(self.application["id"])["status"], "send_uncertain")
        result = await self.pipeline.run()
        self.assertEqual(result["sent"], 0)
        self.assertEqual(self.google.send_application.await_count, 1)
        self.assertFalse(any(event["kind"] == "application.sent" for event in self.store.list_events()))

    async def test_direct_call_must_not_resend_uncertain_or_sent_state(self):
        # Guards future endpoint callers as well as the worker's status filter.
        for status in ("send_uncertain", "sent", "sending", "closed", "rejected"):
            self.store.update_application(self.application["id"], {"status": status})
            self.assertFalse(await self.pipeline.send(self.application), status)
        self.google.send_application.assert_not_awaited()

    async def test_confirmed_interview_with_timezone_creates_one_event(self):
        self.google.search_messages.return_value = [self.mail()]
        self.codex.run_json.return_value = self.decision()
        self.assertEqual((await self.pipeline.sync_mail())["processed"], 1)
        self.assertEqual((await self.pipeline.sync_mail())["processed"], 0)
        self.google.create_interview.assert_awaited_once()
        self.codex.run_json.assert_awaited_once()
        application_id, event = self.google.create_interview.await_args.args
        self.assertEqual(application_id, self.application["id"])
        self.assertEqual(event["time_zone"], "America/Sao_Paulo")
        self.assertEqual(event["source_message_id"], "reply-1")
        self.assertEqual(self.store.get_application(self.application["id"])["status"], "interview")
        events = [item for item in self.store.list_events() if item["kind"] == "interview_created"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_key"], "calendar:event-1")

    async def test_request_for_availability_does_not_create_interview(self):
        body = "Thank you. What times are you available next week?"
        self.google.search_messages.return_value = [self.mail(body)]
        self.codex.run_json.return_value = self.decision(kind="interested", interview_confirmed=False,
            summary="Recruiter requested availability.", start="", end="", time_zone="", evidence="")
        self.assertEqual((await self.pipeline.sync_mail())["processed"], 1)
        self.google.create_interview.assert_not_awaited()
        self.assertEqual(self.store.get_application(self.application["id"])["status"], "interested")

    async def test_interview_without_literal_evidence_is_not_scheduled(self):
        self.google.search_messages.return_value = [self.mail("Would you like to interview?")]
        self.codex.run_json.return_value = self.decision(evidence="Not present in the actual email")
        await self.pipeline.sync_mail()
        self.google.create_interview.assert_not_awaited()

    async def test_naive_interview_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.pipeline.add_interview(self.application["id"], {
                "title": "Interview", "start": "2026-10-26T10:00:00", "end": "2026-10-26T11:00:00",
                "time_zone": "America/Sao_Paulo",
            })
        self.google.create_interview.assert_not_awaited()

    async def test_unrelated_thread_is_never_classified(self):
        mail = self.mail()
        mail["threadId"] = "unrelated-thread"
        self.google.search_messages.return_value = [mail]
        self.assertEqual((await self.pipeline.sync_mail())["processed"], 0)
        self.codex.run_json.assert_not_awaited()
        self.google.create_interview.assert_not_awaited()

    async def test_successful_send_records_receipt_and_persistent_timeline(self):
        self.assertTrue(await self.pipeline.send(self.application))
        saved = self.store.get_application(self.application["id"])
        self.assertEqual(saved["status"], "sent")
        self.assertEqual(saved["gmail_message_id"], "sent-1")
        self.assertEqual(saved["gmail_thread_id"], "thread-1")
        events = [item for item in self.store.list_events() if item["kind"] == "application.sent"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detail"]["message_id"], "sent-1")

    async def test_preparation_uses_updated_cv_and_preserves_creation_snapshot(self):
        old = self.store.get_application(self.application["id"])["snapshot"]
        profile = self.store.get_profile()
        profile["resume_text"] = "Updated verified CV"
        current = self.store.save_profile(profile)
        self.codex.run_json.return_value = {
            "eligible": True, "reason": "Technical and geographic requirements confirmed.",
            "missing_required": [], "location_evidence": "Remote worldwide",
            "subject": "Current profile", "body": "Application based on the updated CV.",
        }
        result = await self.pipeline.prepare(self.application["id"])
        context = self.codex.run_json.await_args.args[1]
        self.assertEqual(context["profile"]["resume_text"], "Updated verified CV")
        self.assertEqual(result["prepared_profile_revision"], current["revision"])
        self.assertEqual(result["snapshot"], old)
        self.assertEqual(result["prepared_snapshot"]["profile"]["resume_text"], "Updated verified CV")

    async def test_changed_profile_invalidates_ready_message_before_send(self):
        profile = self.store.get_profile()
        stale = self.store.update_application(self.application["id"], {"prepared_profile_revision": profile["revision"]})
        self.store.save_profile({**profile, "resume_text": "New facts"})
        self.assertFalse(await self.pipeline.send(stale))
        self.google.send_application.assert_not_awaited()
        self.assertEqual(self.store.get_application(stale["id"])["status"], "needs_information")


if __name__ == "__main__":
    unittest.main()
