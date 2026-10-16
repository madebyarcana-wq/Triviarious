"""物語台本を「朗読系で伸ばすためのルール」に照らして自動チェックする。

時刻は録音前は文字数からの推定(1分あたり約300字)。録音後は実際の長さで再チェックできる。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .story_schema import CURVE_STAGES, STAGE_LABELS, _sentences, count_chars


@dataclass
class Check:
    level: str   # "ok" / "warn"
    rule: str
    message: str


def _fmt(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


def _first(story: dict, stage: str) -> dict | None:
    return next((sg for sg in story["segments"] if sg["stage"] == stage), None)


_DECLARATION = re.compile(r"こうなるまで|なぜこうなった|お話しします|お話しさせて|話をさせて|話をします|聞いてください")


def check_story(story: dict) -> list[Check]:
    segs = story["segments"]
    total = story["total_sec"]
    out: list[Check] = []

    def add(ok: bool, rule: str, good: str, bad: str):
        out.append(Check("ok" if ok else "warn", rule, good if ok else bad))

    # 冒頭3秒
    first = segs[0]
    add(first["stage"] == "hook" and first["speech_sec"] <= 4.0, "冒頭3秒",
        f"1段落目が短いフック({first['speech_sec']:.1f}秒)",
        f"1段落目はフック(stage=hook)にして4秒以内に(現在 {first['stage']} / "
        f"{first['speech_sec']:.1f}秒)。結論につながる意外性を最初の一文で")

    # 冒頭30秒: 理不尽の提示
    inj = _first(story, "injustice")
    add(inj is not None and inj["start_sec"] <= 30, "冒頭30秒",
        f"理不尽な状況を {_fmt(inj['start_sec']) if inj else ''} に提示",
        "30秒以内に「許せない」と思わせる不公平な状況(stage=injustice)を入れる")

    # 冒頭60秒: 全体像の宣言
    ov = _first(story, "overview")
    if ov is None or ov["start_sec"] > 60:
        add(False, "冒頭60秒", "", "60秒以内に「こうなるまでの話をします」と全体像を宣言する(stage=overview)")
    else:
        add(bool(_DECLARATION.search(ov["narration"])), "冒頭60秒",
            f"{_fmt(ov['start_sec'])} に全体像を宣言",
            f"{_fmt(ov['start_sec'])} の宣言に「こうなるまでのお話をします」などの言葉がない")

    # 6段階の感情曲線(順番と位置)
    order = [s for s, _ in CURVE_STAGES]
    starts = {s: _first(story, s) for s in order}
    missing = [STAGE_LABELS[s] for s, v in starts.items() if v is None]
    if missing:
        add(False, "感情曲線", "", f"段階が足りません: {'・'.join(missing)}")
    else:
        times = [starts[s]["start_sec"] for s in order]
        add(times == sorted(times), "感情曲線(順番)", "不幸→さらに不幸→希望→絶望→逆転→完全勝利の順",
            "6段階の順番が入れ替わっています")
        tol = max(45.0, total * 0.12)
        off = []
        for s, minute in CURVE_STAGES:
            expect = total * minute / 10 - (total * 0.06 if minute == 10 else 0)
            actual = starts[s]["start_sec"]
            if abs(actual - expect) > tol:
                off.append(f"{STAGE_LABELS[s]} {_fmt(actual)}(目安 {_fmt(expect)})")
        add(not off, "感情曲線(位置)", "6段階が全体の長さに対してほぼ目安どおりの位置",
            "目安から大きくずれている段階: " + "、".join(off))

    # 感情スコアの浮き沈み
    curve = {c["stage"]: c["score"] for c in story.get("emotion_curve", [])}
    if all(s in curve for s in order):
        sc = [curve[s] for s in order]
        ups_downs = [sc[1] < sc[0], sc[2] > sc[1], sc[3] < sc[2], sc[4] > sc[3], sc[5] >= sc[4]]
        add(all(ups_downs), "浮き沈み", "下がる→上がる→下がる→上がるの起伏がある",
            f"感情スコアの起伏が設計どおりでない: {sc}")

    # 中だるみ: 同じ段階が長く続いていないか
    scale = total / 600
    long_runs = []
    i = 0
    while i < len(segs):
        j = i
        while j + 1 < len(segs) and segs[j + 1]["stage"] == segs[i]["stage"]:
            j += 1
        span = segs[j]["start_sec"] + segs[j]["duration_sec"] - segs[i]["start_sec"]
        if span > 150 * max(scale, 0.5):
            long_runs.append(f"{STAGE_LABELS[segs[i]['stage']]} が {_fmt(segs[i]['start_sec'])}〜 {span/60:.1f}分")
        i = j + 1
    add(not long_runs, "中だるみ", "同じ段階が長く続く箇所はなし",
        "展開が止まっている恐れ: " + "、".join(long_runs) + "(説明を削るか出来事を入れる)")

    # 予想外の展開
    ids = {sg["id"]: sg for sg in segs}
    tw = [t for t in story.get("twists", []) if t.get("segment_id") in ids]
    add(len(tw) >= 3, "予想外の展開", f"{len(tw)}箇所(" + "、".join(_fmt(ids[t['segment_id']]['start_sec']) for t in tw) + ")",
        f"予想外の展開が{len(tw)}箇所。3箇所以上入れる")
    if len(tw) >= 3:
        late = [t for t in tw if ids[t["segment_id"]]["start_sec"] > total * 0.85]
        add(len(late) < len(tw) - 1, "予想外の展開(配置)", "前半〜後半に分散している",
            "予想外の展開が終盤に偏っています。中盤(5分前後)にも置くと離脱を防げます")

    # カタルシスと締め
    vic, rev = _first(story, "victory"), _first(story, "reversal")
    add(vic is not None and rev is not None and vic["start_sec"] > rev["start_sec"], "カタルシス",
        "逆転のあとに完全勝利(スカッとする場面)がある", "逆転のあとに、感情を解放する完全勝利の場面を入れる")
    add(bool(story.get("comment_prompt")) and segs[-1]["stage"] in ("ending", "victory"), "締めの問いかけ",
        "最後にコメントを促す問いかけがある", "最後に視聴者がコメントしたくなる問いかけを入れる")

    # タイトル・サムネの約束
    pr = story.get("promise") or {}
    pseg = ids.get(pr.get("fulfilled_segment_id"))
    add(pseg is not None and pseg["stage"] in ("reversal", "victory"), "約束の実現",
        f"タイトルの約束を {_fmt(pseg['start_sec']) if pseg else ''} で回収",
        "タイトル・サムネで約束したことを、逆転か完全勝利の段落で必ず回収する")
    add(len(story["meta"].get("title_candidates", [])) >= 3, "タイトル案",
        f"{len(story['meta']['title_candidates'])}案", "対比構造のタイトル案を3つ以上用意する")
    add(bool(story.get("thumbnail")), "サムネ", "対比サムネの文言あり", "サムネの文言(左右の対比)がない")

    # 長さ
    target = story["meta"].get("target_minutes") or 10
    add(abs(total - target * 60) <= target * 60 * 0.2, "長さ",
        f"約{total/60:.1f}分(目標 {target}分 / {sum(count_chars(s['narration']) for s in segs)}字)",
        f"約{total/60:.1f}分。目標{target}分から2割以上ずれています")

    # 同じ語尾の連続(3回以上)
    endings = []
    for sg in segs:
        for sent in _sentences(re.sub(r"\s", "", sg["narration"])):
            core = sent.rstrip("。！？!?」』")
            if len(core) >= 3 and not sent.endswith(("」", "』")):
                endings.append((core[-3:], sg["id"]))
    runs, k = [], 0
    while k < len(endings):
        m = k
        while m + 1 < len(endings) and endings[m + 1][0] == endings[k][0]:
            m += 1
        if m - k + 1 >= 3:
            runs.append(f"「〜{endings[k][0]}」×{m-k+1}(段落{endings[k][1]}〜)")
        k = m + 1
    add(not runs, "語尾の連続", "同じ語尾が3回以上続く箇所はなし", "同じ語尾が続いています: " + "、".join(runs))

    # 創作の明示・法律の確認
    add(bool(story["meta"].get("fiction_notice")), "創作の明示", "冒頭にフィクションの表示あり",
        "「この物語はフィクションです」の表示を入れる")
    text = story["meta"].get("genre", "") + story["meta"].get("premise", "") + "".join(sg["narration"] for sg in segs)
    if re.search(r"相続|遺言|遺産|遺留分|登記|裁判", text):
        lc = story.get("legal_checks", [])
        risky = [c["claim"] for c in lc if c.get("status") == "要注意"]
        add(bool(lc) and not risky, "法律・制度の確認",
            f"作中の法律の記述 {len(lc)}件を確認済み",
            "作中の法律の記述を確認してください" + (f"(要注意: {'、'.join(risky)})" if risky else "(確認記録なし)"))
    return out


def format_checks(checks: list[Check]) -> str:
    ok = sum(c.level == "ok" for c in checks)
    lines = [f"ルールチェック: {ok}/{len(checks)} 項目OK"]
    for c in checks:
        mark = "✅" if c.level == "ok" else "⚠️"
        lines.append(f"{mark} {c.rule}: {c.message}")
    return "\n".join(lines)
