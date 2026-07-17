"""Chromium/Chrome ヘッドレスでHTMLを1080x1920の静止画にキャプチャする。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WIDTH, HEIGHT = 1080, 1920

_BROWSER_CANDIDATES = [
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
    "msedge",
]

_BROWSER_PATHS = [
    # Playwright バンドル
    "/opt/pw-browsers/chromium",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


class CaptureError(RuntimeError):
    pass


def find_browser() -> str:
    """利用可能なChrome/Chromium系ブラウザの実行パスを返す。"""
    env = os.environ.get("TTV_BROWSER")
    if env:
        if shutil.which(env) or Path(env).exists():
            return env
        raise CaptureError(f"TTV_BROWSER で指定されたブラウザが見つかりません: {env}")

    pw_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if pw_root:
        for p in sorted(Path(pw_root).glob("chromium*/chrome-linux/chrome"), reverse=True):
            return str(p)
        link = Path(pw_root) / "chromium"
        if link.exists():
            return str(link)

    for name in _BROWSER_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for path in _BROWSER_PATHS:
        if Path(path).exists():
            return path

    raise CaptureError(
        "Chrome / Chromium が見つかりません。インストールするか、"
        "環境変数 TTV_BROWSER に実行ファイルのパスを設定してください。"
    )


def _screenshot_cmd(browser: str, url: str, out: Path, headless_flag: str) -> list[str]:
    return [
        browser,
        headless_flag,
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={WIDTH},{HEIGHT}",
        f"--screenshot={out}",
        url,
    ]


def screenshot(browser: str, html_path: Path, out: Path, t: float | None = None) -> Path:
    """html_path を(必要なら ?t=秒 を付けて)キャプチャして out に保存する。

    出力形式は out の拡張子で決まる(.png / .jpg)。
    """
    url = html_path.resolve().as_uri()
    if t is not None:
        url += f"?t={t:.4f}"
    for flag in ("--headless=new", "--headless"):
        proc = subprocess.run(
            _screenshot_cmd(browser, url, out, flag),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return out
    raise CaptureError(
        f"スクリーンショットに失敗しました: {html_path.name}\n{proc.stderr[-800:]}"
    )


def screenshot_many(
    browser: str,
    jobs: list[tuple[Path, Path, float | None]],
    max_workers: int | None = None,
    on_progress=None,
) -> None:
    """(html, out, t) のジョブ列を並列にキャプチャする。"""
    workers = max_workers or min(6, os.cpu_count() or 4)
    done = 0

    def _one(job):
        nonlocal done
        html, out, t = job
        screenshot(browser, html, out, t)
        done += 1
        if on_progress:
            on_progress(done, len(jobs))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        # 例外を伝播させるため list() で待つ
        list(pool.map(_one, jobs))
