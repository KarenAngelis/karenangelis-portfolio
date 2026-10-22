import concurrent.futures
from contextvars import copy_context
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from career.matching import evaluate
from career.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "career.sqlite3")
        self.store = Store(self.path)
        self.others = []

    def tearDown(self):
        self.store.close()
        for store in self.others:
            store.close()
        self.temp.cleanup()

    def job(self, **changes):
        return self.store.upsert_job({"source": "manual", "external_id": "job-1", "company": "Example",
            "title": "Python Developer", "url": "https://example.org/jobs/1", "description": "Python, PostgreSQL",
            "location": "Remote Brazil", "apply_email": "jobs@example.org", **changes})

    def worker_stores(self, count=6):
        stores = [Store(self.path) for _ in range(count)]
        self.others.extend(stores)
        return stores

    def test_job_deduplication_across_concurrent_connections(self):
        stores = self.worker_stores()
        barrier = threading.Barrier(len(stores))
        def create(store):
            barrier.wait()
            return store.upsert_job({"source": "Manual", "external_id": "same", "title": "Python"})
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(stores)) as pool:
            result = list(pool.map(create, stores))
        self.assertEqual(len({item["id"] for item in result}), 1)
        self.assertEqual(len(self.store.list_jobs()), 1)

    def test_application_deduplication_is_atomic_with_creation_event(self):
        job = self.job()
        stores = self.worker_stores()
        barrier = threading.Barrier(len(stores))
        def create(store):
            barrier.wait()
            return store.create_application(job["id"], {"status": "prepared"})
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(stores)) as pool:
            result = list(pool.map(create, stores))
        self.assertEqual(len({item["id"] for item in result}), 1)
        self.assertEqual(len(self.store.list_applications()), 1)
        self.assertEqual(len(self.store.list_events()), 1)

    def test_snapshot_and_timeline_survive_profile_and_vacancy_updates(self):
        profile = self.store.save_profile({"skills": ["Python"], "facts": {"country": "BR"}})
        self.store.save_answer({"intent": "Formation", "text": "Marketing", "source": "cv-v1"})
        job = self.job()
        app = self.store.create_application(job["id"], {"status": "prepared", "resume_version": "cv-v1"})
        self.store.save_profile({"skills": ["Python", "Java"], "facts": {"country": "BR"}})
        self.store.save_answer({"intent": "formation", "text": "Updated", "source": "cv-v2"})
        self.job(title="Changed vacancy")
        updated = self.store.update_application(app["id"], {"status": "sent", "message_id": "mail-1", "snapshot": {}})
        self.assertEqual(updated["snapshot"], app["snapshot"])
        self.assertEqual(updated["snapshot"]["profile"]["revision"], profile["revision"])
        self.assertEqual(updated["snapshot"]["job"]["title"], "Python Developer")
        self.assertEqual(updated["snapshot"]["answers"][0]["text"], "Marketing")
        self.assertEqual(updated["snapshot"]["initial_data"]["resume_version"], "cv-v1")
        reloaded = Store(self.path)
        self.others.append(reloaded)
        self.assertEqual(reloaded.get_application(app["id"])["status"], "sent")
        events = reloaded.list_events(app["id"])
        self.assertEqual([item["kind"] for item in events], ["application.created", "application.updated"])
        self.assertEqual(events[-1]["detail"]["changes"]["message_id"], "mail-1")

    def test_changed_job_invalidates_match_while_unchanged_refresh_keeps_it(self):
        job = self.job()
        self.store.save_match(job["id"], {"score": 100, "eligible": True})
        self.assertEqual(self.job()["match"]["score"], 100)
        self.assertIsNone(self.job(description="Java required")["match"])

    def test_answer_intent_update_is_unique_and_return_values_are_detached(self):
        one = self.store.save_answer({"intent": " Language ", "text": "Italian", "source": "profile"})
        two = self.store.save_answer({"intent": "language", "text": "Italian fluent", "source": "profile-v2"})
        self.assertEqual(one["id"], two["id"])
        self.assertEqual(len(self.store.list_answers()), 1)
        two["text"] = "mutated in caller"
        self.assertEqual(self.store.list_answers()[0]["text"], "Italian fluent")
        self.assertTrue(self.store.delete_answer(two["id"])["deleted"])
        self.assertFalse(self.store.delete_answer(two["id"])["deleted"])

    def test_event_idempotency_and_foreign_keys(self):
        app = self.store.create_application(self.job()["id"], {})
        event = self.store.add_event(app["id"], "email.received", {"message_id": "m1"}, "gmail:m1")
        repeat = self.store.add_event(app["id"], "email.received", {"message_id": "m1"}, "gmail:m1")
        self.assertEqual(event["id"], repeat["id"])
        with self.assertRaises(ValueError):
            self.store.add_event(None, "different.action", {}, "gmail:m1")
        count = len(self.store.list_events())
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_event("missing-application", "email.received", {}, "gmail:m2")
        self.assertEqual(len(self.store.list_events()), count)

    def test_locks_have_ownership_and_expiry_across_workers(self):
        other = self.worker_stores(1)[0]
        with patch("career.store.time.time", return_value=1000):
            self.assertTrue(self.store.try_lock("send", ttl=30)["acquired"])
            self.assertFalse(other.try_lock("send", ttl=30)["acquired"])
            self.assertFalse(other.release_lock("send")["released"])
            self.assertFalse(self.store.try_lock("send", ttl=30)["acquired"])
        with patch("career.store.time.time", return_value=1031):
            self.assertTrue(other.try_lock("send", ttl=30)["acquired"])
            self.assertFalse(self.store.release_lock("send")["released"])
            self.assertTrue(other.release_lock("send")["released"])

    def test_stale_context_cannot_release_new_lease_on_the_same_store(self):
        old_context, new_context = copy_context(), copy_context()
        with patch("career.store.time.time", return_value=1000):
            self.assertTrue(old_context.run(self.store.try_lock, "send", 30)["acquired"])
        with patch("career.store.time.time", return_value=1031):
            self.assertTrue(new_context.run(self.store.try_lock, "send", 30)["acquired"])
            self.assertFalse(old_context.run(self.store.release_lock, "send")["released"])
            self.assertFalse(self.store.try_lock("send", 30)["acquired"])
            self.assertTrue(new_context.run(self.store.release_lock, "send")["released"])

    def test_missing_identifiers_are_rejected_instead_of_becoming_none_strings(self):
        with self.assertRaises(ValueError):
            self.store.upsert_job({"source": "manual", "external_id": None})
        with self.assertRaises(ValueError):
            self.store.upsert_job({"source": None, "external_id": "1"})
        with self.assertRaises(ValueError):
            self.store.save_answer({"intent": None, "text": "Response"})

    def test_settings_and_ciphertext_persist_without_returning_secret_on_write(self):
        self.store.set_setting("policy", {"auto_apply": False})
        saved = self.store.set_secret("google", "ciphertext-only")
        self.assertNotIn("value", saved)
        other = self.worker_stores(1)[0]
        self.assertEqual(other.get_setting("policy"), {"auto_apply": False})
        self.assertEqual(other.get_secret("google"), "ciphertext-only")
        self.assertIsNone(other.get_secret("unknown"))


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"skills": ["Python", "FastAPI", "Postgres"],
            "preferences": {"roles": ["Backend", "Developer"], "countries": ["BR", "IT"],
                            "remote_only": True, "min_score": 70, "auto_apply": False},
            "facts": {"residence_country": "BR"}}
        self.job = {"title": "Backend Python Developer", "description": "FastAPI and PostgreSQL",
                    "location": "Remote Brazil", "required_skills": ["Python", "FastAPI", "PostgreSQL"]}

    def test_skill_aliases_and_explicit_domestic_remote_are_eligible(self):
        result = evaluate(self.profile, self.job)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["matched_skills"], ["FastAPI", "PostgreSQL", "Python"])
        self.assertTrue(result["eligible"])
        # The policy switch is separate from eligibility; matching never authorizes sending.
        self.assertFalse(self.profile["preferences"]["auto_apply"])

    def test_remote_italy_does_not_imply_remote_from_brazil(self):
        self.job["location"] = "Remote Italy"
        result = evaluate(self.profile, self.job)
        self.assertEqual(result["score"], 100)
        self.assertFalse(result["eligible"])
        self.assertTrue(any("não confirmada" in text for text in result["blockers"]))

    def test_explicit_allowed_countries_override_company_location(self):
        self.job.update(location="Remote Italy", eligible_countries=["BR", "IT"])
        self.assertTrue(evaluate(self.profile, self.job)["eligible"])
        self.job["eligible_countries"] = ["IT"]
        result = evaluate(self.profile, self.job)
        self.assertFalse(result["eligible"])
        self.assertTrue(any("Residência incompatível" in text for text in result["blockers"]))

    def test_worldwide_remote_is_supported_but_generic_remote_is_pending(self):
        self.job["location"] = "Remote"
        self.assertFalse(evaluate(self.profile, self.job)["eligible"])
        self.job["location"] = "Remote worldwide"
        self.assertTrue(evaluate(self.profile, self.job)["eligible"])

    def test_role_remote_and_country_preferences_block_incompatible_jobs(self):
        for changes, expected in [({"title": "Account Manager"}, "Cargo"),
                                  ({"location": "Hybrid Brazil"}, "presencial"),
                                  ({"location": "Remote Canada"}, "País da vaga")]:
            with self.subTest(changes=changes):
                result = evaluate(self.profile, {**self.job, **changes})
                self.assertFalse(result["eligible"])
                self.assertTrue(any(expected in text for text in result["blockers"]))

    def test_missing_skills_and_empty_requirements_never_get_fabricated_scores(self):
        result = evaluate(self.profile, {**self.job, "required_skills": ["Java", "Spring"]})
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["missing_skills"], ["Java", "Spring"])
        self.assertFalse(result["eligible"])
        result = evaluate(self.profile, {"title": "Developer", "location": "Remote Brazil"})
        self.assertEqual(result["score"], 0)
        self.assertFalse(result["eligible"])

    def test_explicit_mandatory_skill_blocks_even_above_score_threshold(self):
        self.job["required_skills"].append("Java")
        result = evaluate(self.profile, self.job)
        self.assertEqual(result["score"], 75)
        self.assertFalse(result["eligible"])
        self.assertTrue(any("obrigatório" in text for text in result["blockers"]))

    def test_years_and_languages_require_explicit_profile_facts(self):
        self.job.update(required_years=3, required_languages=["Italian"])
        result = evaluate(self.profile, self.job)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["score"], 100)
        self.profile["facts"].update(experience_years=3, languages={"Italiano": "fluente"})
        self.assertTrue(evaluate(self.profile, self.job)["eligible"])

    def test_evaluation_does_not_mutate_inputs(self):
        profile, job = deepcopy(self.profile), deepcopy(self.job)
        evaluate(self.profile, self.job)
        self.assertEqual(self.profile, profile)
        self.assertEqual(self.job, job)


if __name__ == "__main__":
    unittest.main()
