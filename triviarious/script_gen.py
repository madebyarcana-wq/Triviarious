"""Claude API(Web検索付き)でお題から台本JSONを生成する。

- モデル: claude-opus-4-8(--model で変更可)
- Web検索ツールで事実確認を行い、出典URLを sources に必ず記録させる
- structured outputs(output_config.format)でスキーマ準拠のJSONを保証
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any

from .script_schema import SCRIPT_JSON_SCHEMA, validate_script

DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
あなたはTikTokのショート動画(縦型・30〜60秒)を専門とする放送作家兼ファクトチェッカーです。
与えられたお題から、視聴維持率と保存率が高くなる構成の台本を1本作成してください。

## 最重要ルール(正確性)
- 動画に含めるすべての事実主張は、必ずWeb検索で信頼できる情報源(公的機関、学術機関、
  大手報道機関、専門機関、一次資料)を確認してから採用すること。
- 検索で裏付けが取れなかった主張は使わない。面白さのために誇張・断定しない。
- 数値・年号・固有名詞は特に慎重に確認する。諸説ある場合は「〜と言われている」と表現し、
  fact_check_notes にその旨を書く。
- 使用した情報源はすべて sources に記録する(title / publisher / url / accessed / used_for)。
  url は検索結果に実際に表示されたものだけを使い、推測でURLを作らないこと。
- 医療・健康・金融・法律に関わる断定的な助言はしない。

## 構成ルール
- title は思わずタップしたくなる15文字前後のフック的タイトルにする(誇張はしない)。
- scenes は「hook(1シーン)→ body(4〜7シーン)→ cta(1シーン)」の順。
- hook: 最初の3秒で惹きつける最重要パート。疑問形・意外な事実・数字を使い、
  「続きが見たい」と思わせる。結論を先に少しだけ見せて引っ張る。
- body: 1シーン=1メッセージ。テンポよく、次が見たくなる引きを作る。
- cta: 保存・フォローを自然に促す一言。
- ナレーションは冗長にしない。間延びする言い回し・繰り返しを避け、
  無音や中だるみが生まれないテンポ重視の話し言葉にする(声入れ前提)。
- telop(画面テロップ)は1行13文字以内・最大3行(改行は\\n)。
  最も重要な単語を1つだけ **で囲んで強調する(例: 実は**心臓が3つ**ある)。
- narration(読み上げ原稿)は自然な話し言葉。テロップと同じ内容を少し詳しく話す。
- duration_sec はナレーション文字数÷5.5+0.5秒を目安に2〜12秒。合計が想定尺に収まること。

## BGM提案ルール(BGMは動画に組み込まず、探す手がかりだけ提示する)
- 動画の雰囲気・テンポに合うBGMを2〜3件提案する。具体的な曲名ではなく、
  ジャンル・ムード・BPM感を書く。
- search_keywords には、DOVA-SYNDROME・YouTubeオーディオライブラリ・甘茶の音楽工房・
  PeriTune 等のフリーBGMサイトでそのまま検索して見つかる語(日本語/英語)を入れる。

必ず指定されたJSONスキーマに従って出力してください。
"""


def _build_user_prompt(topic: str, style: str, length_sec: int) -> str:
    today = _dt.date.today().isoformat()
    return (
        f"お題: {topic}\n"
        f"動画の雰囲気: {style}\n"
        f"想定尺: 約{length_sec}秒\n"
        f"今日の日付: {today}(sources.accessed に使用)\n\n"
        "まずWeb検索でこのお題の事実関係を確認し、そのうえで台本を作成してください。"
    )


def generate_script(
    topic: str,
    *,
    style: str = "雑学",
    length_sec: int = 45,
    model: str = DEFAULT_MODEL,
    max_searches: int = 8,
    log=print,
) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "anthropic パッケージが必要です: pip install anthropic"
        ) from e

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log("注意: ANTHROPIC_API_KEY が未設定です(ant auth login のプロファイルがあれば動作します)")

    client = anthropic.Anthropic()
    log(f"台本を生成中… (model={model}, Web検索最大{max_searches}回)")

    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": SCRIPT_JSON_SCHEMA},
        },
        tools=[
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": max_searches,
            }
        ],
        messages=[{"role": "user", "content": _build_user_prompt(topic, style, length_sec)}],
    )

    try:
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()
    except anthropic.BadRequestError:
        # 構造化出力とWeb検索の併用が拒否された場合はフォーマット指定なしで再試行
        log("structured outputs が使えなかったため、通常出力で再試行します")
        kwargs["output_config"] = {"effort": "high"}
        kwargs["system"] = (
            SYSTEM_PROMPT
            + "\n出力は次のJSONスキーマに完全準拠したJSONのみ(前後の文章なし):\n"
            + json.dumps(SCRIPT_JSON_SCHEMA, ensure_ascii=False)
        )
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("このお題への台本生成は安全上の理由で拒否されました。別のお題をお試しください。")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("出力がトークン上限に達しました。想定尺を短くして再試行してください。")

    searches = sum(
        1 for b in response.content if getattr(b, "type", "") == "server_tool_use"
    )
    log(f"Web検索 {searches}回 実行")

    text = next(
        (b.text for b in reversed(response.content) if getattr(b, "type", "") == "text"),
        None,
    )
    if not text:
        raise RuntimeError("モデルからテキスト出力が得られませんでした")

    data = _parse_json(text)
    return validate_script(data)


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
