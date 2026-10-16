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
    import shutil
    import subprocess

    full = shutil.which("ffmpeg")
    if full:
        filters = subprocess.run([full, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        encs = subprocess.run([full, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        need = [f for f in ("zoompan", "overlay", "silencedetect", "amix") if f" {f} " not in filters]
        need += [e for e in ("libx264", "aac") if f" {e} " not in encs]
        if need:
            print(f"[NG] 朗読動画: ffmpeg に足りない機能があります: {', '.join(need)}")
        else:
            print("[OK] 朗読動画(story-render)に必要な ffmpeg の機能あり")
    else:
        print("[--] 朗読動画(story-render)には PATH 上のフル機能の ffmpeg が必要です")
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


# ---------------- 朗読(長尺)動画 ----------------

def _load_story(path: Path) -> dict:
    from .story_schema import validate_story

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"エラー: 台本ファイルが見つかりません: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"エラー: 台本JSONの構文エラー: {e}")
    try:
        return validate_story(data)
    except ScriptError as e:
        sys.exit(f"エラー: 台本の内容が不正です: {e}")


def _write_story(story: dict, out_dir: Path, md_name: str = "収録用台本.md") -> tuple[Path, Path]:
    from .story_md import story_to_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "story.json"
    keep = {k: v for k, v in story.items() if k != "total_sec"}
    keep["segments"] = [{k: v for k, v in sg.items()
                         if k not in ("start_sec", "duration_sec", "speech_sec", "timing_source")}
                        for sg in story["segments"]]
    json_path.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = out_dir / md_name
    md_path.write_text(story_to_markdown(story), encoding="utf-8")
    return json_path, md_path


def cmd_story_generate(args) -> None:
    from .story_check import check_story, format_checks
    from .story_gen import generate_story

    story = generate_story(args.premise, minutes=args.minutes, genre=args.genre,
                           model=args.model, max_searches=args.max_searches)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = Path(args.out) if args.out else Path("output") / f"{stamp}_{slugify(story['meta']['title'])}"
    json_path, md_path = _write_story(story, out_dir)
    print(f"\n物語台本: {json_path}\n収録用台本: {md_path}\n")
    print(format_checks(check_story(story)))
    print(f"\n★ 収録用台本を確認・修正してから録音し、次を実行してください:\n"
          f"  python -m triviarious story-render {json_path} --audio-dir 録音フォルダ")


def _story_render_opts(args, story_path: Path):
    from .story_render import StoryRenderOptions

    get = lambda name, default=None: getattr(args, name, default)  # noqa: E731
    return StoryRenderOptions(
        audio_dir=Path(args.audio_dir) if get("audio_dir") else None,
        audio=Path(args.audio) if get("audio") else None,
        bgm=Path(args.bgm) if get("bgm") else None,
        bgm_volume=get("bgm_volume", 0.12),
        gap=get("gap", 0.6),
        silence_db=get("silence_db", -35.0),
        min_silence=get("min_silence", 0.8),
        zoom=not get("no_zoom", False),
        max_seconds=get("max_seconds"),
        asset_dir=story_path.parent,
    )


def cmd_story_check(args) -> None:
    from .story_check import check_story, format_checks
    from .story_render import decide_timing

    story = _load_story(Path(args.story))
    if args.audio_dir or args.audio:
        decide_timing(story, _story_render_opts(args, Path(args.story)))
    print(format_checks(check_story(story)))


def cmd_story_render(args) -> None:
    from .story_check import check_story, format_checks
    from .story_render import render_story
    from .thumbnail import render_thumbnail

    path = Path(args.story)
    story = _load_story(path)
    if args.audio_dir and args.audio:
        sys.exit("エラー: --audio-dir と --audio はどちらか一方だけ指定してください")
    out = Path(args.out) if args.out else path.parent / "video.mp4"
    video = render_story(story, out, _story_render_opts(args, path))
    thumb = render_thumbnail(story, out.parent / "thumbnail.png", asset_dir=path.parent)
    print(f"サムネ: {thumb}")
    if args.audio_dir or args.audio:
        from .story_md import story_to_markdown

        md = out.parent / "収録用台本_録音反映.md"
        md.write_text(story_to_markdown(story), encoding="utf-8")
        print(f"録音の長さを反映した台本: {md}")
    print()
    print(format_checks(check_story(story)))


def cmd_story_thumb(args) -> None:
    from .thumbnail import render_thumbnail

    path = Path(args.story)
    out = render_thumbnail(_load_story(path), Path(args.out) if args.out else path.parent / "thumbnail.png",
                           asset_dir=path.parent)
    print(f"サムネ: {out}")


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

    sg = sub.add_parser("story-generate", help="朗読(長尺)動画の物語台本を生成")
    sg.add_argument("premise", help="題材・設定(例: 姉は1億円の相続、私はボロ小屋)")
    sg.add_argument("--minutes", type=float, default=10, help="目標の長さ(分)。既定: 10")
    sg.add_argument("--genre", default="遺産相続・家族の不公平・逆転劇")
    sg.add_argument("--model", default="claude-opus-4-8")
    sg.add_argument("--max-searches", type=int, default=8, help="法律・制度の確認に使うWeb検索の最大回数")
    sg.add_argument("-o", "--out", help="出力先ディレクトリ")
    sg.set_defaults(func=cmd_story_generate)

    def add_audio_args(sp):
        sp.add_argument("--audio-dir", help="段落ごとの録音フォルダ(001.wav, 002.wav, ...)")
        sp.add_argument("--audio", help="通しで1本の録音(段落の間で1.5秒ほど黙る)")
        sp.add_argument("--gap", type=float, default=0.6, help="段落ごと録音のとき段落の後に入れる間(秒)")
        sp.add_argument("--min-silence", type=float, default=0.8, help="1本録音で段落の区切りとみなす無音(秒)")
        sp.add_argument("--silence-db", type=float, default=-35.0, help="無音とみなす音量(dB)")

    sc = sub.add_parser("story-check", help="物語台本をルール(冒頭3秒・感情曲線など)でチェック")
    sc.add_argument("story", help="story.json のパス")
    add_audio_args(sc)
    sc.set_defaults(func=cmd_story_check)

    sr = sub.add_parser("story-render", help="物語台本から横長の朗読動画とサムネを書き出す")
    sr.add_argument("story", help="story.json のパス")
    sr.add_argument("-o", "--out", help="出力動画パス(既定: 台本と同じ場所の video.mp4)")
    add_audio_args(sr)
    sr.add_argument("--bgm", help="BGMの音声ファイル(任意。ループして小さく流す)")
    sr.add_argument("--bgm-volume", type=float, default=0.12, help="BGMの音量(0〜1。既定: 0.12)")
    sr.add_argument("--no-zoom", action="store_true", help="背景のゆっくりズームを止める(書き出しが速くなる)")
    sr.add_argument("--max-seconds", type=float, help="確認用に先頭だけ書き出す(秒)")
    sr.set_defaults(func=cmd_story_render)

    st = sub.add_parser("story-thumb", help="物語台本からサムネ(1280x720)を作る")
    st.add_argument("story", help="story.json のパス")
    st.add_argument("-o", "--out", help="出力画像パス")
    st.set_defaults(func=cmd_story_thumb)

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
