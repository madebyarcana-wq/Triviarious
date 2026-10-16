"""物語台本 → 収録用台本(Markdown)。"""

from __future__ import annotations

from .bgm import free_bgm_markdown
from .story_check import check_story, format_checks
from .story_schema import CURVE_STAGES, STAGE_LABELS, count_chars


def _tc(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m:02d}:{s:02d}"


def audio_filename(seg_id: int, ext: str = "wav") -> str:
    return f"{seg_id:03d}.{ext}"


def story_to_markdown(story: dict) -> str:
    meta, segs = story["meta"], story["segments"]
    timing = "録音の長さ" if all(s.get("timing_source") == "audio" for s in segs) else "文字数からの推定(約300字/分)"
    L: list[str] = []
    L += [f"# 収録用台本: {meta['title']}", ""]
    L += [f"> {meta.get('fiction_notice', '')}", ""]
    L += [f"- **ジャンル**: {meta.get('genre', '')}",
          f"- **長さ**: 約{story['total_sec']/60:.1f}分({timing}) / "
          f"{sum(count_chars(s['narration']) for s in segs)}字 / {len(segs)}段落", ""]

    L += ["## タイトル案(対比構造)", ""]
    for t in meta.get("title_candidates", []):
        L.append(f"- {'**' + t + '**(採用)' if t == meta['title'] else t}")
    L.append("")

    th = story.get("thumbnail")
    if th:
        L += ["## サムネの文言", "",
              "| 左(得をした側) | 右(損をした側) |", "|---|---|",
              f"| **{th['left_label']}**:{th['left_text']} | **{th['right_label']}**:{th['right_text']} |", "",
              f"中央の大きな文字: **{th['main_text']}**", ""]

    if story.get("characters"):
        L += ["## 登場人物", ""]
        for c in story["characters"]:
            L.append(f"- **{c['name']}**({c['role']}):{c['description']}")
        L.append("")

    L += ["## 感情曲線", "", "| 段階 | 目安 | 実際 | 気持ち | 内容 |", "|---|---|---|---|---|"]
    curve = {c["stage"]: c for c in story.get("emotion_curve", [])}
    for st, minute in CURVE_STAGES:
        first = next((s for s in segs if s["stage"] == st), None)
        expect = story["total_sec"] * minute / 10
        c = curve.get(st, {})
        score = c.get("score")
        bar = ""
        if isinstance(score, int):
            bar = ("▼" * -score) if score < 0 else ("▲" * score)
        L.append(f"| {STAGE_LABELS[st]} | {_tc(expect)} | {_tc(first['start_sec']) if first else '—'} "
                 f"| {score if score is not None else ''} {bar} | {c.get('summary', '')} |")
    L.append("")

    if story.get("twists"):
        ids = {s["id"]: s for s in segs}
        L += ["## 予想外の展開", ""]
        for t in story["twists"]:
            sg = ids.get(t["segment_id"])
            L.append(f"- [{_tc(sg['start_sec']) if sg else '??'}] 段落{t['segment_id']}: {t['description']}")
        L.append("")

    pr = story.get("promise")
    if pr:
        L += ["## タイトルの約束と回収", "",
              f"- 約束: {pr['made_in_title']}",
              f"- 回収: 段落{pr['fulfilled_segment_id']} — {pr['how']}", ""]

    L += ["## 録音のしかた", "",
          "どちらかの方法で録音すると、字幕が声に合わせて自動で配置されます。", "",
          "1. **段落ごとに録音**(おすすめ): 段落ごとに別のファイルにし、"
          "下の各段落にある名前(例 `001.wav`)で1つのフォルダに保存する。"
          "→ `python -m triviarious story-render story.json --audio-dir 録音フォルダ`",
          "2. **通しで1本録音**: 段落と段落の間で **1.5秒ほど黙る**。"
          "→ `python -m triviarious story-render story.json --audio 録音.wav`(無音で段落を自動判定)", "",
          "wav / m4a / mp3 に対応しています。", ""]

    L += ["## 本文(収録用)", ""]
    chapter = None
    for s in segs:
        if s.get("chapter") and s["chapter"] != chapter:
            chapter = s["chapter"]
            L += [f"### {chapter}", ""]
        L.append(f"**[{_tc(s['start_sec'])}] 段落{s['id']}** 〈{STAGE_LABELS[s['stage']]}〉"
                 f" — 録音ファイル `{audio_filename(s['id'])}`")
        L.append("")
        L.append(s["narration"])
        if s.get("scene"):
            L.append("")
            L.append(f"<small>場面: {s['scene']}</small>")
        L.append("")
    if story.get("comment_prompt"):
        L += [f"> 最後の問いかけ: **{story['comment_prompt']}**", ""]

    L += ["---", "", "## 法律・制度の確認", ""]
    if story.get("legal_checks"):
        for c in story["legal_checks"]:
            src = f" <{c['source_url']}>" if c.get("source_url") else ""
            L.append(f"- **{c['status']}** — {c['claim']}  ")
            L.append(f"  {c['note']}{src}")
    else:
        L.append("(記録なし)")
    L.append("")

    if story.get("sources"):
        L += ["## 参考資料・出典", ""]
        for i, src in enumerate(story["sources"], 1):
            L.append(f"{i}. **{src['title']}** — {src['publisher']}  ")
            L.append(f"   <{src['url']}>(参照日: {src['accessed']})  ")
            L.append(f"   ↳ {src['used_for']}")
        L.append("")

    L += ["## BGM提案", ""]
    for i, b in enumerate(story.get("bgm_suggestions", []), 1):
        L += [f"### 案{i}: {b['mood']}", "",
              f"- **ジャンル**: {b['genre']}", f"- **テンポ**: {b['tempo']}",
              f"- **使う場面・理由**: {b['reason']}",
              f"- **検索キーワード**: {', '.join(b.get('search_keywords', []))}", ""]
    L += [free_bgm_markdown(), ""]

    L += ["## ルールチェック", "", "```", format_checks(check_story(story)), "```", ""]

    L += ["## 投稿前チェック", "",
          "- [ ] 概要欄と動画の冒頭に「この物語はフィクションです」と明記した",
          "- [ ] 実在の人物・会社・地名に似ていないか確認した",
          "- [ ] タイトルとサムネで約束したことが、本編で回収されている",
          "- [ ] 作中の法律・制度の記述を確認した(上の「法律・制度の確認」)",
          "- [ ] BGM・画像の利用規約(商用利用・クレジット表記)を確認した",
          "- [ ] 公開後、YouTube Studioの視聴維持率で、30秒・5分・8分付近の離脱を確認する", ""]
    return "\n".join(L)
