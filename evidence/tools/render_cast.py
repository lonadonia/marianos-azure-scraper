"""Render an asciinema v2 recording to a WebM video, with no screen recorder: a page replays the recording's output
events in a terminal-sized text area and Playwright's Chromium records that page (Playwright's own VP8 encoder).
What is drawn is exactly what the recording holds, in its order. Idle time between two events is capped (--idle) and
each command's end is held for --hold seconds, so the video is shorter than the recording; the .cast keeps the real
timing. Only line-oriented output is supported (the recorder writes no cursor movement).

usage: python render_cast.py IN.cast OUT.webm [--idle 1.5] [--hold 3.0]
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#16181d}
#t{box-sizing:border-box;width:__W__px;height:__H__px;margin:0;padding:12px 14px;overflow:hidden;
 color:#e1e4e8;background:#16181d;font:15px/19px Consolas,"DejaVu Sans Mono",monospace;white-space:pre}
.n{color:#98c379}.c{color:#61afef}.w{color:#e5c07b}.e{color:#f07178}.x{color:#7f848e}
</style></head><body><pre id="t"></pre><script>
const EV=__EV__, IDLE=__IDLE__, HOLD=__HOLD__, ROWS=__ROWS__;
const t=document.getElementById('t'); let lines=[''];
function cls(s){if(s.startsWith('# '))return 'n';if(s.startsWith('$ '))return 'c';
 if(s.startsWith('[exit 0]'))return 'x';if(s.startsWith('[exit'))return 'e';
 if(/ (WARN|ERROR) /.test(s.slice(0,16)))return 'w';return '';}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
function draw(){const v=lines.slice(-ROWS);t.innerHTML=v.map(s=>{const c=cls(s);return c?'<span class="'+c+'">'+esc(s)+'</span>':esc(s)}).join('\\n');}
function put(text){const parts=text.split('\\r\\n');lines[lines.length-1]+=parts[0];for(let i=1;i<parts.length;i++)lines.push(parts[i]);draw();}
let i=0, prev=0;
function step(){ if(i>=EV.length){setTimeout(()=>{document.title='done'},2500);return;}
 const [ts,text]=EV[i]; let d=Math.min(Math.max(ts-prev,0),IDLE); if(i>0&&EV[i-1][1].startsWith('[exit'))d=Math.max(d,HOLD);
 prev=ts; i++; setTimeout(()=>{put(text);step();}, d*1000);}
setTimeout(step, 800);
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cast")
    ap.add_argument("out")
    ap.add_argument("--idle", type=float, default=1.5)
    ap.add_argument("--hold", type=float, default=3.0)
    a = ap.parse_args()
    with open(a.cast, encoding="utf-8") as f:
        head = json.loads(f.readline())
        ev = [json.loads(x) for x in f if x.strip()]
    ev = [[e[0], e[2]] for e in ev if e[1] == "o"]
    cols, rows = int(head["width"]), int(head["height"])
    w, h = int(cols * 8.25) + 28, rows * 19 + 24
    w, h = w + (w % 2), h + (h % 2)
    html = (
        PAGE.replace("__W__", str(w)).replace("__H__", str(h)).replace("__ROWS__", str(rows))
        .replace("__IDLE__", str(a.idle)).replace("__HOLD__", str(a.hold))
        .replace("__EV__", json.dumps(ev, ensure_ascii=False).replace("</", "<\\/"))
    )  # fmt: skip
    tmp = Path(tempfile.mkdtemp(prefix="cast_"))
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={"width": w, "height": h}, record_video_dir=str(tmp), record_video_size={"width": w, "height": h})
        pg = c.new_page()
        pg.set_content(html)
        pg.wait_for_function("document.title === 'done'", timeout=0, polling=500)
        video = pg.video
        c.close()
        assert video is not None
        src = Path(video.path())
        b.close()
    shutil.move(str(src), a.out)
    shutil.rmtree(tmp, ignore_errors=True)
    print("ok", a.out, Path(a.out).stat().st_size, "bytes;", len(ev), "events;", f"{w}x{h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
