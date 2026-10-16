"""Chromium/Chrome ヘッドレスでHTMLを1080x1920の静止画にキャプチャする。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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
        # headless_shell は表示領域がウィンドウサイズと一致するので最優先
        for pattern in ("chromium_headless_shell*/chrome-linux/headless_shell",
                        "chromium*/chrome-linux/chrome"):
            for p in sorted(Path(pw_root).glob(pattern), reverse=True):
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


_COMMON_FLAGS = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    "--force-device-scale-factor=1",
]

_deficit_cache: dict[str, int] = {}


def _headless_flags(browser: str) -> list[list[str]]:
    if "headless_shell" in Path(browser).name:
        return [[]]
    return [["--headless=new"], ["--headless"]]


def viewport_deficit(browser: str) -> int:
    """新ヘッドレスChromeで表示領域がウィンドウより何px短いかを測る。

    Chromeの --headless=new は表示領域が --window-size より短くなり、
    そのまま撮ると画面下に帯が残る。差分だけウィンドウを広げて撮るために使う。
    """
    if browser in _deficit_cache:
        return _deficit_cache[browser]
    deficit = 0
    if "headless_shell" not in Path(browser).name:
        with tempfile.TemporaryDirectory() as d:
            probe = Path(d) / "vp.html"
            probe.write_text(
                "<html><body><script>document.body.textContent="
                "'VP='+innerHeight</script></body></html>",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [browser, "--headless=new", *_COMMON_FLAGS,
                 f"--window-size={WIDTH},{HEIGHT}", "--dump-dom", probe.as_uri()],
                capture_output=True, text=True, timeout=60,
            )
            m = re.search(r"VP=(\d+)", proc.stdout)
            if m:
                deficit = max(0, HEIGHT - int(m.group(1)))
    _deficit_cache[browser] = deficit
    return deficit


def screenshot(browser: str, html_path: Path, out: Path, t: float | None = None) -> Path:
    """html_path を(必要なら ?t=秒 を付けて)キャプチャして out に保存する。

    出力形式は out の拡張子で決まる(.png / .jpg)。表示領域の不足分だけ
    縦に長く撮る場合があり、その余白はエンコード時に切り落とす。
    """
    url = html_path.resolve().as_uri()
    if t is not None:
        url += f"?t={t:.4f}"
    height = HEIGHT + viewport_deficit(browser)
    for flags in _headless_flags(browser):
        proc = subprocess.run(
            [browser, *flags, *_COMMON_FLAGS, f"--window-size={WIDTH},{height}",
             f"--screenshot={out}", url],
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
