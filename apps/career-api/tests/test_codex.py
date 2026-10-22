"""Protocol tests use a fake subprocess: no installed Codex or live login."""
import asyncio
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from career.codex import CodexClient, CodexError


class FakeStdin:
    def __init__(self, process):
        self.process = process

    def write(self, value):
        message = json.loads(value)
        self.process.requests.append(message)
        if "method" not in message or "id" not in message:
            return
        self.process.handle(message)

    async def drain(self):
        await asyncio.sleep(0)


class FakeProcess:
    def __init__(self, mode="success"):
        self.mode = mode
        self.returncode = None
        self.stdout = asyncio.StreamReader()
        self.stdin = FakeStdin(self)
        self.requests = []
        self.threads = 0
        self.active_turns = 0
        self.max_active_turns = 0

    def emit(self, message):
        self.stdout.feed_data((json.dumps(message) + "\n").encode())

    def answer(self, message, result):
        self.emit({"id": message["id"], "result": result})

    def handle(self, message):
        method = message["method"]
        if self.mode == "rpc_timeout" and method == "initialize":
            return
        if method == "initialize":
            self.answer(message, {"userAgent": "fake"})
        elif method == "account/read":
            self.answer(message, {"account": {"type": "chatgpt", "email": "owner@example.com", "planType": "pro", "accessToken": "NEVER_EXPOSE"}})
        elif method == "account/login/start":
            url = "https://attacker.invalid/" if self.mode == "bad_login" else "https://auth.openai.com/codex/device"
            self.answer(message, {"verificationUrl": url, "userCode": "ABCD-1234", "loginId": "login-1"})
        elif method == "thread/start":
            self.threads += 1
            self.answer(message, {"thread": {"id": "thread-" + str(self.threads)}})
        elif method == "turn/start":
            thread = message["params"]["threadId"]
            turn = "turn-" + str(self.threads)
            self.active_turns += 1
            self.max_active_turns = max(self.max_active_turns, self.active_turns)
            self.answer(message, {"turn": {"id": turn, "status": "inProgress"}})
            self.emit({"method": "turn/started", "params": {"threadId": thread, "turn": {"id": turn}}})
            if self.mode == "turn_timeout":
                return
            asyncio.get_running_loop().call_later(0.001, self.finish, thread, turn)
        elif method == "turn/interrupt":
            self.active_turns = max(0, self.active_turns - 1)
            self.answer(message, {})

    def finish(self, thread, turn):
        self.emit({"method": "item/completed", "params": {"threadId": "unrelated", "item": {"type": "agentMessage", "id": "other", "text": '{"wrong":true}', "phase": "final_answer"}}})
        if self.mode == "tool_request":
            self.emit({"id": "server-1", "method": "item/commandExecution/requestApproval", "params": {"threadId": thread}})
        text = '```json\n{"score":90}\n```' if self.mode == "invalid_json" else '{"score":90,"missing":[]}'
        self.emit({"method": "item/completed", "params": {"threadId": thread, "item": {"type": "agentMessage", "id": "message-1", "phase": "commentary", "text": "Working..."}}})
        self.emit({"method": "item/completed", "params": {"threadId": thread, "item": {"type": "agentMessage", "id": "message-2", "phase": "final_answer", "text": text}}})
        status = "failed" if self.mode == "failed" else "completed"
        self.active_turns -= 1
        self.emit({"method": "turn/completed", "params": {"threadId": thread, "turn": {"id": turn, "status": status, "error": {"message": "SECRET upstream"} if status == "failed" else None}}})

    def terminate(self):
        self.returncode = 0
        self.stdout.feed_eof()

    def kill(self):
        self.terminate()

    async def wait(self):
        return self.returncode


class CodexTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(codex_binary="codex", codex_home=self.directory.name, codex_model="", public_url="http://127.0.0.1:8010", siwc_credentials_file=self.directory.name + "/credentials.json", codex_rpc_timeout=0.1, codex_turn_timeout=0.1)
        self.process = FakeProcess()
        self.spawn = AsyncMock(side_effect=lambda *args, **kwargs: self.process)
        self.patches = [patch("career.codex.shutil.which", return_value="/fake/codex"), patch("career.codex.asyncio.create_subprocess_exec", self.spawn)]
        for item in self.patches:
            item.start()
        self.client = CodexClient(self.settings)

    async def asyncTearDown(self):
        await self.client.close()
        for item in self.patches:
            item.stop()
        self.directory.cleanup()

    async def test_status_exposes_only_account_metadata(self):
        result = await self.client.status()
        self.assertTrue(result["connected"])
        self.assertEqual(result["account"], {"email": "owner@example.com", "planType": "pro"})
        self.assertNotIn("NEVER_EXPOSE", json.dumps(result))

    async def test_device_login_and_reject_untrusted_url(self):
        self.assertEqual((await self.client.login())["verification_url"], "https://auth.openai.com/codex/device")
        self.process.mode = "bad_login"
        with self.assertRaises(CodexError):
            await self.client.login()

    async def test_json_result_and_sandbox_settings(self):
        result = await self.client.run_json("Compare", {"skills": ["Python"]}, {"type": "object"})
        self.assertEqual(result, {"score": 90, "missing": []})
        start = next(item for item in self.process.requests if item.get("method") == "thread/start")
        turn = next(item for item in self.process.requests if item.get("method") == "turn/start")
        self.assertEqual(start["params"]["sandbox"], "readOnly")
        self.assertEqual(turn["params"]["sandboxPolicy"], {"type": "readOnly", "networkAccess": False})
        command = self.spawn.call_args.args
        self.assertIn("features.shell_tool=false", command)
        self.assertIn('web_search="disabled"', command)
        self.assertNotIn("GOOGLE_CLIENT_SECRET", self.spawn.call_args.kwargs["env"])

    async def test_turn_failure_is_not_success_or_secret_leak(self):
        self.process.mode = "failed"
        with self.assertRaises(CodexError) as caught:
            await self.client.run_json("Compare", {})
        self.assertNotIn("SECRET", str(caught.exception))

    async def test_turn_timeout_interrupts_once_and_does_not_retry(self):
        self.process.mode = "turn_timeout"
        with self.assertRaises(CodexError):
            await self.client.run_json("Compare", {})
        methods = [item.get("method") for item in self.process.requests]
        self.assertEqual(methods.count("turn/start"), 1)
        self.assertEqual(methods.count("turn/interrupt"), 1)

    async def test_rpc_timeout_stops_process(self):
        self.process.mode = "rpc_timeout"
        with self.assertRaises(CodexError):
            await self.client.start()
        self.assertEqual(self.process.returncode, 0)

    async def test_concurrent_analyses_are_serialized_and_isolated(self):
        result = await asyncio.gather(self.client.run_json("First", {}), self.client.run_json("Second", {}))
        self.assertEqual(len(result), 2)
        self.assertEqual(self.process.threads, 2)
        self.assertEqual(self.process.max_active_turns, 1)

    async def test_approval_is_declined_and_result_rejected(self):
        self.process.mode = "tool_request"
        with self.assertRaises(CodexError):
            await self.client.run_json("Compare", {})
        response = next(item for item in self.process.requests if item.get("id") == "server-1")
        self.assertEqual(response["result"], {"decision": "decline"})

    async def test_json_must_be_an_object_without_fences_or_duplicate_keys(self):
        self.process.mode = "invalid_json"
        with self.assertRaises(CodexError):
            await self.client.run_json("Compare", {})
        for value in ('[]', '{"x":NaN}', '{"x":1,"x":2}'):
            with self.assertRaises(CodexError):
                self.client._parse_json(value)

    async def test_unavailable_binary_has_explicit_status(self):
        with patch("career.codex.shutil.which", return_value=None):
            self.assertEqual(await self.client.status(), {"available": False, "connected": False})

    async def test_hosted_site_cannot_start_managed_device_login(self):
        self.settings.public_url = "https://karenangelis.com"
        self.client = CodexClient(self.settings)
        status = await self.client.status()
        self.assertFalse(status["available"])
        self.assertFalse(status["connected"])
        self.assertIn("Sign in with ChatGPT", status["reason"])
        self.assertEqual(status["documentation_url"], "https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms")
        self.assertTrue(status["pairing_required"])
        for operation in (self.client.start, self.client.login):
            with self.assertRaises(CodexError):
                await operation()
        with self.assertRaises(CodexError):
            await self.client.run_json("Compare", {})
        self.spawn.assert_not_awaited()

    async def test_hosted_uses_selected_siwc_token_provider_not_managed_login(self):
        self.settings.public_url = "https://karenangelis.com"
        provider = SimpleNamespace(
            metadata=lambda: {"configured": True, "pairing_required": False, "token_ready": True,
                              "account": {"email": "owner@example.com"}},
            access_token=AsyncMock(return_value="test-siwc-access"),
        )
        self.client = CodexClient(self.settings, token_provider=provider)
        status = await self.client.status()
        self.assertTrue(status["connected"])
        self.assertFalse(status["access_verified"])
        self.assertEqual(self.spawn.call_args.kwargs["env"]["ACCESS_TOKEN"], "test-siwc-access")
        self.assertIn('model_provider="openai_chatgpt_plan"', self.spawn.call_args.args)
        self.assertNotIn('forced_login_method="chatgpt"', self.spawn.call_args.args)
        self.assertEqual(await self.client.run_json("Compare", {}), {"score": 90, "missing": []})
        self.assertTrue((await self.client.status())["access_verified"])
        self.assertFalse(any(item.get("method") == "account/login/start" for item in self.process.requests))
        with self.assertRaises(CodexError):
            await self.client.login()


if __name__ == "__main__":
    unittest.main()
