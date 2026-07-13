import io
import sys
import unittest
from pathlib import Path

from flask import Flask, request


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from upload_policy import MAX_UPLOAD_REQUEST_SIZE, configure_upload_limits, is_allowed_upload


class UploadPolicyTests(unittest.TestCase):
    def test_extension_check_is_case_insensitive(self):
        self.assertTrue(is_allowed_upload("SCREEN.PNG"))
        self.assertTrue(is_allowed_upload("notes.md"))

    def test_rejects_missing_or_disallowed_extensions(self):
        for filename in ("", "README", "payload.exe", "archive.zip"):
            with self.subTest(filename=filename):
                self.assertFalse(is_allowed_upload(filename))

    def test_flask_rejects_oversized_body_before_route_runs(self):
        app = Flask(__name__)
        configure_upload_limits(app)
        route_called = False

        @app.post("/upload")
        def upload():
            nonlocal route_called
            request.get_data()
            route_called = True
            return {"ok": True}

        response = app.test_client().post(
            "/upload",
            data={"file": (io.BytesIO(b"x" * (MAX_UPLOAD_REQUEST_SIZE + 1)), "large.txt")},
        )

        self.assertEqual(413, response.status_code)
        self.assertEqual({"ok": False, "raw": "Upload request too large"}, response.get_json())
        self.assertFalse(route_called)


if __name__ == "__main__":
    unittest.main()
