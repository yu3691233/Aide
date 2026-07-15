import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from opencode_client import send_prompt


class OpenCodeClientTests(unittest.TestCase):
    def _response(self, payload=None, status=200):
        response = Mock()
        response.json.return_value = payload
        response.status_code = status
        response.raise_for_status.side_effect = None
        return response

    def test_uses_latest_project_session_and_prompt_async(self):
        http = Mock()
        http.get.return_value = self._response([
            {"id": "old", "directory": r"F:\aide", "time": {"updated": 1}},
            {"id": "new", "directory": r"F:\aide", "time": {"updated": 2}},
        ])
        http.post.return_value = self._response(None, status=204)

        result = send_prompt(
            "finish this",
            task_id="task-1",
            directory=r"F:\aide",
            settings={"opencode_web_port": 4096},
            http=http,
        )

        self.assertEqual("new", result["session_id"])
        url = http.post.call_args.args[0]
        self.assertEqual("http://127.0.0.1:4096/session/new/prompt_async", url)
        self.assertEqual({"directory": r"F:\aide"}, http.post.call_args.kwargs["params"])
        self.assertEqual(
            [{"type": "text", "text": "[AideLink task task-1]\nfinish this"}],
            http.post.call_args.kwargs["json"]["parts"],
        )

    def test_creates_session_when_project_has_no_history(self):
        http = Mock()
        http.get.return_value = self._response([])
        http.post.side_effect = [
            self._response({"id": "created"}),
            self._response(None, status=204),
        ]

        result = send_prompt(
            "hello",
            directory=r"F:\new-project",
            settings={"opencode_web_port": 4096},
            http=http,
        )

        self.assertEqual("created", result["session_id"])
        self.assertEqual("http://127.0.0.1:4096/session", http.post.call_args_list[0].args[0])
        self.assertEqual({"directory": r"F:\new-project"}, http.post.call_args_list[0].kwargs["params"])
        self.assertEqual(
            "http://127.0.0.1:4096/session/created/prompt_async",
            http.post.call_args_list[1].args[0],
        )


if __name__ == "__main__":
    unittest.main()
