"""シーン背景に使う線画モチーフ(インラインSVG)。

すべて viewBox="0 0 100 100" の線画で、色は currentColor(テーマ側の
--motif-color)に従う。台本の scenes[].background.motif にキーを指定すると、
そのシーンの背景に大きく薄く描かれる。
"""

from __future__ import annotations

# key -> (日本語ラベル, SVGの中身)
MOTIFS: dict[str, tuple[str, str]] = {
    "box": ("箱", """
      <path d="M20 45 L50 58 L50 90 L20 77 Z"/>
      <path d="M50 58 L80 45 L80 77 L50 90 Z"/>
      <path d="M20 45 L8 33 L38 20 L50 32"/>
      <path d="M80 45 L92 33 L62 20 L50 32"/>
      <path d="M20 45 L50 32 L80 45"/>"""),
    "catbox": ("箱の中の猫", """
      <path d="M38 40 L35 22 L45 31 C48 30 52 30 55 31 L65 22 L62 40"/>
      <circle cx="44" cy="37" r="1.6"/><circle cx="56" cy="37" r="1.6"/>
      <path d="M20 45 L50 58 L50 90 L20 77 Z"/>
      <path d="M50 58 L80 45 L80 77 L50 90 Z"/>
      <path d="M20 45 L8 33 L30 23"/>
      <path d="M80 45 L92 33 L70 23"/>
      <path d="M20 45 L38 37 M62 37 L80 45"/>"""),
    "cat": ("猫", """
      <path d="M35 88 C29 70 30 56 38 47 L33 22 L45 36 C48 35 52 35 55 36 L67 22 L62 47 C70 56 71 70 65 88 Z"/>
      <path d="M65 84 C80 84 86 72 79 61"/>
      <circle cx="44" cy="47" r="1.8"/><circle cx="56" cy="47" r="1.8"/>
      <path d="M47 54 L50 56 L53 54"/>"""),
    "atom": ("原子・放射性", """
      <circle cx="50" cy="50" r="5" fill="currentColor"/>
      <ellipse cx="50" cy="50" rx="40" ry="14"/>
      <ellipse cx="50" cy="50" rx="40" ry="14" transform="rotate(60 50 50)"/>
      <ellipse cx="50" cy="50" rx="40" ry="14" transform="rotate(120 50 50)"/>"""),
    "poison": ("毒・危険", """
      <path d="M42 14 H58 V26 C72 32 76 44 76 56 V82 C76 88 72 92 66 92 H34 C28 92 24 88 24 82 V56 C24 44 28 32 42 26 Z"/>
      <circle cx="50" cy="60" r="9"/>
      <circle cx="46.5" cy="59" r="1.8"/><circle cx="53.5" cy="59" r="1.8"/>
      <path d="M38 80 L62 72 M38 72 L62 80"/>"""),
    "flask": ("実験・化学", """
      <path d="M42 14 H58 M45 14 V38 L26 76 C23 82 27 86 33 86 H67 C73 86 77 82 74 76 L55 38 V14"/>
      <path d="M32 64 H68"/><circle cx="45" cy="74" r="2"/><circle cx="56" cy="70" r="1.5"/>"""),
    "superposition": ("重なり・2つの状態", """
      <circle cx="38" cy="50" r="26"/><circle cx="62" cy="50" r="26"/>
      <path d="M50 28 V72" stroke-dasharray="3 4"/>"""),
    "document": ("論文・資料", """
      <path d="M26 10 H60 L76 26 V90 H26 Z"/><path d="M60 10 V26 H76"/>
      <path d="M34 40 H66 M34 50 H66 M34 60 H66 M34 70 H54"/>"""),
    "book": ("本・知識", """
      <path d="M50 28 C40 20 22 20 12 24 V80 C22 76 40 76 50 84 C60 76 78 76 88 80 V24 C78 20 60 20 50 28 Z"/>
      <path d="M50 28 V84"/>"""),
    "question": ("疑問", """
      <path d="M34 32 C34 14 66 14 66 32 C66 46 50 46 50 62"/>
      <circle cx="50" cy="78" r="3.5" fill="currentColor"/>"""),
    "lightbulb": ("ひらめき・答え", """
      <path d="M50 14 C34 14 26 27 26 40 C26 50 32 56 38 62 V72 H62 V62 C68 56 74 50 74 40 C74 27 66 14 50 14 Z"/>
      <path d="M40 80 H60 M43 87 H57"/>
      <path d="M44 62 L50 46 L56 62"/>"""),
    "light": ("光", """
      <circle cx="50" cy="50" r="14"/>
      <path d="M50 12 V24 M50 76 V88 M12 50 H24 M76 50 H88 M23 23 L31 31 M69 69 L77 77 M77 23 L69 31 M31 69 L23 77"/>"""),
    "wave": ("空気・波", """
      <path d="M8 34 C20 24 32 44 44 34 C56 24 68 44 80 34 C86 29 90 30 92 32"/>
      <path d="M8 52 C20 42 32 62 44 52 C56 42 68 62 80 52 C86 47 90 48 92 50"/>
      <path d="M8 70 C20 60 32 80 44 70 C56 60 68 80 80 70 C86 65 90 66 92 68"/>"""),
    "comment": ("コメント・会話", """
      <path d="M18 22 H82 C86 22 88 24 88 28 V64 C88 68 86 70 82 70 H46 L30 84 V70 H18 C14 70 12 68 12 64 V28 C12 24 14 22 18 22 Z"/>
      <circle cx="35" cy="46" r="3" fill="currentColor"/><circle cx="50" cy="46" r="3" fill="currentColor"/><circle cx="65" cy="46" r="3" fill="currentColor"/>"""),
    "clock": ("時間・歴史", """
      <circle cx="50" cy="50" r="36"/><path d="M50 50 V26 M50 50 L66 60"/>
      <path d="M50 18 V22 M50 78 V82 M18 50 H22 M78 50 H82"/>"""),
    "globe": ("世界・地理", """
      <circle cx="50" cy="50" r="36"/><ellipse cx="50" cy="50" rx="16" ry="36"/>
      <path d="M14 50 H86 M19 32 H81 M19 68 H81"/>"""),
    "magnifier": ("調べる・発見", """
      <circle cx="42" cy="42" r="22"/><path d="M58 58 L84 84"/>"""),
    "eye": ("見る・観測", """
      <path d="M8 50 C28 22 72 22 92 50 C72 78 28 78 8 50 Z"/>
      <circle cx="50" cy="50" r="12"/><circle cx="50" cy="50" r="4" fill="currentColor"/>"""),
    "heart": ("健康・気持ち", """
      <path d="M50 82 C20 60 10 42 22 28 C32 16 46 22 50 32 C54 22 68 16 78 28 C90 42 80 60 50 82 Z"/>"""),
    "leaf": ("自然・植物", """
      <path d="M20 80 C20 40 50 18 82 18 C82 52 60 80 20 80 Z"/><path d="M20 80 L66 34"/>"""),
    "coin": ("お金", """
      <circle cx="50" cy="50" r="34"/>
      <path d="M38 30 L50 48 L62 30 M50 48 V72 M40 52 H60 M40 61 H60"/>"""),
    "chart": ("データ・推移", """
      <path d="M18 16 V82 H86"/><path d="M26 70 L42 52 L54 60 L76 32"/>
      <circle cx="76" cy="32" r="3" fill="currentColor"/>"""),
    "star": ("ポイント・注目", """
      <path d="M50 12 L60 38 L88 40 L66 58 L74 86 L50 70 L26 86 L34 58 L12 40 L40 38 Z"/>"""),
    "house": ("家・実家", """
      <path d="M14 48 L50 18 L86 48"/><path d="M22 42 V86 H78 V42"/>
      <path d="M42 86 V64 H58 V86"/><path d="M30 52 H40 V60 H30 Z M60 52 H70 V60 H60 Z"/>"""),
    "shack": ("古い小屋", """
      <path d="M16 52 L48 26 L84 50"/><path d="M22 47 L23 86 H78 L77 46"/>
      <path d="M40 86 V66 L54 65 V86"/><path d="M30 58 L44 70 M44 58 L30 70"/>
      <path d="M60 30 L60 22 L68 22 L68 37"/>"""),
    "crown": ("勝者・富", """
      <path d="M16 72 L22 32 L38 52 L50 24 L62 52 L78 32 L84 72 Z"/><path d="M16 80 H84"/>
      <circle cx="22" cy="30" r="3"/><circle cx="50" cy="22" r="3"/><circle cx="78" cy="30" r="3"/>"""),
    "key": ("鍵・手がかり", """
      <circle cx="32" cy="38" r="16"/><circle cx="32" cy="38" r="6"/>
      <path d="M44 50 L82 88 M64 70 L72 62 M72 78 L80 70"/>"""),
    "scale": ("公平・裁き", """
      <path d="M50 14 V84 M30 84 H70 M18 28 H82"/>
      <path d="M18 28 L8 56 H28 Z M82 28 L72 56 H92 Z"/>"""),
    "envelope": ("手紙・遺言", """
      <path d="M12 26 H88 V78 H12 Z"/><path d="M12 26 L50 56 L88 26"/>
      <path d="M12 78 L40 50 M88 78 L60 50"/>"""),
    "tear": ("涙・悲しみ", """
      <path d="M50 12 C50 12 24 46 24 62 C24 78 36 88 50 88 C64 88 76 78 76 62 C76 46 50 12 50 12 Z"/>
      <path d="M38 64 C38 72 43 77 50 78"/>"""),
    "palette": ("色・デザイン", """
      <path d="M50 14 C28 14 12 30 12 50 C12 70 28 86 46 86 C52 86 54 82 52 76 C50 70 54 66 60 66 H70 C80 66 88 58 88 48 C88 28 70 14 50 14 Z"/>
      <circle cx="32" cy="46" r="5"/><circle cx="44" cy="30" r="5"/><circle cx="62" cy="30" r="5"/><circle cx="72" cy="46" r="5"/>"""),
}


def motif_svg(key: str) -> str:
    """モチーフのSVG要素(<svg>…</svg>)を返す。未知のキーは空文字。"""
    if key not in MOTIFS:
        return ""
    return (
        '<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
        f'xmlns="http://www.w3.org/2000/svg">{MOTIFS[key][1]}</svg>'
    )


def motif_keys() -> list[str]:
    return list(MOTIFS)
