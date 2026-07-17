"""台本JSONのスキーマ定義・検証・正規化(標準ライブラリのみ)。"""

from __future__ import annotations

import re
from typing import Any

# ナレーションの想定読み上げ速度(文字/秒)。日本語のTikTokナレーションの実測目安
CHARS_PER_SEC = 5.5
MIN_SCENE_SEC = 2.0
MAX_SCENE_SEC = 12.0

SCENE_ROLES = ("hook", "body", "cta")

# Claude API の structured outputs に渡す JSON Schema
SCRIPT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "meta": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "入力されたお題"},
                "title": {"type": "string", "description": "動画タイトル(15文字前後)"},
                "style": {"type": "string", "description": "動画の雰囲気(例: 雑学/解説/ハウツー)"},
                "target_length_sec": {"type": "number", "description": "想定尺(秒)"},
            },
            "required": ["topic", "title", "style", "target_length_sec"],
            "additionalProperties": False,
        },
        "scenes": {
            "type": "array",
            "description": "冒頭フック→本編→CTAの順のシーン列",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["hook", "body", "cta"]},
                    "telop": {
                        "type": "string",
                        "description": "画面テロップ。1行13文字以内・最大3行。改行は\\n。最重要語は**で囲む",
                    },
                    "subtelop": {
                        "type": ["string", "null"],
                        "description": "補足テロップ(任意・短く)",
                    },
                    "narration": {"type": "string", "description": "読み上げ原稿(話し言葉)"},
                    "duration_sec": {"type": "number", "description": "シーン表示秒数(2〜12秒)"},
                    "note": {
                        "type": ["string", "null"],
                        "description": "編集・演出メモ(任意)",
                    },
                },
                "required": ["role", "telop", "subtelop", "narration", "duration_sec", "note"],
                "additionalProperties": False,
            },
        },
        "sources": {
            "type": "array",
            "description": "参照した資料・出典。動画内の事実主張はすべてここに対応させる",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "publisher": {"type": "string", "description": "発行元・サイト名"},
                    "url": {"type": "string"},
                    "accessed": {"type": "string", "description": "参照日 YYYY-MM-DD"},
                    "used_for": {"type": "string", "description": "この資料が裏付ける主張"},
                },
                "required": ["title", "publisher", "url", "accessed", "used_for"],
                "additionalProperties": False,
            },
        },
        "fact_check_notes": {
            "type": "string",
            "description": "確度に関する注記。不確実な点・諸説ある点・検証できなかった点を明記",
        },
        "bgm_suggestions": {
            "type": "array",
            "description": "動画の雰囲気に合うBGMの提案(2〜3件)",
            "items": {
                "type": "object",
                "properties": {
                    "mood": {"type": "string", "description": "雰囲気(例: 軽快でコミカル)"},
                    "genre": {"type": "string", "description": "ジャンル(例: ポップ/ローファイ)"},
                    "tempo": {"type": "string", "description": "テンポ感(例: BPM100前後)"},
                    "reason": {"type": "string", "description": "この動画に合う理由"},
                    "search_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "BGM素材サイトで探す際の検索キーワード",
                    },
                },
                "required": ["mood", "genre", "tempo", "reason", "search_keywords"],
                "additionalProperties": False,
            },
        },
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "posting_tips": {"type": "string", "description": "投稿時間帯・キャプション等のアドバイス"},
    },
    "required": [
        "meta",
        "scenes",
        "sources",
        "fact_check_notes",
        "bgm_suggestions",
        "hashtags",
        "posting_tips",
    ],
    "additionalProperties": False,
}


class ScriptError(ValueError):
    pass


def estimate_duration(narration: str) -> float:
    plain = re.sub(r"\s", "", narration)
    return round(min(MAX_SCENE_SEC, max(MIN_SCENE_SEC, len(plain) / CHARS_PER_SEC + 0.4)), 1)


def validate_script(data: Any) -> dict:
    """台本dictを検証し、欠損値を補完して返す。問題があれば ScriptError。"""
    if not isinstance(data, dict):
        raise ScriptError("台本はJSONオブジェクトである必要があります")

    meta = data.get("meta")
    if not isinstance(meta, dict) or not meta.get("title"):
        raise ScriptError("meta.title がありません")
    meta.setdefault("topic", meta["title"])
    meta.setdefault("style", "雑学")
    meta.setdefault("target_length_sec", 45)

    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ScriptError("scenes が空です")
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            raise ScriptError(f"scenes[{i}] がオブジェクトではありません")
        if not sc.get("telop"):
            raise ScriptError(f"scenes[{i}].telop がありません")
        role = sc.get("role")
        if role not in SCENE_ROLES:
            sc["role"] = "hook" if i == 0 else ("cta" if i == len(scenes) - 1 else "body")
        sc.setdefault("narration", sc["telop"].replace("**", "").replace("\n", ""))
        dur = sc.get("duration_sec")
        if not isinstance(dur, (int, float)) or dur <= 0:
            sc["duration_sec"] = estimate_duration(sc["narration"])
        else:
            sc["duration_sec"] = round(min(MAX_SCENE_SEC, max(MIN_SCENE_SEC, float(dur))), 1)
        sc.setdefault("subtelop", None)
        sc.setdefault("note", None)

    for key, default in (
        ("sources", []),
        ("bgm_suggestions", []),
        ("hashtags", []),
        ("fact_check_notes", ""),
        ("posting_tips", ""),
    ):
        data.setdefault(key, default)

    return data


def total_duration(script: dict) -> float:
    return round(sum(sc["duration_sec"] for sc in script["scenes"]), 1)


def slugify(title: str, max_len: int = 40) -> str:
    """出力ディレクトリ名用のスラッグ(日本語はそのまま許容し、記号のみ除去)。"""
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", title.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] or "video"
