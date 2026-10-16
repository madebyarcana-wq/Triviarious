"""台本JSON → シーンHTML → キャプチャ → 動画 のオーケストレーション。"""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import capture, encoder
from .script_schema import validate_script
from .themes import DEFAULT_THEME, THEMES, build_scene_html

# 入場アニメーションをサンプリングする時間窓(秒)。テーマ中の最長アニメより長め
ANIM_WINDOW_SEC = 1.0

SWIPE_TEXTS = {"hook": "▼ 最後まで見てね", "body": "", "cta": "フォローで続きが見られます"}


@dataclass
class RenderOptions:
    theme: str = DEFAULT_THEME
    fps: int = 30
    quality: str = "normal"  # draft: アニメなし / normal: 1/2サンプリング / high: 全フレーム
    keep_frames: bool = False
    ffmpeg: str | None = None
    overrides: dict | None = None  # 色オーバーライド {"--ov-accent": "#2792c3", ...}
    asset_dir: Path | None = None  # background.image の相対パスの基準(台本ファイルの場所)


def _resolve_background(bg: dict | None, asset_dir: Path | None) -> dict | None:
    if not bg or not bg.get("image") or asset_dir is None:
        return bg
    img = Path(bg["image"]).expanduser()
    if not img.is_absolute() and (asset_dir / img).is_file():
        bg = {**bg, "image": str((asset_dir / img).resolve())}
    return bg


def _capture_step(fps: int, quality: str) -> int:
    """出力何フレームごとに1枚キャプチャするか(0=アニメなし)。"""
    return {"draft": 0, "normal": 2, "high": 1}.get(quality, 2)


def render_video(script: dict, out_path: Path, opts: RenderOptions, log=print) -> Path:
    script = validate_script(script)
    if opts.theme not in THEMES:
        raise ValueError(f"未知のテーマです: {opts.theme}(利用可能: {', '.join(THEMES)})")

    browser = capture.find_browser()
    info = encoder.probe(opts.ffmpeg)
    log(f"ブラウザ: {browser}")
    log(f"エンコード: {info.label}")

    scenes = script["scenes"]
    title = script["meta"]["title"]
    step = _capture_step(opts.fps, opts.quality)

    workdir = Path(tempfile.mkdtemp(prefix="ttv_frames_"))
    try:
        # 1) シーンHTMLとキャプチャジョブを作る
        jobs: list[tuple[Path, Path, float | None]] = []
        # frame_plan_parts[i] = [(画像パス, 繰り返し数), ...]
        frame_plan_parts: list[list[tuple[Path, int]]] = []

        for i, sc in enumerate(scenes):
            html_path = workdir / f"scene_{i:02d}.html"
            html_path.write_text(
                build_scene_html(
                    theme=opts.theme,
                    role=sc["role"],
                    kicker=title,
                    telop=sc["telop"],
                    subtelop=sc.get("subtelop"),
                    scene_index=i,
                    scene_total=len(scenes),
                    swipe_text=SWIPE_TEXTS.get(sc["role"], ""),
                    overrides=opts.overrides,
                    background=_resolve_background(sc.get("background"), opts.asset_dir),
                ),
                encoding="utf-8",
            )

            total_frames = max(1, round(sc["duration_sec"] * opts.fps))
            part: list[tuple[Path, int]] = []
            used = 0
            if step > 0:
                n_capture = min(
                    int(ANIM_WINDOW_SEC * opts.fps / step), total_frames // step
                )
                for k in range(n_capture):
                    t = (k * step) / opts.fps
                    img = workdir / f"s{i:02d}_a{k:03d}.{info.frame_format}"
                    jobs.append((html_path, img, t))
                    repeat = min(step, total_frames - used)
                    part.append((img, repeat))
                    used += repeat
            hold = workdir / f"s{i:02d}_hold.{info.frame_format}"
            jobs.append((html_path, hold, None))
            if total_frames - used > 0:
                part.append((hold, total_frames - used))
            frame_plan_parts.append(part)

        # 2) キャプチャ(並列)
        log(f"キャプチャ: {len(jobs)}枚(シーン{len(scenes)}個 / {opts.quality})")

        def _progress(done, total):
            print(f"\r  {done}/{total}", end="", file=sys.stderr, flush=True)

        capture.screenshot_many(browser, jobs, on_progress=_progress)
        print(file=sys.stderr)

        # 3) エンコード
        frame_plan = [item for part in frame_plan_parts for item in part]
        total_frames = sum(r for _, r in frame_plan)
        log(f"エンコード: {total_frames}フレーム / {opts.fps}fps "
            f"≈ {total_frames / opts.fps:.1f}秒")
        out = encoder.encode_frames(info, frame_plan, out_path, fps=opts.fps)
        log(f"完了: {out}")
        return out
    finally:
        if opts.keep_frames:
            keep_dir = out_path.parent / "frames"
            if keep_dir.exists():
                shutil.rmtree(keep_dir)
            shutil.move(str(workdir), str(keep_dir))
            log(f"フレーム保存: {keep_dir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def render_theme_previews(out_dir: Path, sample_telop: str | None = None, log=print) -> Path:
    """全テーマのプレビュー画像とギャラリーHTMLを生成する。"""
    browser = capture.find_browser()
    out_dir.mkdir(parents=True, exist_ok=True)
    telop = sample_telop or "実は**タコの心臓**は\n3つある!?"

    jobs = []
    for name in THEMES:
        html_path = out_dir / f"preview_{name}.html"
        html_path.write_text(
            build_scene_html(
                theme=name,
                role="body",
                kicker="テーマプレビュー",
                telop=telop,
                subtelop="サブテロップのサンプルです",
                scene_index=1,
                scene_total=5,
            ),
            encoding="utf-8",
        )
        jobs.append((html_path, out_dir / f"preview_{name}.png", None))

    capture.screenshot_many(browser, jobs)

    cards = "\n".join(
        f'<figure><a href="preview_{name}.png"><img src="preview_{name}.png" alt="{name}"></a>'
        f"<figcaption><b>{name}</b> — {label}<br><small>{desc}</small></figcaption></figure>"
        for name, (label, desc) in THEMES.items()
    )
    gallery = out_dir / "index.html"
    gallery.write_text(
        "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
        "<title>テロップテーマ一覧</title><style>"
        "body{font-family:sans-serif;background:#f0f0f3;margin:40px}"
        "h1{font-size:22px}main{display:flex;flex-wrap:wrap;gap:24px}"
        "figure{margin:0;width:270px}img{width:270px;border-radius:12px;"
        "box-shadow:0 8px 24px rgba(0,0,0,.18)}figcaption{margin-top:8px;font-size:13px}"
        "</style></head><body><h1>テロップテーマ一覧 — 好みのテーマ名を --theme に指定してください</h1>"
        f"<main>{cards}</main></body></html>",
        encoding="utf-8",
    )
    for name in THEMES:
        (out_dir / f"preview_{name}.html").unlink(missing_ok=True)
    log(f"プレビューを生成しました: {gallery}")
    return gallery
