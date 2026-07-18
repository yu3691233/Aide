"""
注册所有 Blueprint 到 Flask app。
"""

import sys
from pathlib import Path
_server_dir = str(Path(__file__).parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


def register_all_routes(app):
    from .log_routes import log_bp
    from .config_routes import config_bp
    from .model_routes import model_bp
    from .service_routes import service_bp
    from .project_routes import project_bp
    from .task_routes import task_bp
    from .ide_routes import ide_bp
    from .phone_routes import phone_bp
    from .screenshot_routes import screenshot_bp
    from .device_routes import device_bp
    from .misc_routes import misc_bp
    from .mimo_routes import mimo_bp
    from window_layout import layout_bp
    from .ui_locator_routes import ui_locator_bp
    from .evolution_routes import evolution_bp
    from .oc_web_routes import oc_web_bp
    from .devspace_mcp_routes import devspace_bp
    from .prompt_routes import prompt_bp
    from .floating_window_routes import floating_window_bp
    from . import task_routes_flow  # noqa: F401
    from . import task_routes_management  # noqa: F401
    from . import task_routes_workflow  # noqa: F401

    app.register_blueprint(log_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(model_bp)
    app.register_blueprint(service_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(ide_bp)
    app.register_blueprint(phone_bp)
    app.register_blueprint(screenshot_bp)
    app.register_blueprint(device_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(mimo_bp)
    app.register_blueprint(layout_bp)
    app.register_blueprint(ui_locator_bp)
    app.register_blueprint(evolution_bp)
    app.register_blueprint(oc_web_bp)
    app.register_blueprint(devspace_bp)
    app.register_blueprint(prompt_bp)
    app.register_blueprint(floating_window_bp)
