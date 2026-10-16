"""朗読(長尺)動画の書き出し: 1920x1080、背景+ゆっくりズーム+字幕+声(+BGM)。

流れ:
  1. 段落ごとの長さを決める(録音ファイルの長さ / 1本録音を無音で分割 / 文字数から推定)
  2. 背景画像(写真 or 線画)と、透過PNGの字幕を Chromium で描く
  3. 段落ごとに ffmpeg で「背景のゆっくりズーム + 字幕の切り替え」を作ってつなぐ
  4. 声(段落ごとの録音はつなぎ、間を入れる)とBGMを合成する
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import capture
from .story_schema import SEGMENT_PAUSE_SEC, apply_timing, subtitle_timeline
from .themes.motifs import motif_svg

W, H = 1920, 1080
FPS = 30
AUDIO_EXTS = (".wav", ".m4a", ".mp3", ".aac", ".flac", ".ogg")
DEFAULT_BG = "#141821"
DEFAULT_ACCENT = "#f2c14e"


class StoryRenderError(RuntimeError):
    pass


@dataclass
class StoryRenderOptions:
    audio_dir: Path | None = None     # 段落ごとの録音(001.wav, 002.wav, ...)
    audio: Path | None = None         # 通しで1本の録音(段落の間で黙る)
    bgm: Path | None = None
    bgm_volume: float = 0.12
    gap: float = SEGMENT_PAUSE_SEC    # 段落ごと録音のときに段落の後へ入れる間(秒)
    silence_db: float = -35.0         # 1本録音の無音判定のしきい値
    min_silence: float = 0.8          # 段落の区切りとみなす無音の長さ(秒)
    zoom: bool = True
    max_seconds: float | None = None  # 確認用に先頭だけ書き出す
    asset_dir: Path | None = None     # background.image の相対パスの基準
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    log: object = field(default=print)


# ---------------- 長さの決定 ----------------

def _probe_duration(ffprobe: str, path: Path) -> float:
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError as e:
        raise StoryRenderError(f"音声の長さを読めません: {path}") from e


def find_segment_audio(audio_dir: Path, seg_ids: list[int]) -> dict[int, Path]:
    files: dict[int, Path] = {}
    for p in sorted(audio_dir.iterdir()):
        if p.suffix.lower() in AUDIO_EXTS:
            m = re.match(r"(\d+)", p.stem)
            if m:
                files.setdefault(int(m.group(1)), p)
    missing = [i for i in seg_ids if i not in files]
    if missing:
        raise StoryRenderError(
            "録音ファイルが足りません: " + ", ".join(f"{i:03d}" for i in missing)
            + f"(フォルダ: {audio_dir})"
        )
    return {i: files[i] for i in seg_ids}


def detect_silences(ffmpeg: str, audio: Path, noise_db: float, min_silence: float) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(audio),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return list(zip(starts, ends))


def split_by_silence(opts: StoryRenderOptions, n_segments: int) -> list[tuple[float, float, float, float]]:
    """1本録音を、長い無音のうち上位 n-1 個で区切る。

    段落ごとに (区切りの開始, 区切りの終了, 話し始め, 話し終わり) を返す。
    区切りは無音の真ん中。字幕は話し始め〜話し終わりに合わせる。
    """
    total = _probe_duration(opts.ffprobe, opts.audio)
    all_sil = detect_silences(opts.ffmpeg, opts.audio, opts.silence_db, opts.min_silence)
    sil = [(s, e) for s, e in all_sil if s > 0.3 and e < total - 0.3]  # 先頭・末尾の無音は区切りにしない
    need = n_segments - 1
    if len(sil) < need:
        raise StoryRenderError(
            f"段落の区切り(長さ{opts.min_silence}秒以上の無音)が{len(sil)}箇所しか見つかりません"
            f"(必要: {need}箇所)。段落の間でもう少し長く黙るか、--min-silence を短くしてください。"
        )
    chosen = sorted(sorted(sil, key=lambda x: x[1] - x[0], reverse=True)[:need])
    lead = next((e for s, e in all_sil if s <= 0.3), 0.0)          # 録音冒頭の無音
    tail = next((s for s, e in all_sil if e >= total - 0.3), total)  # 録音末尾の無音
    bounds = [0.0] + [(s + e) / 2 for s, e in chosen] + [total]
    speech_starts = [lead] + [e for _, e in chosen]
    speech_ends = [s for s, _ in chosen] + [tail]
    return [(bounds[i], bounds[i + 1], speech_starts[i], speech_ends[i]) for i in range(n_segments)]


def decide_timing(story: dict, opts: StoryRenderOptions) -> dict[int, Path] | None:
    """段落の長さを決めて story に書き込む。段落ごと録音ならファイルの対応表を返す。"""
    ids = [sg["id"] for sg in story["segments"]]
    if opts.audio_dir:
        files = find_segment_audio(opts.audio_dir, ids)
        durs = {i: _probe_duration(opts.ffprobe, f) for i, f in files.items()}
        apply_timing(story, durs, pause=opts.gap)
        return files
    if opts.audio:
        parts = split_by_silence(opts, len(ids))
        apply_timing(story, {i: b1 - b0 for i, (b0, b1, _, _) in zip(ids, parts)}, pause=0.0)
        for sg, (b0, b1, t0, t1) in zip(story["segments"], parts):
            sg["speech_offset"] = round(t0 - b0, 3)
            sg["speech_sec"] = round(t1 - t0, 3)
        return None
    apply_timing(story)
    return None


# ---------------- 描画(HTML) ----------------

_FONT = ('"Noto Sans JP","Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",'
         'Meiryo,"IPAPGothic","IPAGothic",sans-serif')


def _mix(hex_color: str, other: str, t: float) -> str:
    """2色を t の割合で混ぜる(#rrggbb)。"""
    def rgb(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    a, b = rgb(hex_color), rgb(other)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _safe_color(v: str | None, default: str) -> str:
    return v if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", v) else default


def scene_colors(sg: dict) -> tuple[str, str]:
    colors = ((sg.get("background") or {}).get("colors")) or {}
    return _safe_color(colors.get("bg"), DEFAULT_BG), _safe_color(colors.get("accent"), DEFAULT_ACCENT)


def background_html(sg: dict, asset_dir: Path | None) -> str:
    bg, accent = scene_colors(sg)
    b = sg.get("background") or {}
    layer = ""
    image = b.get("image")
    if image:
        p = Path(image).expanduser()
        if not p.is_absolute() and asset_dir is not None:
            p = asset_dir / p
        if not p.is_file():
            raise StoryRenderError(f"背景画像が見つかりません: {image}")
        layer = (f'<div class="img" style="background-image:url(\'{p.resolve().as_uri()}\')"></div>'
                 '<div class="shade"></div>')
    elif b.get("motif"):
        layer = f'<div class="motif">{motif_svg(b["motif"])}</div>'
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden}}
body{{background:radial-gradient(ellipse 1500px 950px at 50% 40%,{_mix(bg, '#ffffff', .10)},{bg} 62%,{_mix(bg, '#000000', .55)})}}
.motif{{position:absolute;left:50%;top:40%;width:700px;height:700px;transform:translate(-50%,-50%) rotate(-6deg);
  color:{accent};opacity:.24;filter:drop-shadow(0 0 16px {accent})}}
.motif svg{{width:100%;height:100%}}
.img{{position:absolute;inset:0;background-size:cover;background-position:center}}
.shade{{position:absolute;inset:0;background:linear-gradient(rgba(0,0,0,.05) 55%,rgba(0,0,0,.45))}}
.vignette{{position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 58%,rgba(0,0,0,.5))}}
</style></head><body>{layer}<div class="vignette"></div></body></html>"""


def subtitle_html(text: str, chapter: str, accent: str, notice: str | None) -> str:
    lines = "<br>".join(_html.escape(line) for line in text.split("\n"))
    chap = f'<div class="chapter">{_html.escape(chapter)}</div>' if chapter else ""
    note = f'<div class="notice">{_html.escape(notice)}</div>' if notice else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:transparent}}
body{{font-family:{_FONT};-webkit-font-smoothing:antialiased}}
.chapter{{position:absolute;left:56px;top:44px;font-weight:700;font-size:30px;color:#fff;
  background:rgba(0,0,0,.5);border-left:8px solid {accent};padding:10px 22px;border-radius:6px}}
.notice{{position:absolute;right:56px;top:48px;font-weight:500;font-size:24px;color:rgba(255,255,255,.88);
  background:rgba(0,0,0,.45);padding:8px 16px;border-radius:6px}}
.sub{{position:absolute;left:50%;bottom:52px;transform:translateX(-50%);width:1720px;height:220px;
  box-sizing:border-box;padding:0 60px;background:rgba(8,10,16,.74);border-radius:18px;
  border-top:5px solid {accent};display:flex;align-items:center;justify-content:center;text-align:center}}
.sub p{{margin:0;font-weight:800;font-size:62px;line-height:1.45;color:#fff;white-space:nowrap;
  text-shadow:0 3px 8px rgba(0,0,0,.6)}}
</style></head><body>{chap}{note}<div class="sub"><p>{lines}</p></div>
<script>
const p=document.querySelector('.sub p');let s=62;
while(p.scrollWidth>1600&&s>36){{s-=2;p.style.fontSize=s+'px';}}
</script></body></html>"""


# ---------------- 書き出し ----------------

def _run(cmd: list[str], what: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise StoryRenderError(f"{what}に失敗しました:\n{proc.stderr[-1500:]}")


def _segment_clip(opts: StoryRenderOptions, bg_png: Path, subs: list[tuple[float, float, Path]],
                  dur: float, out: Path, zoom_in: bool) -> None:
    frames = max(1, round(dur * FPS))
    cmd = [opts.ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if opts.zoom:
        cmd += ["-i", str(bg_png)]
        z = f"1+0.05*on/{frames}" if zoom_in else f"1.05-0.05*on/{frames}"
        chain = (f"[0:v]scale={W * 2}:{H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                 f":d={frames}:s={W}x{H}:fps={FPS}[b0]")
    else:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(bg_png)]
        chain = "[0:v]null[b0]"
    for _, _, png in subs:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
    parts = [chain]
    last = "b0"
    for k, (s, e, _) in enumerate(subs, start=1):
        parts.append(f"[{last}][{k}:v]overlay=0:0:enable='gte(t,{s:.3f})*lt(t,{e:.3f})'[v{k}]")
        last = f"v{k}"
    parts.append(f"[{last}]format=yuv420p[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-t", f"{dur:.3f}", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)]
    _run(cmd, f"段落の動画({out.name})の作成")


def _build_audio(opts: StoryRenderOptions, story: dict, files: dict[int, Path] | None,
                 total: float, out: Path) -> Path | None:
    """声とBGMを合成した音声(m4a)を作る。音が何もなければ None。"""
    inputs: list[str] = []
    filters: list[str] = []
    voice = None
    segs = [sg for sg in story["segments"] if sg["start_sec"] < total]
    if files:
        labels = []
        for k, sg in enumerate(segs):
            inputs += ["-i", str(files[sg["id"]])]
            dur = min(sg["duration_sec"], total - sg["start_sec"])
            filters.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,"
                           f"apad=whole_dur={dur:.3f},atrim=0:{dur:.3f}[s{k}]")
            labels.append(f"[s{k}]")
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[voice]")
        voice = "[voice]"
    elif opts.audio:
        inputs += ["-i", str(opts.audio)]
        filters.append(f"[0:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f}[voice]")
        voice = "[voice]"
    if opts.bgm:
        k = len(inputs) // 2
        inputs += ["-stream_loop", "-1", "-i", str(opts.bgm)]
        fade = max(0.0, total - 3)
        filters.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},"
                       f"volume={opts.bgm_volume},afade=t=out:st={fade:.3f}:d=3[bgm]")
        if voice:
            filters.append(f"{voice}[bgm]amix=inputs=2:duration=first:normalize=0[mix]")
            voice = "[mix]"
        else:
            voice = "[bgm]"
    if not voice:
        return None
    _run([opts.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *inputs,
          "-filter_complex", ";".join(filters), "-map", voice, "-t", f"{total:.3f}",
          "-c:a", "aac", "-b:a", "192k", str(out)], "音声の合成")
    return out


def render_story(story: dict, out_path: Path, opts: StoryRenderOptions) -> Path:
    log = opts.log
    if not shutil.which(opts.ffmpeg):
        raise StoryRenderError("ffmpeg が見つかりません(朗読動画にはフル機能の ffmpeg が必要です)")
    files = decide_timing(story, opts)
    total = story["total_sec"]
    if opts.max_seconds:
        total = min(total, opts.max_seconds)
    segs = [sg for sg in story["segments"] if sg["start_sec"] < total]
    src = ("段落ごとの録音" if files else "1本録音(無音で分割)" if opts.audio else "文字数からの推定")
    log(f"長さ: {total/60:.1f}分 / 段落{len(segs)}個 / 時間の決め方: {src}")

    browser = capture.find_browser()
    work = Path(tempfile.mkdtemp(prefix="ttv_story_"))
    try:
        # 1) 背景(同じ見た目は1枚を使い回す)と字幕の画像を描く
        bg_jobs, sub_jobs = [], []
        bg_files: dict[str, Path] = {}
        seg_bg: dict[int, Path] = {}
        seg_subs: dict[int, list[tuple[float, float, Path]]] = {}
        notice = story["meta"].get("fiction_notice") or None
        for sg in segs:
            key = json.dumps(sg.get("background") or {}, sort_keys=True, ensure_ascii=False)
            if key not in bg_files:
                n = len(bg_files)
                h = work / f"bg{n:03d}.html"
                h.write_text(background_html(sg, opts.asset_dir), encoding="utf-8")
                bg_files[key] = work / f"bg{n:03d}.png"
                bg_jobs.append((h, bg_files[key], None))
            seg_bg[sg["id"]] = bg_files[key]
            _, accent = scene_colors(sg)
            items = []
            for k, (s, e, text) in enumerate(subtitle_timeline(sg)):
                h = work / f"s{sg['id']:03d}_{k:02d}.html"
                show_notice = notice if sg is segs[0] else None
                h.write_text(subtitle_html(text, sg.get("chapter", ""), accent, show_notice), encoding="utf-8")
                png = work / f"s{sg['id']:03d}_{k:02d}.png"
                sub_jobs.append((h, png, None))
                items.append((s, e, png))
            seg_subs[sg["id"]] = items
        log(f"描画: 背景{len(bg_jobs)}枚 / 字幕{len(sub_jobs)}枚")
        capture.screenshot_many(browser, bg_jobs, size=(W, H))
        capture.screenshot_many(browser, sub_jobs, size=(W, H), transparent=True)

        # 2) 段落ごとの動画(並列に作る)
        clips = [work / f"clip{n:03d}.mp4" for n in range(len(segs))]
        done = 0

        def _make(n: int) -> None:
            nonlocal done
            sg = segs[n]
            dur = min(sg["duration_sec"], total - sg["start_sec"])
            _segment_clip(opts, seg_bg[sg["id"]], seg_subs[sg["id"]], dur, clips[n], zoom_in=(n % 2 == 0))
            done += 1
            print(f"\r  段落の動画 {done}/{len(segs)}", end="", flush=True)

        workers = max(1, min(4, (os.cpu_count() or 2) // 2))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_make, range(len(segs))))
        print()
        listing = work / "clips.txt"
        listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
        video = work / "video_only.mp4"
        _run([opts.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
              "-i", str(listing), "-c", "copy", str(video)], "動画の連結")

        # 3) 音声
        audio = _build_audio(opts, story, files, total, work / "audio.m4a")
        out_path = out_path.with_suffix(".mp4")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if audio:
            _run([opts.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(audio),
                  "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-t", f"{total:.3f}",
                  "-movflags", "+faststart", str(out_path)], "音声の合成")
        else:
            _run([opts.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
                  "-c", "copy", "-movflags", "+faststart", str(out_path)], "書き出し")
            log("音声なしで書き出しました(録音を入れると字幕が声に合わせて配置されます)")
        log(f"完了: {out_path}")
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
