"""フリーBGM素材サイトのリファレンス。

BGMは動画には組み込まず、台本の最下部に「参考に使えるフリーBGMサイト」の
リンク・候補として提示する方針。各サイトの利用規約(商用利用・クレジット表記の
要否)は変わり得るため、使用前に必ず確認する旨を添える。
"""

from __future__ import annotations

# (サイト名, URL, 特徴・向いている雰囲気, 利用上の注意)
FREE_BGM_SITES: list[tuple[str, str, str, str]] = [
    (
        "DOVA-SYNDROME",
        "https://dova-s.jp/",
        "国内最大級。ポップ〜シネマティックまで幅広く、ショート向けの短尺も多い",
        "商用利用可(規約は素材ごと。クレジット任意の曲が多い)",
    ),
    (
        "YouTube オーディオ ライブラリ",
        "https://studio.youtube.com/ (YouTube Studio 内)",
        "YouTube公式。ジャンル・ムード・尺で絞り込みやすい",
        "多くが表示義務なしで商用可。曲ごとの帰属表示条件を確認",
    ),
    (
        "甘茶の音楽工房",
        "https://amachamusic.chagasi.com/",
        "やわらかい・かわいい・和風など雰囲気別に探しやすい",
        "商用利用可・クレジット表記は任意(推奨)",
    ),
    (
        "OtoLogic",
        "https://otologic.jp/",
        "BGMと効果音が揃う。落ち着いた・上品な曲が豊富で教養系に合う",
        "クレジット表記でほぼ自由に利用可(規約参照)",
    ),
    (
        "PeriTune",
        "https://peritune.com/",
        "和風・シネマティック・ファンタジー系が強い。歴史・伝統ネタに好相性",
        "クレジット表記で商用利用可(CC BY 相当。規約参照)",
    ),
    (
        "MusMus",
        "https://musmus.main.jp/",
        "BGM・ジングルが豊富。ニュース/解説系のかっちりした曲も見つかる",
        "商用利用可・クレジット任意(規約参照)",
    ),
    (
        "魔王魂",
        "https://maou.audio/",
        "曲数が多く即戦力。ポップ・ロック・8bitなどエンタメ系に",
        "規約に沿えば商用可・クレジット任意",
    ),
]


def free_bgm_markdown() -> str:
    """台本Markdownに差し込むフリーBGMサイト一覧を返す。"""
    lines = ["### 参考: フリーBGMサイト(BGMは各自でダウンロードして使用)", ""]
    for name, url, feat, note in FREE_BGM_SITES:
        lines.append(f"- **{name}** — <{url}>  ")
        lines.append(f"  {feat}  ")
        lines.append(f"  ↳ 利用条件: {note}")
    lines.append("")
    lines.append(
        "> 曲ごとに商用利用可否・クレジット表記の要否が異なります。"
        "ダウンロードページの規約を必ず確認してください。"
    )
    return "\n".join(lines)
