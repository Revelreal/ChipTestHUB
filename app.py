# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime

from flask import Flask, jsonify
from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
task_manager = None  # set after emitters are defined


def _ensure_directories():
    for d in ("logs", "uploads", "exports", "test_results"):
        os.makedirs(d, exist_ok=True)


def _setup_logging(app: Flask) -> None:
    _ensure_directories()
    log_path = os.path.join("logs", f"hub_{datetime.now().strftime('%Y%m%d')}.log")

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s: %(message)s [%(name)s]")
    )
    handler.setLevel(logging.INFO)

    for logger_name in ("app", "voltage_scan", "task_manager", "emit"):
        logger = logging.getLogger(logger_name)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info("Chip Test HUB started")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("CHIP_TEST_HUB_SECRET", "chip-test-hub-dev")

    try:
        from flask_cors import CORS  # type: ignore

        CORS(app)
    except Exception:  # noqa: BLE001
        # Flask-Cors is optional for local UI usage; start.bat installs it by default.
        pass
    _setup_logging(app)

    from routes.main_routes import main_bp
    from routes.test_routes import test_bp
    from routes.settings_routes import settings_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(test_bp, url_prefix="/test")
    app.register_blueprint(settings_bp)

    socketio.init_app(app)

    @app.errorhandler(Exception)
    def handle_exception(e):  # noqa: ANN001
        app.logger.exception("Unhandled exception: %s", e)
        return jsonify({"success": False, "message": str(e)}), 500

    return app


def _emit_log(test_type: str, message: str) -> None:
    logging.getLogger("emit").info(f"[{test_type}] {message}")
    try:
        print(f"[EMIT LOG] [{test_type}] {message}")
        socketio.emit(
            "log_message",
            {
                "test_type": test_type,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "message": message,
            },
        )
    except Exception as e:
        logging.getLogger("emit").error(f"Emit log failed: {e}")
        print(f"[EMIT ERROR] {e}")


def _emit_progress(test_type: str, progress: float, message: str) -> None:
    logging.getLogger("emit").debug(f"[{test_type}] progress={progress} {message}")
    try:
        socketio.emit(
            "test_progress",
            {
                "test_type": test_type,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "progress": float(progress),
                "message": message,
            },
        )
    except Exception as e:
        logging.getLogger("emit").error(f"Emit progress failed: {e}")


def _emit_test_completed(test_type: str, task_id: str, result_path: str) -> None:
    import os
    logging.getLogger("emit").info(f"[{test_type}] test_completed: {result_path}")
    try:
        socketio.emit(
            "test_completed",
            {
                "test_type": test_type,
                "task_id": task_id,
                "result_path": result_path,
                "filename": os.path.basename(result_path),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            },
        )
    except Exception as e:
        logging.getLogger("emit").error(f"Emit test_completed failed: {e}")


def _emit_temp_data(data: dict) -> None:
    logger = logging.getLogger("emit")
    try:
        socketio.emit("temp_data", data)
    except Exception as e:
        logger.error(f"[TEMP_DATA] Emit temp_data failed: {e}")


from utils.notification_service import get_notification_service  # noqa: E402
from utils.task_manager import TaskManager  # noqa: E402

notification_service = get_notification_service()
task_manager = TaskManager(
    _emit_log, _emit_progress, _emit_test_completed, _emit_temp_data, notification_service
)

app = create_app()

if __name__ == "__main__":
    print("=" * 60)
    print("Chip Test HUB running")
    print("URL: http://127.0.0.1:5000")
    print("Stop: Ctrl + C")
    print("=" * 60)
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=True,
        allow_unsafe_werkzeug=True,
    )

