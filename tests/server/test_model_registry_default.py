import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import model_registry


class ModelRegistryDefaultTests(unittest.TestCase):
    def test_default_model_never_returns_alias(self):
        with patch.object(model_registry, "_load_user_file", return_value={"__default_model__": "auto"}), patch.object(
            model_registry,
            "get_active_models",
            return_value={"auto": {}, "free": {}, "minimax-m3": {}},
        ):
            self.assertEqual("minimax-m3", model_registry.get_default_model())

    def test_default_model_uses_first_real_active_model(self):
        with patch.object(model_registry, "_load_user_file", return_value={"__default_model__": "free"}), patch.object(
            model_registry,
            "get_active_models",
            return_value={"free": {}, "ollama-local": {}},
        ):
            self.assertEqual("ollama-local", model_registry.get_default_model())


if __name__ == "__main__":
    unittest.main()
