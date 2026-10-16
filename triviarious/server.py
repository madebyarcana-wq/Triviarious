"""ローカルWebアプリのサーバ(標準ライブラリのみ)。

`python -m triviarious serve` で起動 → ブラウザで:
  1. 検索バーにお題を入力
  2. テーマにカーソルを合わせて選び、色をピッカーで調整(プレビュー即反映)
  3. 「動画を作る」ボタンで台本(API)と動画を生成し、その場で再生

プレビューはブラウザ内でCSSを使ってリアルタイム描画するため、色調整のたびに
サーバへ問い合わせません。台本生成と動画レンダリングだけをサーバで処理します。
"""

from __future__ import annotations

import datetime as _dt
import json
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .script_schema import slugify, total_duration, validate_script
from .themes import THEME_ADJUST, THEMES, all_theme_css, layout_css

_WEB_DIR = Path(__file__).parent / "webapp"
OUTPUT_ROOT = Path("output")


def _theme_meta() -> list[dict]:
    return [
        {
            "name": name,
            "label": label,
            "desc": desc,
            "adjust": [
                {"var": var, "label": alabel, "default": default}
                for var, alabel, default in THEME_ADJUST.get(name, [])
            ],
        }
        for name, (label, desc) in THEMES.items()
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = "Triviarious"

    # ----- 共通 -----
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def log_message(self, fmt, *args):  # ログを静かに
        pass

    # ----- GET -----
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._send(200, (_WEB_DIR / "index.html").read_bytes(),
                           "text/html; charset=utf-8")
            elif path == "/api/config":
                from .themes.motifs import MOTIFS, motif_svg

                self._json(200, {
                    "themes": _theme_meta(),
                    "layout_css": layout_css(),
                    "theme_css": all_theme_css(),
                    "motifs": {k: {"label": v[0], "svg": motif_svg(k)} for k, v in MOTIFS.items()},
                })
            elif path.startswith("/output/"):
                self._serve_output(path)
            else:
                self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": str(e)})

    def _serve_output(self, path: str) -> None:
        rel = unquote(path[len("/output/"):])
        target = (OUTPUT_ROOT / rel).resolve()
        if not str(target).startswith(str(OUTPUT_ROOT.resolve())) or not target.is_file():
            self._json(404, {"error": "not found"})
            return
        ctype = {
            ".mp4": "video/mp4", ".webm": "video/webm",
            ".json": "application/json", ".md": "text/markdown; charset=utf-8",
            ".png": "image/png",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    # ----- POST -----
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/generate":
                self._api_generate()
            elif path == "/api/render":
                self._api_render()
            else:
                self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": str(e)})

    def _api_generate(self) -> None:
        req = self._read_json()
        topic = (req.get("topic") or "").strip()
        if not topic:
            self._json(400, {"error": "お題(topic)を入力してください"})
            return
        from .script_gen import generate_script

        script = generate_script(
            topic,
            style=req.get("style") or "雑学",
            length_sec=int(req.get("length") or 45),
            model=req.get("model") or "claude-opus-4-8",
            max_searches=int(req.get("max_searches") or 8),
            log=lambda *a: None,
        )
        out_dir = self._new_out_dir(script)
        self._write_script(script, out_dir)
        self._json(200, {
            "script": script,
            "out_dir": str(out_dir),
            "total_sec": total_duration(script),
            "md_url": f"/output/{out_dir.name}/台本.md",
        })

    def _api_render(self) -> None:
        req = self._read_json()
        script = validate_script(req["script"])
        theme = req.get("theme") or "pop"
        overrides = req.get("overrides") or {}
        quality = req.get("quality") or "normal"
        out_dir_name = req.get("out_dir")

        out_dir = Path(out_dir_name) if out_dir_name else self._new_out_dir(script)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._write_script(script, out_dir)

        from .renderer import RenderOptions, render_video

        opts = RenderOptions(theme=theme, quality=quality, overrides=overrides)
        video = render_video(script, out_dir / "video.mp4", opts, log=lambda *a: None)
        self._json(200, {
            "video_url": f"/output/{out_dir.name}/{video.name}",
            "md_url": f"/output/{out_dir.name}/台本.md",
            "out_dir": str(out_dir),
        })

    # ----- helpers -----
    def _new_out_dir(self, script: dict) -> Path:
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return OUTPUT_ROOT / f"{stamp}_{slugify(script['meta']['title'])}"

    def _write_script(self, script: dict, out_dir: Path) -> None:
        from .script_md import script_to_markdown

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "script.json").write_text(
            json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "台本.md").write_text(script_to_markdown(script), encoding="utf-8")


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    OUTPUT_ROOT.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Triviarious Web UI: {url}")
    print("停止するには Ctrl+C")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
        httpd.shutdown()
