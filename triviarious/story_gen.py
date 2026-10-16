"""Claude API で朗読(長尺)動画の物語台本を生成する。

視聴維持率を上げるための構成ルール(冒頭3秒・30秒・60秒、6段階の感情曲線、
予想外の展開、カタルシス、対比タイトル)を指示に組み込み、作中の法律・制度は
Web検索で確認させる。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any

from .script_gen import DEFAULT_MODEL, _parse_json
from .story_schema import CHARS_PER_MIN, STORY_JSON_SCHEMA, validate_story

STORY_SYSTEM_PROMPT = f"""\
あなたはYouTubeの朗読チャンネル(長尺・横長)を担当する放送作家です。
与えられた題材から、最後まで見られて「スカッとした」とコメントされる創作の物語を1本書きます。
語り手は1人称「私」。投稿者本人が声で朗読するので、声に出して読みやすい文章にします。

## 長さ
- 朗読の速さは1分あたり約{CHARS_PER_MIN}字。目標の分数 × {CHARS_PER_MIN}字前後の本文にする。
- 無駄に伸ばさない。説明だけの段落は作らず、どの段落でも何かが起きる・分かるようにする。

## 冒頭(ここで離脱が決まる)
- 1段落目(stage=hook): 3秒で読める1文。結論につながる意外性を見せる
  (例:「全財産を奪った兄が、親戚の前で青ざめた日の話です。」)。結論そのものは明かさない。
- 30秒以内(stage=injustice): 視聴者が「許せない」と思う不公平な状況を具体的に示す。
- 60秒以内(stage=overview): 「今日は、こうなるまでのお話をさせてください」のように全体像を宣言する。

## 感情曲線(6段階)
- 10分の動画なら、1分目:不幸 → 3分目:さらに不幸 → 5分目:希望 → 7分目:絶望 → 9分目:逆転 →
  10分目:完全勝利。長さが違えば比率を合わせる。各段落の stage をこの段階に合わせる。
- emotion_curve には各段階の気持ちを -5〜+5 で付ける。下がる→上がる→下がる→上がるの起伏を必ず作る。
  ずっと不幸は疲れ、ずっと幸せは退屈になる。
- 同じ段階を2分半以上続けない(中だるみ)。

## 展開
- 視聴者が「え、そうなるの?」と思う予想外の展開を3つ以上。終盤だけでなく中盤(5分前後)にも置く。
  twists にどの段落か書く。
- 予定調和にしない。8分目あたりで「どうせこうなる」と読めてしまう流れを避ける。
- 最後は逆転のあとに完全勝利の場面を置き、感情を解放する(カタルシス)。
  ただし暴力や違法な仕返しで勝たせない。嘘が明らかになる・正当な手続きで取り戻す、など。
- 締め(stage=ending)で、冒頭の問いに答え、コメントしたくなる問いかけで終える(comment_prompt にも書く)。

## タイトルとサムネ
- title_candidates は対比構造で5案(例:「姉は1億円の相続、私はボロ小屋。でも奥に見つけたものは…」)。
- thumbnail は不公平な状況を左右の対比で見せる文言(得をした側 vs 損をした側)。
- タイトルとサムネで約束したことを本編で必ず回収し、promise にどの段落で回収するか書く。

## 書き方
- 同じ語尾を3回続けない。話し言葉で、1文は長くしすぎない。
- 「あの人」「それ」ではなく名前で書く。決まり文句やたとえ話は使わない。
- 登場人物の名前は実在の有名人と重ならない、ありふれた名前にする。

## 正確性(重要)
- 物語は創作だが、作中に出る法律・制度(相続の割合、遺言、遺留分、手続き、期限など)は
  Web検索で確認し、事実と違う説明をしない。確認結果を legal_checks に書き、
  物語の都合で現実と違う設定にした所は status=物語上の設定 とする。
- 確認に使った資料は sources に書く。URLは検索結果に実際に出たものだけを使う。
- meta.fiction_notice に「この物語はフィクションです。」と書く。

## 背景
- 各段落の background.motif は、その段落の出来事に直接関係する絵を選ぶ(なければ none)。
  同じ絵を何段落も続けない。colors.bg は段階の気持ちに合う暗めの色(字幕が読める明るさ)。

## BGM
- 動画には組み込まない。場面に合うBGMの雰囲気を2〜3案、フリーBGMサイトで探せる検索語つきで書く。

必ず指定されたJSONスキーマに従って出力してください。
"""


def _user_prompt(premise: str, minutes: float, genre: str) -> str:
    return (
        f"題材: {premise}\n"
        f"ジャンル: {genre}\n"
        f"目標の長さ: 約{minutes:g}分(本文 約{int(minutes * CHARS_PER_MIN)}字)\n"
        f"今日の日付: {_dt.date.today().isoformat()}(sources.accessed に使用)\n\n"
        "作中に出す法律・制度をWeb検索で確認してから、物語を書いてください。"
    )


def generate_story(
    premise: str,
    *,
    minutes: float = 10,
    genre: str = "遺産相続・家族の不公平・逆転劇",
    model: str = DEFAULT_MODEL,
    max_searches: int = 8,
    log=print,
) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("anthropic パッケージが必要です: pip install anthropic") from e
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log("注意: ANTHROPIC_API_KEY が未設定です(ant auth login のプロファイルがあれば動作します)")

    client = anthropic.Anthropic()
    log(f"物語を生成中… (model={model}, 約{minutes:g}分, Web検索最大{max_searches}回)")
    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=48000,
        system=STORY_SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": STORY_JSON_SCHEMA},
        },
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}],
        messages=[{"role": "user", "content": _user_prompt(premise, minutes, genre)}],
    )
    try:
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()
    except anthropic.BadRequestError:
        log("structured outputs が使えなかったため、通常出力で再試行します")
        kwargs["output_config"] = {"effort": "high"}
        kwargs["system"] = (STORY_SYSTEM_PROMPT + "\n出力は次のJSONスキーマに完全準拠したJSONのみ:\n"
                            + json.dumps(STORY_JSON_SCHEMA, ensure_ascii=False))
        with client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("この題材での物語生成は安全上の理由で拒否されました。題材を変えてお試しください。")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("出力がトークン上限に達しました。目標の分数を短くして再試行してください。")
    text = next((b.text for b in reversed(response.content) if getattr(b, "type", "") == "text"), None)
    if not text:
        raise RuntimeError("モデルからテキスト出力が得られませんでした")
    return validate_story(_parse_json(text))
