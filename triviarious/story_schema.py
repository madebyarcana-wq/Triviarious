"""朗読(長尺・横長)動画の物語台本: スキーマ・検証・時間推定・字幕分割。

1本の物語は segments(段落)の並び。各段落は物語上の段階(stage)を持ち、
冒頭3秒・30秒・60秒のルールと6段階の感情曲線をこの段階で表す。
"""

from __future__ import annotations

import re
from typing import Any

from .script_schema import SCRIPT_JSON_SCHEMA, ScriptError
from .themes.motifs import motif_keys

# 朗読の速さ(字/分)。一般的な朗読・ナレーションの目安
CHARS_PER_MIN = 300
CHARS_PER_SEC = CHARS_PER_MIN / 60
SEGMENT_PAUSE_SEC = 0.6  # 段落の間の間(ま)

# (キー, 表示名)
STAGES: list[tuple[str, str]] = [
    ("hook", "冒頭フック(3秒)"),
    ("injustice", "理不尽の提示(〜30秒)"),
    ("overview", "全体像の宣言(〜60秒)"),
    ("misfortune", "不幸"),
    ("worse", "さらに不幸"),
    ("hope", "希望"),
    ("despair", "絶望"),
    ("reversal", "逆転"),
    ("victory", "完全勝利"),
    ("ending", "締め・問いかけ"),
]
STAGE_LABELS = dict(STAGES)

# 6段階の感情曲線と、10分動画での目標位置(分)。動画の長さに比例させて使う
CURVE_STAGES: list[tuple[str, float]] = [
    ("misfortune", 1),
    ("worse", 3),
    ("hope", 5),
    ("despair", 7),
    ("reversal", 9),
    ("victory", 10),
]

_MOTIF_ENUM = [*motif_keys(), "none"]
_str = {"type": "string"}
_nstr = {"type": ["string", "null"]}

STORY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "meta": {
            "type": "object",
            "properties": {
                "premise": {"type": "string", "description": "入力された題材・設定"},
                "genre": {"type": "string", "description": "例: 遺産相続/家族の不公平/復讐劇"},
                "title": {"type": "string", "description": "採用するタイトル(対比構造)"},
                "title_candidates": {
                    "type": "array", "items": _str,
                    "description": "対比構造のタイトル案を5つ(採用案を含む)",
                },
                "target_minutes": {"type": "number"},
                "fiction_notice": {"type": "string", "description": "例: この物語はフィクションです。"},
            },
            "required": ["premise", "genre", "title", "title_candidates",
                         "target_minutes", "fiction_notice"],
            "additionalProperties": False,
        },
        "thumbnail": {
            "type": "object",
            "description": "不公平な状況を左右の対比で見せるサムネの文言",
            "properties": {
                "left_label": {"type": "string", "description": "得をした側の人物(例: 兄)"},
                "left_text": {"type": "string", "description": "得をした側の状況(例: 実家と預金6千万円)"},
                "left_motif": {"type": "string", "enum": _MOTIF_ENUM},
                "right_label": {"type": "string", "description": "損をした側の人物(例: 私)"},
                "right_text": {"type": "string", "description": "損をした側の状況(例: 裏山の古い小屋)"},
                "right_motif": {"type": "string", "enum": _MOTIF_ENUM},
                "main_text": {"type": "string", "description": "続きが気になる一言(例: でも小屋の奥に…)"},
            },
            "required": ["left_label", "left_text", "left_motif", "right_label",
                         "right_text", "right_motif", "main_text"],
            "additionalProperties": False,
        },
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": _str, "role": _str, "description": _str},
                "required": ["name", "role", "description"],
                "additionalProperties": False,
            },
        },
        "emotion_curve": {
            "type": "array",
            "description": "6段階の感情曲線(不幸→さらに不幸→希望→絶望→逆転→完全勝利)",
            "items": {
                "type": "object",
                "properties": {
                    "stage": {"type": "string", "enum": [s for s, _ in CURVE_STAGES]},
                    "score": {"type": "integer", "description": "-5(最悪)〜+5(最高)"},
                    "summary": _str,
                },
                "required": ["stage", "score", "summary"],
                "additionalProperties": False,
            },
        },
        "twists": {
            "type": "array",
            "description": "視聴者の予想を裏切る展開(3つ以上)",
            "items": {
                "type": "object",
                "properties": {"segment_id": {"type": "integer"}, "description": _str},
                "required": ["segment_id", "description"],
                "additionalProperties": False,
            },
        },
        "promise": {
            "type": "object",
            "description": "タイトルとサムネで約束したこと、それを本編のどこで実現するか",
            "properties": {
                "made_in_title": _str,
                "fulfilled_segment_id": {"type": "integer"},
                "how": _str,
            },
            "required": ["made_in_title", "fulfilled_segment_id", "how"],
            "additionalProperties": False,
        },
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "stage": {"type": "string", "enum": [s for s, _ in STAGES]},
                    "chapter": {"type": "string", "description": "章の見出し(画面左上に表示)"},
                    "narration": {"type": "string", "description": "朗読する本文"},
                    "scene": {"type": "string", "description": "場面の説明(背景画像を用意する時の手がかり)"},
                    "background": {
                        "type": "object",
                        "properties": {
                            "motif": {"type": "string", "enum": _MOTIF_ENUM},
                            "colors": {
                                "type": "object",
                                "properties": {"bg": _nstr, "accent": _nstr},
                                "required": ["bg", "accent"],
                                "additionalProperties": False,
                            },
                        },
                        "required": ["motif", "colors"],
                        "additionalProperties": False,
                    },
                },
                "required": ["id", "stage", "chapter", "narration", "scene", "background"],
                "additionalProperties": False,
            },
        },
        "legal_checks": {
            "type": "array",
            "description": "作中に出る法律・制度の記述と、その確認結果",
            "items": {
                "type": "object",
                "properties": {
                    "claim": _str,
                    "status": {"type": "string", "enum": ["確認済み", "要注意", "物語上の設定"]},
                    "note": _str,
                    "source_url": _nstr,
                },
                "required": ["claim", "status", "note", "source_url"],
                "additionalProperties": False,
            },
        },
        "sources": SCRIPT_JSON_SCHEMA["properties"]["sources"],
        "bgm_suggestions": SCRIPT_JSON_SCHEMA["properties"]["bgm_suggestions"],
        "comment_prompt": {"type": "string", "description": "最後にコメントを促す問いかけ"},
    },
    "required": ["meta", "thumbnail", "characters", "emotion_curve", "twists", "promise",
                 "segments", "legal_checks", "sources", "bgm_suggestions", "comment_prompt"],
    "additionalProperties": False,
}


def count_chars(text: str) -> int:
    """読み上げる文字数(空白・改行を除く)。"""
    return len(re.sub(r"\s", "", text))


def estimate_seconds(text: str) -> float:
    return round(count_chars(text) / CHARS_PER_SEC, 2)


def validate_story(data: Any) -> dict:
    """物語台本を検証し、欠損を補って時刻(start_sec/duration_sec)を付けて返す。"""
    if not isinstance(data, dict):
        raise ScriptError("物語台本はJSONオブジェクトである必要があります")
    meta = data.get("meta")
    if not isinstance(meta, dict) or not meta.get("title"):
        raise ScriptError("meta.title がありません")
    meta.setdefault("premise", meta["title"])
    meta.setdefault("genre", "")
    meta.setdefault("title_candidates", [meta["title"]])
    meta.setdefault("target_minutes", 10)
    meta.setdefault("fiction_notice", "この物語はフィクションです。")

    segs = data.get("segments")
    if not isinstance(segs, list) or not segs:
        raise ScriptError("segments が空です")
    seen = set()
    for i, sg in enumerate(segs):
        if not isinstance(sg, dict) or not sg.get("narration"):
            raise ScriptError(f"segments[{i}].narration がありません")
        sg.setdefault("id", i + 1)
        if sg["id"] in seen:
            raise ScriptError(f"segments の id が重複しています: {sg['id']}")
        seen.add(sg["id"])
        if sg.get("stage") not in STAGE_LABELS:
            sg["stage"] = "misfortune"
        sg.setdefault("chapter", "")
        sg.setdefault("scene", "")
        bg = sg.get("background")
        if not isinstance(bg, dict):
            sg["background"] = None
        elif bg.get("motif") == "none":
            bg["motif"] = None

    for key, default in (("thumbnail", None), ("characters", []), ("emotion_curve", []),
                         ("twists", []), ("promise", None), ("legal_checks", []),
                         ("sources", []), ("bgm_suggestions", []), ("comment_prompt", "")):
        data.setdefault(key, default)

    apply_timing(data)
    return data


def apply_timing(story: dict, durations: dict[int, float] | None = None,
                 pause: float = SEGMENT_PAUSE_SEC) -> dict:
    """各段落に speech_sec / duration_sec / start_sec を付ける。

    durations(段落id→話している秒数)があれば録音の長さを使い、なければ文字数から推定する。
    duration_sec は話している時間 + 段落の後の間(pause)。
    """
    t = 0.0
    for sg in story["segments"]:
        if durations and sg["id"] in durations:
            speech = durations[sg["id"]]
            sg["timing_source"] = "audio"
        else:
            speech = estimate_seconds(sg["narration"])
            sg["timing_source"] = "estimate"
        sg["speech_sec"] = round(speech, 3)
        sg["duration_sec"] = round(speech + pause, 3)
        sg["start_sec"] = round(t, 3)
        t += sg["duration_sec"]
    story["total_sec"] = round(t, 3)
    return story


# ---- 字幕の分割 ----

_ENDERS = "。！？!?」』"
_NO_BREAK_BEFORE = "」』。、！？!?"


def _sentences(text: str) -> list[str]:
    """文に分ける。かぎかっこ(「」『』)の中では切らない。"""
    out, buf, depth = [], "", 0
    for i, ch in enumerate(text):
        buf += ch
        if ch in "「『":
            depth += 1
        elif ch in "」』":
            depth = max(0, depth - 1)
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if depth == 0 and ch in _ENDERS and nxt not in _NO_BREAK_BEFORE:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def split_subtitles(text: str, max_line: int = 24, max_lines: int = 2) -> list[str]:
    """朗読文を字幕のかたまりに分ける。各かたまりは改行(\\n)入りで最大 max_lines 行。

    句読点・かぎかっこの切れ目(フレーズ)を単位に1行ずつ詰め、文の途中では
    なるべく句読点の位置で改行する。かたまりは文の境目でも区切る。
    """
    text = re.sub(r"\s+", "", text)
    chunks: list[list[str]] = []
    parts: list[str] = []
    for sentence in _sentences(text):
        # 字幕2行に収まらない長いせりふは、かぎかっこの中でも句点で区切る
        if len(sentence) > max_line * max_lines:
            parts += [p for p in re.split(r"(?<=[。！？!?])(?![」』。！？!?])", sentence) if p]
        else:
            parts.append(sentence)
    for sentence in parts:
        phrases: list[str] = []
        for ph in re.split(r"(?<=[、。！？!?」』…])(?![」』。、！？!?])", sentence):
            while len(ph) > max_line:
                phrases.append(ph[:max_line])
                ph = ph[max_line:]
            if ph:
                phrases.append(ph)
        lines: list[str] = []
        cur = ""
        for ph in phrases:
            if cur and len(cur) + len(ph) > max_line:
                lines.append(cur)
                cur = ph
            else:
                cur += ph
        if cur:
            lines.append(cur)
        for i in range(0, len(lines), max_lines):
            chunks.append(lines[i:i + max_lines])
    # 1行だけの短いかたまりは、次のかたまりとまとめて切り替えの回数を減らす
    merged: list[list[str]] = []
    for c in chunks:
        if merged and len(merged[-1]) == 1 and len(c) == 1:
            prev = merged[-1][0]
            merged[-1] = [prev + c[0]] if len(prev) + len(c[0]) <= max_line else [prev, c[0]]
        else:
            merged.append(c)
    return ["\n".join(c) for c in merged]


def subtitle_timeline(segment: dict) -> list[tuple[float, float, str]]:
    """段落内の字幕を (開始秒, 終了秒, 文) に割り付ける(段落内の相対時刻)。

    録音の長さが分かっていれば、その長さを文字数の比で配分する。
    """
    chunks = split_subtitles(segment["narration"])
    speech = max(0.5, segment.get("speech_sec") or segment["duration_sec"])
    offset = segment.get("speech_offset", 0.0)  # 段落の中で話し始めるまでの無音
    weights = [max(1, count_chars(c)) for c in chunks]
    total = sum(weights)
    out, t = [], offset
    for c, w in zip(chunks, weights):
        d = speech * w / total
        out.append((round(t, 3), round(t + d, 3), c))
        t += d
    # 最初の字幕は段落の頭から、最後の字幕は段落の終わりまで出しておく
    if out:
        _, e, c = out[0]
        out[0] = (0.0, e, c)
        s, _, c = out[-1]
        out[-1] = (s, segment["duration_sec"], c)
    return out
