from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from control_okua.app_qt.design_system import APP_DISPLAY_NAME
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
from control_okua.services.remote_api_bootstrap import (
    build_remote_api_runtime_status,
    ensure_remote_api_runtime_config,
)
from control_okua.services.remote_api_service import RemoteApiService
from control_okua.services.session_controller import SessionController


def _emit_runtime_message(message: str) -> None:
    stream = getattr(sys, "stdout", None)
    if stream is None or not hasattr(stream, "write"):
        return
    try:
        print(str(message), file=stream, flush=True)
    except Exception:
        return


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
        _emit_runtime_message(f"[config] {warning}")

    cfg, remote_runtime_warnings, remote_config_changed = ensure_remote_api_runtime_config(cfg)
    if remote_config_changed:
        save_config(cfg, config_path)
    for warning in remote_runtime_warnings:
        _emit_runtime_message(f"[remote_api] {warning}")

    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("okua.ckv2.control")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)

    qss_path = resource_path("assets/theme.qss")
    if qss_path.exists():
        app.setStyleSheet(load_qss(qss_path))

    icon_path = app_icon_path()
    if icon_path.exists():
        # Barra de tareas (QApplication): fondo BRAND_DEEP + logo encima, en memoria.
        # Garantiza visibilidad sobre el fondo oscuro del taskbar sin tocar los archivos.
        src = QPixmap(str(icon_path))
        if not src.isNull():
            bg = QPixmap(src.size())
            bg.fill(QColor(11, 59, 39))          # BRAND_DEEP
            painter = QPainter(bg)
            painter.drawPixmap(0, 0, src)
            painter.end()
            app.setWindowIcon(QIcon(bg))

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
            _emit_runtime_message(f"[config] {profile_warning}")
            active_profile = selected_profile

    session_controller = SessionController(cfg)
    remote_api_service: RemoteApiService | None = None

    def _stop_remote_api_service() -> None:
        nonlocal remote_api_service
        if remote_api_service is None:
            return
        remote_api_service.stop()
        remote_api_service = None

    def _emit_remote_runtime_summary(status: object, *, announce_urls: bool = True) -> None:
        effective_bind_host = getattr(status, "effective_bind_host", None)
        port = getattr(status, "port", None)
        service_state = getattr(status, "service_state", "stopped")
        if service_state == "running" and effective_bind_host and port:
            _emit_runtime_message(
                "[remote_api] servicio remoto activo en "
                f"http://{effective_bind_host}:{port}"
            )
        else:
            _emit_runtime_message(f"[remote_api] estado={service_state}")
        _emit_runtime_message(f"[remote_api] exposure_mode={getattr(status, 'exposure_mode', '-')}")
        user_store_path = getattr(status, "user_store_path", None)
        if user_store_path:
            _emit_runtime_message(f"[remote_api] store de usuarios remotos en {user_store_path}")
        if service_state == "running" and effective_bind_host and port:
            _emit_runtime_message(
                "[remote_api] consola remota disponible en "
                f"http://{effective_bind_host}:{port}/remote/"
            )
        if not announce_urls:
            return
        local_access_url = getattr(status, "local_access_url", None)
        remote_access_url = getattr(status, "remote_access_url", None)
        access_urls = getattr(status, "access_urls", tuple())
        if local_access_url:
            _emit_runtime_message(f"[remote_api] local url: {local_access_url}")
        if remote_access_url:
            _emit_runtime_message(f"[remote_api] remote url: {remote_access_url}")
        for access_url in access_urls:
            _emit_runtime_message(f"[remote_api] access url: {access_url}")

    def _restart_remote_api_runtime() -> tuple[object, str]:
        nonlocal remote_api_service
        remote_api_config = resolve_remote_api_config(cfg)
        _stop_remote_api_service()

        if not remote_api_config.enabled:
            status = build_remote_api_runtime_status(
                remote_api_config,
                service_state="stopped",
            )
            _emit_runtime_message("[remote_api] deshabilitado: remote_api.enabled=false en config.")
            return status, "Servicio remoto deshabilitado. El acceso desde otro dispositivo quedó apagado."

        _emit_runtime_message(
            "[remote_api] intentando iniciar servicio remoto en "
            f"mode={remote_api_config.exposure_mode} port={remote_api_config.port}"
        )
        try:
            remote_api_service = RemoteApiService(
                runtime_client=session_controller,
                config=remote_api_config,
                config_path=config_path,
            )
            remote_api_service.start()
            status = build_remote_api_runtime_status(
                remote_api_config,
                service_state="running",
                effective_bind_host=remote_api_service.effective_bind_host,
                user_store_path=remote_api_service.user_store_path,
            )
            _emit_remote_runtime_summary(status)
            return status, (
                "Servicio remoto actualizado. Revise la URL sugerida en Herramientas avanzadas "
                "y use la URL remota cuando el modo sea Tailscale."
            )
        except Exception as exc:
            status = build_remote_api_runtime_status(
                remote_api_config,
                service_state="failed",
                failure_message=str(exc),
            )
            _emit_runtime_message(f"[remote_api] no se pudo iniciar servicio remoto: {exc}")
            if remote_api_config.auth_mode == "bearer_token_inventory":
                _emit_runtime_message("[remote_api] auth_mode=bearer_token_inventory")
                if remote_api_config.tokens:
                    for token_entry in remote_api_config.tokens:
                        _emit_runtime_message(
                            "[remote_api] token requerido: "
                            f"role={token_entry.role} env_var={token_entry.env_var}"
                        )
                else:
                    _emit_runtime_message("[remote_api] remote_api.tokens esta vacio en config.")
            elif remote_api_config.auth_mode == "bearer_token":
                _emit_runtime_message(
                    "[remote_api] token requerido en variable de entorno "
                    f"{remote_api_config.token_env_var}"
                )
            return status, (
                "La configuración se guardó, pero el servicio remoto no pudo iniciarse: "
                f"{exc}"
            )

    def _apply_remote_api_settings(enabled: bool, exposure_mode: str) -> tuple[object, str]:
        remote_cfg = cfg.setdefault("remote_api", {})
        if not isinstance(remote_cfg, dict):
            remote_cfg = {}
            cfg["remote_api"] = remote_cfg
        remote_cfg["enabled"] = enabled
        remote_cfg["exposure_mode"] = exposure_mode
        if exposure_mode == "local_only":
            remote_cfg["bind_host"] = "127.0.0.1"
        elif exposure_mode == "tailscale_only":
            current_bind = remote_cfg.get("bind_host")
            if not isinstance(current_bind, str) or not current_bind.strip():
                remote_cfg["bind_host"] = "127.0.0.1"
        save_config(cfg, config_path)
        return _restart_remote_api_runtime()

    app.aboutToQuit.connect(_stop_remote_api_service)
    remote_runtime_status, _ = _restart_remote_api_runtime()

    window = MainWindow(
        cfg=cfg,
        config_path=config_path,
        warnings=warnings,
        session_controller=session_controller,
        on_apply_remote_settings=_apply_remote_api_settings,
    )
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.set_remote_api_status(remote_runtime_status)
    window.showMaximized()

    # Permite validaciones automáticas sin afectar ejecución normal.
    auto_close_ms = os.getenv("CKV2_AUTOCLOSE_MS", "").strip()
    if auto_close_ms.isdigit():
        QTimer.singleShot(int(auto_close_ms), app.quit)

    return app.exec()
