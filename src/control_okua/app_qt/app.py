from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from control_okua.app_qt.main_window import MainWindow
from control_okua.app_qt.profile_selector_dialog import ProfileSelectorDialog
from control_okua.app_qt.resources import app_icon_path, load_qss, resource_path
from control_okua.core.config.config_schema import load_config, save_config
from control_okua.core.profiles.profile_service import (
    infer_profile_from_config,
    is_known_profile_id,
    set_active_profile,
)
from control_okua.services.remote_api_contract import resolve_remote_api_config
from control_okua.services.remote_api_service import RemoteApiService
from control_okua.services.session_controller import SessionController


def _get_active_profile_id(cfg: dict[str, object]) -> str | None:
    profile_cfg = cfg.get("profile")
    if not isinstance(profile_cfg, dict):
        return None
    active_profile = profile_cfg.get("active")
    if isinstance(active_profile, str) and is_known_profile_id(active_profile):
        return active_profile
    return None


def run_app() -> int:
    cfg, warnings, config_path = load_config()
    for warning in warnings:
        print(f"[config] {warning}")

    app = QApplication(sys.argv)

    qss_path = resource_path("assets/theme.qss")
    if qss_path.exists():
        app.setStyleSheet(load_qss(qss_path))

    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    active_profile = _get_active_profile_id(cfg)
    if active_profile is None:
        inferred_profile = infer_profile_from_config(cfg)
        selected_profile = ProfileSelectorDialog.choose_profile(
            current_profile_id=inferred_profile,
        )

        if isinstance(selected_profile, str):
            cfg = set_active_profile(cfg, selected_profile)
            save_config(cfg, config_path)
            profile_warning = (
                f"profile.active actualizado a '{selected_profile}' desde selector guiado."
            )
            warnings.append(profile_warning)
            print(f"[config] {profile_warning}")
            active_profile = selected_profile

    session_controller = SessionController(cfg)
    window = MainWindow(
        cfg=cfg,
        config_path=config_path,
        warnings=warnings,
        session_controller=session_controller,
    )
    remote_api_service: RemoteApiService | None = None
    remote_api_config = resolve_remote_api_config(cfg)
    if remote_api_config.enabled:
        try:
            remote_api_service = RemoteApiService(
                runtime_client=session_controller,
                config=remote_api_config,
            )
            remote_api_service.start()
            app.aboutToQuit.connect(remote_api_service.stop)
            print(
                "[remote_api] servicio remoto activo en "
                f"http://{remote_api_config.bind_host}:{remote_api_service.port}"
            )
        except Exception as exc:
            print(f"[remote_api] no se pudo iniciar servicio remoto: {exc}")
    window.show()

    # Permite validaciones automáticas sin afectar ejecución normal.
    auto_close_ms = os.getenv("CKV2_AUTOCLOSE_MS", "").strip()
    if auto_close_ms.isdigit():
        QTimer.singleShot(int(auto_close_ms), app.quit)

    return app.exec()
