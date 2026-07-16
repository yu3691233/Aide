import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.ide_routes import _install_aidelink_skill, ide_bp


class IdeSkillInstallTests(unittest.TestCase):
    def test_installs_bundled_skill_for_codex_and_trae(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source" / "aidelink-manager-worker"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("---\nname: aidelink-manager-worker\ndescription: test\n---\n", encoding="utf-8")

            self.assertEqual(2, _install_aidelink_skill("codex", root / "home", source))
            self.assertEqual(1, _install_aidelink_skill("trae_solo_cn", root / "home", source))
            self.assertTrue((root / "home" / ".agents" / "skills" / source.name / "SKILL.md").is_file())
            self.assertTrue((root / "home" / ".codex" / "skills" / source.name / "SKILL.md").is_file())
            self.assertTrue((root / "home" / ".trae" / "skills" / source.name / "SKILL.md").is_file())

    def test_trae_solo_cn_route_installs_mcp_and_skill(self):
        app = Flask(__name__)
        app.register_blueprint(ide_bp)
        with tempfile.TemporaryDirectory() as temp_dir:
            appdata = Path(temp_dir) / "AppData"
            user_dir = appdata / "TRAE SOLO CN" / "User"
            user_dir.mkdir(parents=True)
            with patch.dict("os.environ", {"APPDATA": str(appdata)}), patch(
                "routes.ide_routes._install_aidelink_skill", return_value=1
            ):
                response = app.test_client().post(
                    "/api/ide/install-mcp", json={"key": "trae_solo_cn"}
                )

            payload = response.get_json()
            self.assertTrue(payload["success"])
            self.assertIn("经理/员工技能", payload["message"])
            mcp = json.loads((user_dir / "mcp.json").read_text(encoding="utf-8"))
            self.assertIn("aidelink", mcp["mcpServers"])

    def test_minimax_route_rejects_mcp_install_without_writing_files(self):
        """MiniMax Code 当前未验证支持第三方 MCP：接口必须返回 success=false、
        给出明确非永久性提示，且不会创建任何 MiniMax Code 的 mcp.json 文件。"""
        app = Flask(__name__)
        app.register_blueprint(ide_bp)
        with tempfile.TemporaryDirectory() as temp_dir:
            appdata = Path(temp_dir) / "AppData"
            appdata.mkdir(parents=True)
            home_dir = Path(temp_dir) / "home"
            home_dir.mkdir(parents=True)
            with patch.dict("os.environ", {"APPDATA": str(appdata), "USERPROFILE": str(home_dir)}), patch(
                "routes.ide_routes._install_aidelink_skill", return_value=0
            ) as skill_mock:
                response = app.test_client().post(
                    "/api/ide/install-mcp", json={"key": "minimax"}
                )

            payload = response.get_json()
            self.assertFalse(payload["success"])
            self.assertIn("当前未验证支持第三方 MCP", payload["message"])

            # 不得创建 VSCode 内核风格的 User/mcp.json
            self.assertFalse((appdata / "MiniMax Code" / "User" / "mcp.json").exists())
            # 不得创建 ~/.minimax/mcp/mcp.json 猜测路径
            self.assertFalse((home_dir / ".minimax" / "mcp" / "mcp.json").exists())

            # success=False 时不应当继续触发 Skill 自动安装
            skill_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
