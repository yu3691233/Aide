import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from manager_utils import _is_aidelink_process


class _Process:
    def __init__(self, exe="", cwd=""):
        self._exe = exe
        self._cwd = cwd

    def exe(self):
        return self._exe

    def cwd(self):
        return self._cwd


class ProcessCleanupScopeTests(unittest.TestCase):
    def test_accepts_aidelink_process_path(self):
        proc = _Process(cwd=r"C:\Apps\AideLink\server")
        self.assertTrue(_is_aidelink_process(proc, "python manager_tray.py", r"C:\Apps\AideLink\server"))


    def test_rejects_unrelated_same_named_process(self):
        proc = _Process(exe=r"C:\Tools\frpc.exe", cwd=r"C:\OtherProject")
        self.assertFalse(_is_aidelink_process(proc, "frpc.exe", r"C:\Apps\AideLink\server"))
