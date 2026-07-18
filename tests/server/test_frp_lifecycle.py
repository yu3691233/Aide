import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import frp_service
import manager_tray


class FrpLifecycleTests(unittest.TestCase):
    def test_detects_existing_aidelink_frp_after_service_restart(self):
        process = Mock()
        process.info = {
            "pid": 123,
            "name": "frpc.exe",
            "cmdline": [
                r"F:\aide\server\frpc.exe",
                "-c",
                r"F:\aide\server\frpc_run.toml",
            ],
        }
        psutil = Mock()
        psutil.process_iter.return_value = [process]
        psutil.NoSuchProcess = RuntimeError
        psutil.AccessDenied = PermissionError

        with patch.dict(sys.modules, {"psutil": psutil}), patch.object(
            frp_service, "BRIDGE_DIR", Path(r"F:\aide\server")
        ):
            self.assertIs(process, frp_service._find_running_frp_process())

    def test_auto_start_checkbox_only_updates_persisted_setting(self):
        config = {"frp": {"enabled": False, "server_addr": "example"}}

        with patch.object(manager_tray, "load_config", return_value=config), patch.object(
            manager_tray, "save_config", return_value=(True, "ok")
        ) as save, patch.object(manager_tray, "refresh_tray_menu"), patch.object(
            manager_tray, "start_frp_client"
        ) as start:
            manager_tray._tray_toggle_frp_auto_start()

        self.assertTrue(save.call_args.args[0]["frp"]["enabled"])
        start.assert_not_called()

    def test_immediate_enable_does_not_change_auto_start_setting(self):
        with patch.object(manager_tray, "start_frp_client", return_value=True) as start, patch.object(
            manager_tray, "save_config"
        ) as save, patch.object(manager_tray, "refresh_tray_menu"):
            manager_tray._tray_start_frp_now()

        start.assert_called_once_with(force=True)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
