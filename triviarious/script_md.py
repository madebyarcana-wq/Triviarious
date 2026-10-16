"""台本JSON → 台本Markdown(最下部に出典・BGM提案)の変換。"""

from __future__ import annotations

from .bgm import free_bgm_markdown
from .script_schema import total_duration, validate_script

ROLE_LABELS = {"hook": "フック", "body": "本編", "cta": "CTA"}


def _timecode(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m:02d}:{s:02d}"


def _background_label(bg: dict | None) -> str:
    if not bg:
        return ""
    from .themes.motifs import MOTIFS

    parts = []
    if bg.get("image"):
        parts.append(f"画像 {bg['image']}")
    elif bg.get("motif") in MOTIFS:
        parts.append(MOTIFS[bg["motif"]][0])
    color = (bg.get("colors") or {}).get("bg")
    if color:
        parts.append(color)
    return " / ".join(parts)


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def script_to_markdown(script: dict) -> str:
    script = validate_script(script)
    meta = script["meta"]
    scenes = script["scenes"]

    lines: list[str] = []
    lines.append(f"# 台本: {meta['title']}")
    lines.append("")
    lines.append(f"- **お題**: {meta['topic']}")
    lines.append(f"- **雰囲気**: {meta['style']}")
    lines.append(f"- **合計尺**: 約{total_duration(script)}秒(想定 {meta['target_length_sec']}秒)")
    lines.append(f"- **シーン数**: {len(scenes)}")
    lines.append("")

    lines.append("## 構成表")
    lines.append("")
    lines.append("| # | 時間 | 区分 | テロップ | ナレーション | 演出メモ |")
    lines.append("|---|------|------|----------|--------------|----------|")
    t = 0.0
    for i, sc in enumerate(scenes, 1):
        start = _timecode(t)
        t += sc["duration_sec"]
        end = _timecode(t)
        telop = _md_escape(sc["telop"])
        if sc.get("subtelop"):
            telop += f"<br><small>{_md_escape(sc['subtelop'])}</small>"
        memo = _md_escape(sc.get("note") or "")
        bg_desc = _background_label(sc.get("background"))
        if bg_desc:
            memo = f"背景: {bg_desc}" + (f"<br>{memo}" if memo else "")
        lines.append(
            f"| {i} | {start}–{end} | {ROLE_LABELS.get(sc['role'], sc['role'])} "
            f"| {telop} | {_md_escape(sc['narration'])} | {memo} |"
        )
    lines.append("")

    lines.append("## ナレーション全文(収録用)")
    lines.append("")
    for i, sc in enumerate(scenes, 1):
        lines.append(f"{i}. {sc['narration']}")
    lines.append("")

    if script["hashtags"]:
        lines.append("## ハッシュタグ案")
        lines.append("")
        lines.append(" ".join(script["hashtags"]))
        lines.append("")

    if script["posting_tips"]:
        lines.append("## 投稿のヒント")
        lines.append("")
        lines.append(script["posting_tips"])
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 参考資料・出典")
    lines.append("")
    if script["sources"]:
        for i, src in enumerate(script["sources"], 1):
            lines.append(
                f"{i}. **{src.get('title', '(無題)')}** — {src.get('publisher', '')}  "
            )
            lines.append(f"   <{src.get('url', '')}>(参照日: {src.get('accessed', '不明')})  ")
            if src.get("used_for"):
                lines.append(f"   ↳ 裏付けている主張: {src['used_for']}")
        lines.append("")
    else:
        lines.append("(出典情報なし — 投稿前に必ず事実確認をしてください)")
        lines.append("")

    if script["fact_check_notes"]:
        lines.append("### ファクトチェックメモ")
        lines.append("")
        lines.append(script["fact_check_notes"])
        lines.append("")

    lines.append("## BGM提案")
    lines.append("")
    if script["bgm_suggestions"]:
        for i, bgm in enumerate(script["bgm_suggestions"], 1):
            lines.append(f"### 案{i}: {bgm.get('mood', '')}")
            lines.append("")
            lines.append(f"- **ジャンル**: {bgm.get('genre', '')}")
            lines.append(f"- **テンポ**: {bgm.get('tempo', '')}")
            lines.append(f"- **理由**: {bgm.get('reason', '')}")
            kw = bgm.get("search_keywords") or []
            if kw:
                lines.append(f"- **検索キーワード**: {', '.join(kw)}")
            lines.append("")
    else:
        lines.append("(BGM提案なし)")
        lines.append("")

    lines.append(free_bgm_markdown())
    lines.append("")

    lines.append(
        "> ⚠️ 投稿前チェック: 上記の出典に目を通し、数値・固有名詞・年号が"
        "最新の情報と一致しているか確認してください。BGMは各素材サイトの利用規約"
        "(商用利用・クレジット表記)を確認のうえ使用してください。"
    )
    lines.append("")
    return "\n".join(lines)
