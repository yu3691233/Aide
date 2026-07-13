import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.devspace_mcp_routes import _netstat_pids_for_port


class DevspaceProcessUtilsTests(unittest.TestCase):
    def test_netstat_parser_returns_only_listening_port_pids(self):
        lines = [
            "  TCP    127.0.0.1:7676    0.0.0.0:0    LISTENING    1234",
            "  TCP    127.0.0.1:7676    0.0.0.0:0    ESTABLISHED  5678",
            "  TCP    127.0.0.1:5000    0.0.0.0:0    LISTENING    9999",
        ]
        with patch("routes.devspace_mcp_routes._netstat_lines", return_value=lines):
            self.assertEqual(["1234"], _netstat_pids_for_port(7676))


if __name__ == "__main__":
    unittest.main()
