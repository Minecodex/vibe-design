from __future__ import annotations

import base64
import contextlib
import inspect
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from app.services.agent_harness.agent_resources.browser import run_browser_task

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


VIEWPORTS: dict[str, tuple[int, int]] = {
    "desktop": (1440, 900),
    "mobile": (390, 844),
}


@dataclass(frozen=True, slots=True)
class ScreenshotEvidence:
    screenshot_ref: str | None
    warning: dict[str, str] | None = None


async def capture_artifact_screenshot(
    *,
    ctx: "HarnessContext",
    entry: str,
    viewport: str,
    evidence_dir: Path,
) -> ScreenshotEvidence:
    width, height = VIEWPORTS.get(viewport, VIEWPORTS["desktop"])
    try:
        return await run_browser_task(
            _capture_artifact_screenshot,
            ctx=ctx,
            entry=entry,
            viewport=viewport,
            width=width,
            height=height,
            evidence_dir=evidence_dir,
        )
    except Exception as exc:
        return ScreenshotEvidence(
            screenshot_ref=None,
            warning={
                "code": "screenshot_unavailable",
                "message": f"Browser screenshot capture failed; copied the artifact entry as deterministic evidence ({type(exc).__name__}).",
            },
        )


async def _capture_artifact_screenshot(
    *,
    ctx: "HarnessContext",
    entry: str,
    viewport: str,
    width: int,
    height: int,
    evidence_dir: Path,
) -> ScreenshotEvidence:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # type: ignore
    except Exception as exc:
        raise RuntimeError("crawl4ai is not installed") from exc

    root = ctx.project_dir.resolve()
    active = (root / entry).resolve()
    active.relative_to(root)
    if not active.is_file():
        raise FileNotFoundError(entry)

    server = _StaticPreviewServer(root)
    server.start()
    try:
        url_path = quote(active.relative_to(root).as_posix())
        url = f"http://127.0.0.1:{server.port}/{url_path}"
        browser_config = _construct_config(
            BrowserConfig,
            {
                "headless": True,
                "viewport_width": width,
                "viewport_height": height,
            },
        )
        run_config = _construct_config(
            CrawlerRunConfig,
            {
                "screenshot": True,
                "wait_until": "networkidle",
                "page_timeout": 15000,
            },
        )
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
        screenshot = str(_result_value(result, "screenshot") or "").strip()
        if not screenshot:
            raise RuntimeError("crawl4ai returned no screenshot")
        if "," in screenshot and screenshot.lower().startswith("data:"):
            screenshot = screenshot.split(",", 1)[1]
        png = base64.b64decode(screenshot, validate=False)
        if not png:
            raise RuntimeError("crawl4ai returned an empty screenshot")
        evidence_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = evidence_dir / f"{viewport}-{width}x{height}.png"
        screenshot_path.write_bytes(png)
        screenshot_ref = screenshot_path.relative_to(ctx.conversation_dir.resolve()).as_posix()
        return ScreenshotEvidence(screenshot_ref=screenshot_ref)
    finally:
        server.stop()


def _construct_config(cls: type, values: dict[str, Any]) -> Any:
    try:
        params = inspect.signature(cls).parameters
    except Exception:
        params = {}
    if params:
        accepts_kwargs = any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values())
        if not accepts_kwargs:
            values = {key: value for key, value in values.items() if key in params}
    return cls(**values)


def _result_value(result: Any, name: str) -> Any:
    if isinstance(result, dict):
        return result.get(name)
    return getattr(result, name, None)


class _StaticPreviewServer:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("preview server is not running")
        return int(self._server.server_port)

    def start(self) -> None:
        root = self.root

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(root), **kwargs)

            def list_directory(self, path: str):  # noqa: ANN001
                self.send_error(404, "Directory listing disabled")
                return None

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is not None:
            with contextlib.suppress(Exception):
                server.shutdown()
            with contextlib.suppress(Exception):
                server.server_close()
        if thread is not None:
            with contextlib.suppress(Exception):
                thread.join(timeout=1)
