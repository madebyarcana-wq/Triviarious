"""ffmpeg の探索・機能プローブ・静止画列からの動画エンコード。

方針: すべての見た目(フェード・アニメーション)はキャプチャ時にHTML側で
確定させ、ffmpeg は「連番静止画→動画」の単純なエンコーダとしてのみ使う。
これにより最小構成の ffmpeg ビルドでも動作する。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FFMPEG_GLOBS = [
    # Playwright バンドル (Linux / macOS / Windows)
    "/opt/pw-browsers/ffmpeg-*/ffmpeg-linux",
    str(Path.home() / ".cache/ms-playwright/ffmpeg-*/ffmpeg-linux"),
    str(Path.home() / "Library/Caches/ms-playwright/ffmpeg-*/ffmpeg-mac"),
    str(Path.home() / "AppData/Local/ms-playwright/ffmpeg-*/ffmpeg-win64.exe"),
]


class EncodeError(RuntimeError):
    pass


@dataclass
class FfmpegInfo:
    path: str
    encoder: str          # libx264 / libopenh264 / libvpx-vp9 / libvpx / mpeg4
    container: str        # mp4 / webm
    frame_format: str     # png / jpg
    frame_codec: str      # png / mjpeg

    @property
    def label(self) -> str:
        return f"{Path(self.path).name} → {self.encoder} ({self.container})"


def find_ffmpeg() -> str:
    env = os.environ.get("TTV_FFMPEG")
    if env:
        if shutil.which(env) or Path(env).exists():
            return env
        raise EncodeError(f"TTV_FFMPEG で指定された ffmpeg が見つかりません: {env}")
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    import glob as _glob

    for pattern in _FFMPEG_GLOBS:
        for p in sorted(_glob.glob(pattern), reverse=True):
            return p
    raise EncodeError(
        "ffmpeg が見つかりません。https://ffmpeg.org からインストールするか、"
        "`pip install imageio-ffmpeg`、または環境変数 TTV_FFMPEG を設定してください。"
    )


def _list_caps(ffmpeg: str, kind: str) -> str:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", f"-{kind}"], capture_output=True, text=True, timeout=60
    )
    return proc.stdout


def probe(ffmpeg: str | None = None) -> FfmpegInfo:
    """ffmpeg を探し、利用可能なエンコーダ/デコーダから出力構成を決める。"""
    path = ffmpeg or find_ffmpeg()
    encoders = _list_caps(path, "encoders")
    decoders = _list_caps(path, "decoders")

    if " libx264 " in encoders:
        enc, container = "libx264", "mp4"
    elif " libopenh264 " in encoders:
        enc, container = "libopenh264", "mp4"
    elif " libvpx-vp9 " in encoders:
        enc, container = "libvpx-vp9", "webm"
    elif " libvpx " in encoders:
        enc, container = "libvpx", "webm"
    elif " mpeg4 " in encoders:
        enc, container = "mpeg4", "mp4"
    else:
        raise EncodeError("この ffmpeg にはH.264/VP8/VP9系のエンコーダがありません")

    if " png " in decoders:
        frame_format, frame_codec = "png", "png"
    elif " mjpeg " in decoders:
        frame_format, frame_codec = "jpg", "mjpeg"
    else:
        raise EncodeError("この ffmpeg はPNG/JPEGのどちらもデコードできません")

    return FfmpegInfo(path, enc, container, frame_format, frame_codec)


def _encoder_args(info: FfmpegInfo, fps: int) -> list[str]:
    # キャプチャが縦に長い場合(新ヘッドレスChromeの表示領域補正)は上端から1080x1920に切る
    common = ["-vf", "crop=1080:1920:0:0", "-pix_fmt", "yuv420p", "-r", str(fps)]
    if info.encoder == "libx264":
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "19",
                "-profile:v", "high", "-movflags", "+faststart", *common]
    if info.encoder == "libopenh264":
        return ["-c:v", "libopenh264", "-b:v", "6M", "-movflags", "+faststart", *common]
    if info.encoder == "libvpx-vp9":
        return ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-row-mt", "1", *common]
    if info.encoder == "libvpx":
        return ["-c:v", "libvpx", "-b:v", "5M", "-qmin", "4", "-qmax", "40", *common]
    return ["-c:v", info.encoder, "-b:v", "8M", *common]


def encode_frames(
    info: FfmpegInfo,
    frame_plan: list[tuple[Path, int]],
    out: Path,
    fps: int = 30,
) -> Path:
    """frame_plan = [(画像パス, 繰り返しフレーム数), ...] を out に動画化する。"""
    out = out.with_suffix(f".{info.container}")
    cmd = [
        info.path, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "image2pipe", "-c:v", info.frame_codec,
        "-framerate", str(fps), "-i", "pipe:0",
        *_encoder_args(info, fps),
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for path, repeat in frame_plan:
            data = path.read_bytes()
            for _ in range(repeat):
                proc.stdin.write(data)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    proc.wait()
    if proc.returncode != 0 or not out.exists():
        raise EncodeError(f"エンコードに失敗しました:\n{stderr[-1200:]}")
    return out
