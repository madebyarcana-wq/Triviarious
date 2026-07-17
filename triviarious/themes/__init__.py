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


def theme_css(name: str) -> str:
    path = _THEME_DIR / f"{name}.css"
    if not path.exists():
        raise ValueError(f"未知のテーマです: {name}(利用可能: {', '.join(THEMES)})")
    return path.read_text(encoding="utf-8")


def _base_template() -> string.Template:
    return string.Template((_THEME_DIR / "base.html").read_text(encoding="utf-8"))


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
        THEME_CSS=theme_css(theme),
        KICKER=_html.escape(kicker, quote=False),
        INDEX=f"{scene_index + 1}/{scene_total}",
        TELOP=telop_to_html(telop),
        SUBTELOP=sub,
        STEPS=steps,
        SWIPE=_html.escape(swipe_text, quote=False),
    )
