"""朗読動画のサムネ(1280x720): 不公平な状況を左右の対比で見せる。

左 = 得をした側(明るい金色)、右 = 損をした側(暗い青灰色)。中央下に大きな一言。
thumbnail.left_image / right_image に画像のパスを入れると、線画の代わりに使う。
"""

from __future__ import annotations

import html as _html
import tempfile
from pathlib import Path

from . import capture
from .themes.motifs import motif_svg

TW, TH = 1280, 720
_FONT = ('"Noto Sans JP","Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",'
         'Meiryo,"IPAPGothic","IPAGothic",sans-serif')


def _side(label: str, text: str, motif: str | None, image: str | None, asset_dir: Path | None) -> str:
    if image:
        p = Path(image).expanduser()
        if not p.is_absolute() and asset_dir is not None:
            p = asset_dir / p
        art = f'<div class="img" style="background-image:url(\'{p.resolve().as_uri()}\')"></div>' if p.is_file() else ""
    else:
        art = f'<div class="art">{motif_svg(motif)}</div>' if motif else ""
    return (f'{art}<div class="label">{_html.escape(label)}</div>'
            f'<div class="text">{_html.escape(text)}</div>')


def thumbnail_html(story: dict, asset_dir: Path | None = None) -> str:
    th = story.get("thumbnail") or {}
    left = _side(th.get("left_label", ""), th.get("left_text", ""), th.get("left_motif"),
                 th.get("left_image"), asset_dir)
    right = _side(th.get("right_label", ""), th.get("right_text", ""), th.get("right_motif"),
                  th.get("right_image"), asset_dir)
    main = _html.escape(th.get("main_text", story["meta"]["title"]))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{TW}px;height:{TH}px;overflow:hidden;font-family:{_FONT}}}
.side{{position:absolute;top:0;bottom:0;overflow:hidden}}
.left{{left:0;width:700px;clip-path:polygon(0 0,100% 0,82% 100%,0 100%);
  background:linear-gradient(140deg,#ffe08a,#f7a928 55%,#d9690f)}}
.right{{right:0;width:700px;clip-path:polygon(18% 0,100% 0,100% 100%,0 100%);
  background:linear-gradient(140deg,#5b6b7d,#2b3440 60%,#151a21)}}
.art{{position:absolute;top:70px;width:380px;height:380px;opacity:.55}}
.art svg{{width:100%;height:100%}}
.left .art{{left:130px;color:#fff6d5;filter:drop-shadow(0 0 18px rgba(255,255,255,.7))}}
.right .art{{right:110px;color:#c9d4e0;opacity:.45}}
.img{{position:absolute;inset:0;background-size:cover;background-position:center}}
.label{{position:absolute;top:28px;font-weight:900;font-size:44px;padding:6px 26px;border-radius:12px}}
.left .label{{left:36px;background:#fff;color:#c2410c}}
.right .label{{right:36px;background:#0f141a;color:#fff;border:3px solid #9fb0c2}}
.text{{position:absolute;top:380px;font-weight:900;font-size:58px;line-height:1.2;
  -webkit-text-stroke:12px #1a1a1a;paint-order:stroke fill;white-space:nowrap}}
.left .text{{left:40px;color:#fff}}
.right .text{{right:40px;color:#e6edf3;text-align:right}}
.vs{{position:absolute;left:50%;top:220px;transform:translateX(-50%) rotate(-8deg);font-weight:900;
  font-size:96px;color:#ff2d2d;-webkit-text-stroke:10px #fff;paint-order:stroke fill;
  text-shadow:0 8px 20px rgba(0,0,0,.5)}}
.band{{position:absolute;left:0;right:0;bottom:0;height:150px;
  background:linear-gradient(transparent,rgba(0,0,0,.55) 40%,rgba(0,0,0,.75))}}
.main{{position:absolute;left:50%;bottom:26px;transform:translateX(-50%);display:inline-block;
  font-weight:900;font-size:92px;color:#ffe600;-webkit-text-stroke:16px #111;paint-order:stroke fill;
  white-space:nowrap;text-shadow:0 10px 24px rgba(0,0,0,.6)}}
</style></head><body>
<div class="side left">{left}</div><div class="side right">{right}</div>
<div class="vs">VS</div><div class="band"></div><div class="main">{main}</div>
<script>
for (const el of document.querySelectorAll('.text,.main')) {{
  let s = parseFloat(getComputedStyle(el).fontSize);
  const max = el.classList.contains('main') ? 1220 : 600;
  while (el.getBoundingClientRect().width > max && s > 24) {{ s -= 2; el.style.fontSize = s + 'px'; }}
}}
</script></body></html>"""


def render_thumbnail(story: dict, out: Path, asset_dir: Path | None = None) -> Path:
    out = out.with_suffix(".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        h = Path(d) / "thumb.html"
        h.write_text(thumbnail_html(story, asset_dir), encoding="utf-8")
        capture.screenshot(capture.find_browser(), h, out, size=(TW, TH))
    return out
