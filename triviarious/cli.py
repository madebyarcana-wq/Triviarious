"""コマンドラインインターフェース。

使い方:
  python -m triviarious themes                       # テロップデザイン一覧のプレビュー生成
  python -m triviarious generate "お題" -o out/      # 台本(JSON+Markdown)を生成
  python -m triviarious render out/script.json --theme pop   # 台本から動画を生成
  python -m triviarious create "お題" --theme pop    # 台本生成→動画生成まで一括
  python -m triviarious doctor                       # 実行環境の診断
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from .script_schema import ScriptError, slugify, total_duration, validate_script
from .themes import DEFAULT_THEME, THEMES


def _load_script(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"エラー: 台本ファイルが見つかりません: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"エラー: 台本JSONの構文エラー: {e}")
    try:
        return validate_script(data)
    except ScriptError as e:
        sys.exit(f"エラー: 台本の内容が不正です: {e}")


def _write_outputs(script: dict, out_dir: Path) -> tuple[Path, Path]:
    from .script_md import script_to_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "script.json"
    md_path = out_dir / "台本.md"
    json_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(script_to_markdown(script), encoding="utf-8")
    return json_path, md_path


def cmd_themes(args) -> None:
    if args.list:
        print("利用可能なテロップテーマ:")
        for name, (label, desc) in THEMES.items():
            print(f"  {name:8s} {label} — {desc}")
        return
    from .renderer import render_theme_previews

    gallery = render_theme_previews(Path(args.out), sample_telop=args.text)
    print(f"\nブラウザで開いて確認してください: {gallery}")
    print("気に入ったテーマ名を render / create の --theme に指定します。")


def cmd_generate(args) -> Path:
    from .script_gen import generate_script

    script = generate_script(
        args.topic,
        style=args.style,
        length_sec=args.length,
        model=args.model,
        max_searches=args.max_searches,
    )
    out_dir = Path(args.out) if args.out else _default_out_dir(script)
    json_path, md_path = _write_outputs(script, out_dir)
    print(f"\n台本JSON: {json_path}")
    print(f"台本Markdown: {md_path}")
    print(f"合計尺: 約{total_duration(script)}秒 / シーン{len(script['scenes'])}個")
    print("\n★ 動画にする前に 台本.md の内容と出典を確認・編集してください。")
    print(f"★ 次のステップ: python -m triviarious render {json_path} --theme {DEFAULT_THEME}")
    return json_path


def _default_out_dir(script: dict) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    return Path("output") / f"{stamp}_{slugify(script['meta']['title'])}"


def cmd_render(args) -> None:
    from .renderer import RenderOptions, render_video

    script_path = Path(args.script)
    script = _load_script(script_path)
    out = Path(args.out) if args.out else script_path.parent / "video.mp4"
    opts = RenderOptions(
        theme=args.theme,
        fps=args.fps,
        quality=args.quality,
        keep_frames=args.keep_frames,
        asset_dir=script_path.parent,
    )
    render_video(script, out, opts)


def cmd_create(args) -> None:
    json_path = cmd_generate(args)
    print()
    args.script = str(json_path)
    args.out = args.video_out or str(json_path.parent / "video.mp4")
    cmd_render(args)


def cmd_serve(args) -> None:
    from .server import serve

    serve(host=args.host, port=args.port, open_browser=not args.no_browser)


def cmd_doctor(args) -> None:
    from . import capture, encoder

    print("=== 環境診断 ===")
    try:
        browser = capture.find_browser()
        print(f"[OK] ブラウザ: {browser}")
    except Exception as e:
        print(f"[NG] ブラウザ: {e}")
    try:
        info = encoder.probe()
        print(f"[OK] ffmpeg: {info.path}")
        print(f"     エンコーダ: {info.encoder} → .{info.container} / "
              f"中間画像: {info.frame_format}")
        if info.container != "mp4":
            print("     ※ H.264が使えないため出力はwebmになります。"
                  "TikTokはwebmも投稿可能ですが、mp4推奨なら full版ffmpeg を導入してください。")
    except Exception as e:
        print(f"[NG] ffmpeg: {e}")
    try:
        import anthropic  # noqa: F401

        print("[OK] anthropic SDK(台本生成が利用可能)")
    except ImportError:
        print("[--] anthropic SDK なし(render のみ利用可能。generate には "
              "`pip install anthropic` が必要)")
    import os

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("[OK] APIキー設定あり")
    else:
        print("[--] ANTHROPIC_API_KEY 未設定(generate 実行時に必要)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="triviarious",
        description="お題からTikTok向け縦型動画(1080x1920)と台本を生成するツール",
    )
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("themes", help="テロップデザイン候補のプレビューを生成")
    t.add_argument("-o", "--out", default="output/themes", help="出力先ディレクトリ")
    t.add_argument("--text", help="プレビューに使うサンプルテロップ")
    t.add_argument("--list", action="store_true", help="テーマ名の一覧だけ表示")
    t.set_defaults(func=cmd_themes)

    def add_gen_args(sp):
        sp.add_argument("topic", help="動画のお題・内容(例: タコの意外な生態)")
        sp.add_argument("--style", default="雑学", help="雰囲気(雑学/解説/ハウツー等。既定: 雑学)")
        sp.add_argument("--length", type=int, default=45, help="想定尺・秒(既定: 45)")
        sp.add_argument("--model", default="claude-opus-4-8", help="使用モデル")
        sp.add_argument("--max-searches", type=int, default=8, help="Web検索の最大回数")
        sp.add_argument("-o", "--out", help="出力先ディレクトリ(既定: output/日時_タイトル)")

    g = sub.add_parser("generate", help="お題から台本(JSON+Markdown)を生成")
    add_gen_args(g)
    g.set_defaults(func=cmd_generate)

    def add_render_args(sp):
        sp.add_argument("--theme", default=DEFAULT_THEME,
                        help=f"テロップテーマ({'/'.join(THEMES)})")
        sp.add_argument("--fps", type=int, default=30, help="フレームレート(既定: 30)")
        sp.add_argument("--quality", choices=["draft", "normal", "high"], default="normal",
                        help="draft=静止(高速) / normal=標準 / high=アニメ滑らか")
        sp.add_argument("--keep-frames", action="store_true", help="中間フレーム画像を残す")

    r = sub.add_parser("render", help="台本JSONから動画を生成")
    r.add_argument("script", help="台本JSONのパス")
    r.add_argument("-o", "--out", help="出力動画パス(既定: 台本と同じ場所の video.mp4)")
    add_render_args(r)
    r.set_defaults(func=cmd_render)

    c = sub.add_parser("create", help="台本生成→動画生成まで一括実行")
    add_gen_args(c)
    add_render_args(c)
    c.add_argument("--video-out", help="出力動画パス")
    c.set_defaults(func=cmd_create)

    s = sub.add_parser("serve", help="Web UI(検索バー+テーマ選択+色調整)を起動")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    s.set_defaults(func=cmd_serve)

    d = sub.add_parser("doctor", help="実行環境(ブラウザ/ffmpeg/APIキー)を診断")
    d.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit("\n中断しました")
    except Exception as e:
        sys.exit(f"エラー: {e}")


if __name__ == "__main__":
    main()
