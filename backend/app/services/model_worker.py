"""Generic model worker server base class.

Provides a Unix socket server that runs a GPU/CPU model in a dedicated process,
shared across all uvicorn workers. Subclasses only need to implement:
  - _create_model() -> load and return the model
  - _handle_request() -> process one request using the model

Features:
  - File lock ensures only one server process starts across all uvicorn workers
  - TTL-based auto-unloading: model is freed after idle timeout
  - Length-prefixed JSON protocol over Unix socket
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import multiprocessing
import os
import socket
import struct
import time
from typing import Any

from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows test environments
    fcntl = None

logger = logging.getLogger(__name__)

_SOCKET_READY_TIMEOUT_SECONDS = 30.0
_SOCKET_READY_POLL_SECONDS = 0.1


def _send_msg(conn: socket.socket, data: dict) -> None:
    payload = json.dumps(data).encode()
    conn.sendall(struct.pack(">I", len(payload)) + payload)


def _recv_msg(conn: socket.socket) -> dict:
    raw_len = b""
    while len(raw_len) < 4:
        chunk = conn.recv(4 - len(raw_len))
        if not chunk:
            raise ConnectionError("connection closed")
        raw_len += chunk
    msg_len = struct.unpack(">I", raw_len)[0]
    data = b""
    while len(data) < msg_len:
        chunk = conn.recv(msg_len - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data += chunk
    return json.loads(data)


class ModelWorkerServer:
    """Base class for a dedicated model worker process."""

    def __init__(self, name: str, socket_path: str, lock_path: str) -> None:
        self.name = name
        self.socket_path = socket_path
        self.lock_path = lock_path
        self._process: multiprocessing.Process | None = None
        self._lock_fd = None
        self._config: dict[str, Any] = {}
        self._session_ttl: int = 600
        self._recycle_on_idle_unload: bool = False
        self._recycle_after_request: bool = False

    def __getstate__(self) -> dict:
        """Exclude unpicklable file descriptor when spawning subprocess."""
        state = self.__dict__.copy()
        state["_lock_fd"] = None
        state["_process"] = None
        return state

    def _create_model(self, config: dict[str, Any]) -> Any:
        raise NotImplementedError

    def _handle_request(self, model: Any, request: dict) -> dict:
        raise NotImplementedError

    def start(
        self,
        config: dict[str, Any] | None = None,
        session_ttl: int = 600,
        recycle_after_request: bool = False,
        recycle_on_idle_unload: bool = False,
    ) -> None:
        self._config = config or {}
        self._session_ttl = session_ttl
        self._recycle_after_request = recycle_after_request
        self._recycle_on_idle_unload = recycle_on_idle_unload

        self._lock_fd = open(self.lock_path, "w")
        if fcntl is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                logger.info("%s worker server already running (another worker started it)", self.name)
                self._lock_fd.close()
                self._lock_fd = None
                self._wait_until_ready(timeout=_SOCKET_READY_TIMEOUT_SECONDS)
                return

        self._start_process()
        self._wait_until_ready(timeout=_SOCKET_READY_TIMEOUT_SECONDS)

    def _start_process(self) -> None:
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        self._process = multiprocessing.Process(
            target=self._server_loop,
            args=(self._config, self._session_ttl),
            daemon=True,
            name=f"{self.name}-worker",
        )
        self._process.start()
        logger.info("%s worker server started (pid=%s)", self.name, self._process.pid)

    def _ensure_alive(self) -> None:
        if self._lock_fd is None:
            try:
                self._lock_fd = open(self.lock_path, "w")
                if fcntl is not None:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.info("%s worker: acquired orphaned lock, will restart", self.name)
            except OSError:
                if self._lock_fd is not None:
                    self._lock_fd.close()
                    self._lock_fd = None
                return

        if self._process is not None and self._process.is_alive():
            return

        if self._process is not None:
            self._process.join(timeout=1)
            logger.warning(
                "%s worker process died (exit_code=%s), restarting...",
                self.name,
                self._process.exitcode,
            )

        self._start_process()
        self._wait_until_ready(timeout=_SOCKET_READY_TIMEOUT_SECONDS)

    def _wait_until_ready(
        self,
        *,
        timeout: float = _SOCKET_READY_TIMEOUT_SECONDS,
        poll_interval: float = _SOCKET_READY_POLL_SECONDS,
        log_timeout: bool = True,
    ) -> bool:
        deadline = time.monotonic() + max(timeout, 0.0)
        last_error: BaseException | None = None

        while True:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(max(min(poll_interval, timeout), 0.001))
                    sock.connect(self.socket_path)
                    _send_msg(sock, {"cmd": "ping"})
                    result = _recv_msg(sock)
                    if result.get("ok"):
                        return True
                    last_error = RuntimeError(str(result.get("error") or "worker ping failed"))
            except (ConnectionRefusedError, ConnectionError, FileNotFoundError, OSError) as exc:
                last_error = exc

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if log_timeout:
                    logger.warning(
                        "%s worker: socket not ready after %.1fs (%s)",
                        self.name,
                        timeout,
                        last_error,
                    )
                return False
            time.sleep(min(poll_interval, remaining))

    def shutdown(self) -> None:
        if self._process is not None and self._process.is_alive():
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.socket_path)
                _send_msg(sock, {"cmd": "shutdown"})
                _recv_msg(sock)
                sock.close()
            except Exception:
                pass

            self._process.join(timeout=30)
            if self._process.is_alive():
                logger.warning("%s worker did not exit in time, terminating", self.name)
                self._process.terminate()
            self._process = None

        if self._lock_fd is not None:
            if fcntl is not None:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None

        logger.info("%s worker shutdown complete", self.name)

    def _trim_process_heap(self) -> None:
        try:
            import ctypes
        except ImportError:
            return

        for libc_name in ("libc.so.6", "libc.so", "libSystem.B.dylib"):
            try:
                libc = ctypes.CDLL(libc_name)
            except OSError:
                continue

            malloc_trim = getattr(libc, "malloc_trim", None)
            if malloc_trim is None:
                continue

            try:
                malloc_trim(0)
                logger.info("%s worker: malloc_trim completed via %s", self.name, libc_name)
            except Exception:
                logger.debug(
                    "%s worker: malloc_trim failed via %s",
                    self.name,
                    libc_name,
                    exc_info=True,
                )
            return

    def _release_model_resources(self) -> None:
        gc.collect()
        self._trim_process_heap()

    async def submit(self, request: dict, timeout: float = 300) -> dict:
        """Connect to the worker server, send a request, and return the result."""
        import asyncio

        def _do_request():
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(self.socket_path)
            try:
                _send_msg(sock, request)
                return _recv_msg(sock)
            finally:
                sock.close()

        for attempt in range(2):
            try:
                result = await asyncio.to_thread(_do_request)
                break
            except (ConnectionRefusedError, ConnectionError, FileNotFoundError, OSError) as exc:
                if attempt == 1:
                    raise
                logger.warning(
                    "%s worker: connection failed (%s), attempting restart...",
                    self.name,
                    exc,
                )
                self._ensure_alive()
                self._wait_until_ready(timeout=min(float(timeout), _SOCKET_READY_TIMEOUT_SECONDS), log_timeout=False)

        if not result.get("ok"):
            raise RuntimeError(result.get("error", "unknown error"))
        return result

    async def warmup(
        self,
        config: dict[str, Any] | None = None,
        session_ttl: int = 600,
        *,
        timeout: float = 300,
        recycle_after_request: bool = False,
        recycle_on_idle_unload: bool = False,
    ) -> dict:
        effective_config = config or {}
        coordinator = EphemeralTaskCoordinator(ttl_seconds=180.0)
        task = EphemeralTaskKey.build(
            domain="model-worker",
            kind="warmup",
            resource_parts=[self.name],
            version=_config_fingerprint(effective_config, session_ttl),
        )
        lease = await coordinator.start(task, ttl_seconds=180.0, owner_prefix=f"{self.name}-warmup")
        if not lease.acquired:
            snapshot = lease.snapshot
            if snapshot is not None and snapshot.status == "done":
                return {"ok": True, "status": "ready", "deduplicated": True}
            return {"ok": True, "status": "pending", "deduplicated": True}
        try:
            self.start(
                config=effective_config,
                session_ttl=session_ttl,
                recycle_after_request=recycle_after_request,
                recycle_on_idle_unload=recycle_on_idle_unload,
            )
            result = await self.submit({"cmd": "warmup"}, timeout=timeout)
        except Exception as exc:
            await coordinator.fail(lease, error_type=type(exc).__name__)
            raise
        await coordinator.finish(lease, status="done", result={"status": str(result.get("status") or "ready")})
        return result

    def _server_loop(self, config: dict[str, Any], session_ttl: int) -> None:
        import app.core.logging as app_logging

        app_logging.setup_logging()
        logger.info("%s worker process started (pid=%s, ttl=%ds)", self.name, os.getpid(), session_ttl)

        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.socket_path)
        os.chmod(self.socket_path, 0o666)
        server.listen(16)
        server.settimeout(30)

        model = None
        last_used: float = 0

        while True:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                if model is not None and time.time() - last_used > session_ttl:
                    logger.info("%s worker: session idle > %ds, unloading model", self.name, session_ttl)
                    del model
                    model = None
                    self._release_model_resources()
                    if self._recycle_on_idle_unload:
                        logger.info("%s worker: recycle_on_idle_unload enabled, exiting worker process", self.name)
                        break
                continue
            except OSError:
                break

            try:
                task = _recv_msg(conn)

                if task.get("cmd") == "shutdown":
                    _send_msg(conn, {"ok": True})
                    conn.close()
                    break

                if task.get("cmd") == "ping":
                    _send_msg(conn, {"ok": True, "status": "ready"})
                    continue

                if model is None:
                    logger.info("%s worker: loading model...", self.name)
                    model = self._create_model(config)
                    logger.info("%s worker: model loaded", self.name)

                if task.get("cmd") == "warmup":
                    last_used = time.time()
                    _send_msg(conn, {"ok": True, "status": "ready"})
                    continue

                last_used = time.time()
                result = self._handle_request(model, task)
                _send_msg(conn, result)
            except Exception as exc:
                logger.exception("%s worker: request failed", self.name)
                try:
                    _send_msg(conn, {"ok": False, "error": str(exc)})
                except Exception:
                    pass
            finally:
                conn.close()
            if self._recycle_after_request and model is not None:
                logger.info("%s worker: recycle_after_request enabled, exiting worker process", self.name)
                break

        server.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        if model is not None:
            del model
            self._release_model_resources()
        logger.info("%s worker process exiting", self.name)


def _config_fingerprint(config: dict[str, Any], session_ttl: int) -> str:
    payload = json.dumps(
        {"config": config, "session_ttl": int(session_ttl)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
