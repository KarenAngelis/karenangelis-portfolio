"""Interview scheduling requires calendar evidence or literal dated text."""
import base64
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from career.pipeline import Pipeline, calendar_invite
from career.store import Store


def encoded(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def invite_message(*, method="REQUEST", status="CONFIRMED", aware=True, text="Interview invitation.", summary="Entrevista · Example"):
    start = "DTSTART;TZID=America/Sao_Paulo:20261026T100000" if aware else "DTSTART:20261026T100000"
    end = "DTEND;TZID=America/Sao_Paulo:20261026T110000" if aware else "DTEND:20261026T110000"
    ics = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Example//Interview//EN", "METHOD:" + method,
        "BEGIN:VEVENT", "UID:interview-1@example.org", "DTSTAMP:20261022T100000Z", "SUMMARY:" + summary,
        "STATUS:" + status, start, end, "END:VEVENT", "END:VCALENDAR", ""])
    return {"id": "message-1", "threadId": "thread-1", "internalDate": "1000", "snippet": text,
        "payload": {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "text/plain", "body": {"data": encoded(text)}},
            {"mimeType": "text/calendar", "body": {"data": encoded(ics)}},
        ]}}


class CalendarInviteTests(unittest.TestCase):
    def test_confirmed_interview_with_timezone_is_normalized_to_utc(self):
        invitation = calendar_invite(invite_message())
        self.assertEqual(invitation["start"], "2026-10-26T13:00:00+00:00")
        self.assertEqual(invitation["end"], "2026-10-26T14:00:00+00:00")
        self.assertEqual(invitation["time_zone"], "UTC")
        self.assertEqual(invitation["source_message_id"], "message-1")

    def test_floating_calendar_times_are_rejected_without_inventing_timezone(self):
        self.assertIsNone(calendar_invite(invite_message(aware=False)))

    def test_canceled_calendar_and_unrelated_events_are_not_invitations(self):
        self.assertIsNone(calendar_invite(invite_message(method="CANCEL")))
        self.assertIsNone(calendar_invite(invite_message(status="CANCELLED")))
        self.assertIsNone(calendar_invite(invite_message(summary="Team lunch")))


class PipelineCalendarEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="career-calendar-test-")
        self.store = Store(str(Path(self.directory.name) / "career.sqlite3"))
        job = self.store.upsert_job({"source": "test", "external_id": "1", "company": "Example",
            "title": "Python Developer", "url": "https://example.org/jobs/1", "description": "Python. Remote worldwide.", "location": "Worldwide"})
        self.application = self.store.create_application(job["id"], {"status": "sent", "company": "Example",
            "title": "Python Developer", "contact_email": "jobs@example.org", "gmail_thread_id": "thread-1"})
        self.google = SimpleNamespace(create_interview=AsyncMock(return_value={"id": "calendar-1"}))
        self.codex = SimpleNamespace(run_json=AsyncMock())
        self.pipeline = Pipeline(self.store, self.google, self.codex, SimpleNamespace(worker_enabled=False, worker_interval=300))

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    def decision(self, **changes):
        result = {"application_id": self.application["id"], "kind": "interview", "summary": "Interview message.",
            "interview_confirmed": True, "start": "2026-10-26T10:00:00-03:00", "end": "2026-10-26T11:00:00-03:00",
            "time_zone": "America/Sao_Paulo", "evidence": "Interview invitation.", "meeting_url": ""}
        result.update(changes)
        return result

    def plain_message(self, text):
        return {"id": "message-1", "threadId": "thread-1", "internalDate": "1000", "snippet": text,
            "payload": {"mimeType": "text/plain", "body": {"data": encoded(text)}}}

    async def test_verified_ics_can_schedule_using_its_actual_utc_instants(self):
        self.codex.run_json.return_value = self.decision(interview_confirmed=False, start="", end="", time_zone="", evidence="")
        await self.pipeline.process_message(self.application, invite_message())
        self.google.create_interview.assert_awaited_once()
        application_id, details = self.google.create_interview.await_args.args
        self.assertEqual(application_id, self.application["id"])
        self.assertEqual(details["start"], "2026-10-26T13:00:00+00:00")
        self.assertEqual(details["time_zone"], "UTC")
        self.assertEqual(self.store.get_application(application_id)["status"], "interview")
        self.assertEqual(sum(event["kind"] == "interview_created" for event in self.store.list_events()), 1)

    async def test_literal_generic_text_without_dates_does_not_authorize_model_times(self):
        text = "We would like to schedule an interview. What is your availability?"
        self.codex.run_json.return_value = self.decision(evidence=text)
        await self.pipeline.process_message(self.application, self.plain_message(text))
        self.google.create_interview.assert_not_awaited()
        self.assertNotEqual(self.store.get_application(self.application["id"])["status"], "interview")
        self.assertFalse(any(event["kind"] == "interview_created" for event in self.store.list_events()))

    async def test_ics_without_timezone_and_generic_text_never_schedules(self):
        self.codex.run_json.return_value = self.decision()
        await self.pipeline.process_message(self.application, invite_message(aware=False))
        self.google.create_interview.assert_not_awaited()

    async def test_explicit_iso_times_and_timezone_in_literal_text_can_schedule(self):
        text = "Confirmed interview: 2026-10-26T10:00:00-03:00 to 2026-10-26T11:00:00-03:00 America/Sao_Paulo."
        self.codex.run_json.return_value = self.decision(evidence=text)
        await self.pipeline.process_message(self.application, self.plain_message(text))
        self.google.create_interview.assert_awaited_once()

    async def test_canceled_ics_is_never_overridden_by_model_or_text_fallback(self):
        text = "Interview 2026-10-26T10:00:00-03:00 to 2026-10-26T11:00:00-03:00 America/Sao_Paulo was canceled."
        self.codex.run_json.return_value = self.decision(evidence=text)
        await self.pipeline.process_message(self.application, invite_message(method="CANCEL", text=text))
        self.google.create_interview.assert_not_awaited()
        self.assertFalse(any(event["kind"] == "interview_created" for event in self.store.list_events()))

    async def test_cancelled_event_status_is_never_overridden_by_text_fallback(self):
        text = "Interview 2026-10-26T10:00:00-03:00 to 2026-10-26T11:00:00-03:00 America/Sao_Paulo was canceled."
        self.codex.run_json.return_value = self.decision(evidence=text)
        await self.pipeline.process_message(self.application, invite_message(status="CANCELLED", text=text))
        self.google.create_interview.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
