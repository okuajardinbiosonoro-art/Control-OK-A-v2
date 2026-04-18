from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import logging
from pathlib import Path
from threading import Thread

from control_okua.core.firmware.ota_manifest_models import DEFAULT_OTA_HTTP_PORT
from control_okua.core.firmware.ota_manifest_service import resolve_ota_publish_root


class OtaServerServiceError(RuntimeError):
    """Base error for the local OTA HTTP server."""


class _OtaRequestHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".json": "application/json",
        ".bin": "application/octet-stream",
    }

    def __init__(self, *args, logger: logging.Logger, directory: str, **kwargs) -> None:
        self._logger = logger
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args) -> None:
        self._logger.info("OTA HTTP %s - %s", self.address_string(), format % args)


class OtaServerService:
    def __init__(
        self,
        *,
        root_dir: Path | str | None = None,
        bind_host: str = "0.0.0.0",
        port: int = DEFAULT_OTA_HTTP_PORT,
        logger: logging.Logger | None = None,
    ) -> None:
        self._root_dir = (
            Path(root_dir).expanduser()
            if root_dir is not None
            else resolve_ota_publish_root()
        )
        self._bind_host = bind_host
        self._port = int(port)
        self._logger = logger or logging.getLogger(__name__)
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    @property
    def bind_host(self) -> str:
        return self._bind_host

    @property
    def port(self) -> int:
        if self._server is not None:
            return int(self._server.server_port)
        return self._port

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return

        self._root_dir.mkdir(parents=True, exist_ok=True)
        handler = partial(
            _OtaRequestHandler,
            logger=self._logger,
            directory=str(self._root_dir),
        )
        try:
            self._server = ThreadingHTTPServer((self._bind_host, self._port), handler)
        except OSError as exc:
            message = (
                f"No se pudo iniciar servidor OTA local en {self._bind_host}:{self._port}: {exc}"
            )
            if getattr(exc, "winerror", None) == 10013:
                if self._bind_host == "0.0.0.0":
                    message += (
                        " En Windows, 0.0.0.0 a veces queda restringido o reservado; "
                        "prueba con la IP LAN del PC, o cambia el puerto OTA."
                    )
                else:
                    message += (
                        " En Windows, esa dirección o ese puerto pueden estar restringidos "
                        "o reservados; prueba otra IP local o cambia el puerto OTA."
                    )
            raise OtaServerServiceError(message) from exc

        self._server.daemon_threads = True
        self._thread = Thread(
            target=self._server.serve_forever,
            name="ota-http-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return

        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None

        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2.0)
