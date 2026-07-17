"""テロップデザインテーマの定義とHTML組み立て。"""

from __future__ import annotations

import html as _html
import re
import string
from pathlib import Path

_THEME_DIR = Path(__file__).parent

# name -> (表示名, 説明)
THEMES: dict[str, tuple[str, str]] = {
    "pop": ("ポップ/バラエティ", "白文字+黒縁取り・強調は黄色。エンタメ・雑学・驚き系に"),
    "news": ("ニュース/解説", "白カード+紺文字+赤アクセント。情報・ビジネス・時事系に"),
    "cinema": ("シネマ/落ち着き", "暗背景+明朝体+金アクセント。歴史・教養・ストーリー系に"),
    "neon": ("ネオン/サイバー", "黒背景+発光文字。テック・ガジェット・ミステリー系に"),
    "marker": ("マーカー/シンプル", "白背景+黒太字+蛍光ペン強調。ハウツー・学習系に"),
}

DEFAULT_THEME = "pop"

# 各テーマで色調整できるスロット: (CSS変数, ラベル, カラーピッカー用の既定色)
# 背景が既定でグラデーションのテーマは、ピッカー用に代表的な単色を既定値にする。
THEME_ADJUST: dict[str, list[tuple[str, str, str]]] = {
    "pop": [
        ("--ov-bg", "背景", "#ff4d6d"),
        ("--ov-accent", "強調", "#ffe600"),
        ("--ov-text", "本文", "#ffffff"),
    ],
    "news": [
        ("--ov-bg", "背景", "#e8eef5"),
        ("--ov-accent", "アクセント", "#d7263d"),
        ("--ov-text", "見出し", "#0d2149"),
    ],
    "cinema": [
        ("--ov-bg", "背景", "#0b0b0f"),
        ("--ov-accent", "アクセント", "#c9a86a"),
        ("--ov-text", "本文", "#f5f1e6"),
    ],
    "neon": [
        ("--ov-bg", "背景", "#05010d"),
        ("--ov-glow", "発光", "#00fff0"),
        ("--ov-accent", "強調", "#ff2fb3"),
    ],
    "marker": [
        ("--ov-bg", "背景", "#fffdf6"),
        ("--ov-accent", "蛍光ペン", "#ffd60a"),
        ("--ov-text", "本文", "#1a1a1a"),
    ],
}

# 背景色スロットを持つテーマでは、単色背景に付随して微調整が要る変数も一緒に設定する
_BG_COMPANION = {
    "pop": ["--ov-bg-solid"],  # kickerの文字色を背景色に合わせる
}


def theme_css(name: str) -> str:
    path = _THEME_DIR / f"{name}.css"
    if not path.exists():
        raise ValueError(f"未知のテーマです: {name}(利用可能: {', '.join(THEMES)})")
    return path.read_text(encoding="utf-8")


def layout_css() -> str:
    return (_THEME_DIR / "layout.css").read_text(encoding="utf-8")


def all_theme_css() -> dict[str, str]:
    """全テーマのCSSを {name: css} で返す(Webのライブプレビュー用)。"""
    return {name: theme_css(name) for name in THEMES}


def _base_template() -> string.Template:
    return string.Template((_THEME_DIR / "base.html").read_text(encoding="utf-8"))


def valid_overrides(theme: str, overrides: dict[str, str] | None) -> dict[str, str]:
    """テーマが受け付ける調整スロットだけを残し、色値を検証して返す。"""
    if not overrides:
        return {}
    allowed = {var for var, _, _ in THEME_ADJUST.get(theme, [])}
    out: dict[str, str] = {}
    for var, value in overrides.items():
        if var in allowed and _is_color(value):
            out[var] = value
    # 背景色に付随する変数を補完
    if "--ov-bg" in out:
        for comp in _BG_COMPANION.get(theme, []):
            out.setdefault(comp, out["--ov-bg"])
    return out


def _is_color(v: str) -> bool:
    if not isinstance(v, str):
        return False
    v = v.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", v):
        return True
    return bool(re.fullmatch(r"(rgb|rgba|hsl|hsla)\([0-9.,%\s/]+\)", v))


def override_style(theme: str, overrides: dict[str, str] | None) -> str:
    ov = valid_overrides(theme, overrides)
    if not ov:
        return ""
    decls = " ".join(f"{var}: {val};" for var, val in ov.items())
    return f":root {{ {decls} }}"


def telop_to_html(text: str) -> str:
    """テロップ文字列をHTMLへ。改行→<br>、**強調**→<em>。"""
    escaped = _html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<em>\1</em>", escaped)
    return escaped.replace("\n", "<br>")


def build_scene_html(
    *,
    theme: str,
    role: str,
    kicker: str,
    telop: str,
    subtelop: str | None,
    scene_index: int,
    scene_total: int,
    swipe_text: str = "",
    overrides: dict[str, str] | None = None,
) -> str:
    """1シーン分の1080x1920 HTMLページを生成する。"""
    steps = "".join(
        f'<div class="step{" active" if i <= scene_index else ""}"></div>'
        for i in range(scene_total)
    )
    sub = (
        f'<div class="subtelop anim" style="--d:0.12s">{telop_to_html(subtelop)}</div>'
        if subtelop
        else ""
    )
    return _base_template().substitute(
        THEME=theme,
        ROLE=role,
        LAYOUT_CSS=layout_css(),
        THEME_CSS=theme_css(theme),
        OVERRIDE_STYLE=override_style(theme, overrides),
        KICKER=_html.escape(kicker, quote=False),
        INDEX=f"{scene_index + 1}/{scene_total}",
        TELOP=telop_to_html(telop),
        SUBTELOP=sub,
        STEPS=steps,
        SWIPE=_html.escape(swipe_text, quote=False),
    )
