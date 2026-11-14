#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iconlib.py — 图标库工具：列 id、生成图标墙预览。

用法：
    python iconlib.py --list                 打印所有图标 id（按分组）
    python iconlib.py --preview icons.png    生成图标墙 PNG，用于挑图标 / 核对画得对不对

图标定义在 assets/icons.svg。它是 sprite（<symbol>）而不是普通 svg：
模板里要**内联**这段 sprite 才能用 `<use href="#i-xxx"/>`——外部文件引用在
file:// 下会被浏览器按跨域拦掉，headless 截图直接没有图标。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "..", "assets", "icons.svg")

GROUP_RE = re.compile(r"<!-- =+ (.+?) =+ -->")


def load():
    with open(ICONS, encoding="utf-8") as f:
        return f.read()


def groups(svg):
    """按注释分组返回 [(组名, [id...])]，没有分组的归入「其它」。"""
    out, cur = [], ("图标", [])
    for line in svg.splitlines():
        m = GROUP_RE.search(line)
        if m:
            if cur[1]:
                out.append(cur)
            cur = (m.group(1).strip(), [])
            continue
        m = re.search(r'<symbol id="([^"]+)"', line)
        if m:
            cur[1].append(m.group(1))
    if cur[1]:
        out.append(cur)
    return out


def find_browser():
    for env in ("SCENE_BROWSER", "CHROME_PATH", "EDGE_PATH"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            return p
    cands = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("LOCALAPPDATA", "")):
            if base:
                cands += [os.path.join(base, r"Microsoft\Edge\Application\msedge.exe"),
                          os.path.join(base, r"Google\Chrome\Application\chrome.exe")]
    elif sys.platform == "darwin":
        cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
            p = shutil.which(n)
            if p:
                cands.append(p)
    return next((c for c in cands if c and os.path.exists(c)), None)


def ascii_tmpdir(prefix="_icons_"):
    if os.name == "nt":
        base = os.environ.get("SystemDrive", "C:") + os.sep
        for root in (base, os.path.join(base, "Temp"), os.environ.get("TEMP", "")):
            if root and os.path.isdir(root):
                try:
                    return tempfile.mkdtemp(prefix=prefix, dir=root)
                except OSError:
                    pass
    return tempfile.mkdtemp(prefix=prefix)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1760px;background:#fff;font-family:"Segoe UI","Microsoft YaHei",sans-serif;padding:44px}
.grid{display:grid;grid-template-columns:repeat(8,1fr);gap:16px}
.c{background:#F7FBFF;border:1px solid #E3EFFC;border-radius:22px;padding:14px;
   display:flex;flex-direction:column;align-items:center}
.g{width:118px;height:118px;color:#2E6FCB;stroke-width:1.7}
.n{font:14px/1.4 monospace;color:#7A848F;margin-top:8px;text-align:center;word-break:break-all}
</style></head><body>{svg}<div class="grid">{cells}</div></body></html>"""


def preview(dst):
    svg = load()
    cells = "".join(
        '<div class="c"><svg class="g"><use href="#%s"/></svg>'
        '<div class="n">%s</div></div>' % (i, i)
        for _, ids in groups(svg) for i in ids)
    html = PAGE.replace("{svg}", svg).replace("{cells}", cells)

    browser = find_browser()
    if not browser:
        print("[x] 没找到 Edge / Chrome / Chromium")
        return 1
    work = ascii_tmpdir()
    page = os.path.join(work, "icons.html")
    shot = os.path.join(work, "icons.png")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--no-first-run", "--force-device-scale-factor=1",
                    "--window-size=1760,1320", "--screenshot=" + shot,
                    "file:///" + page.replace("\\", "/").lstrip("/")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    if not os.path.isfile(shot):
        print("[x] 预览图生成失败")
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    shutil.copyfile(shot, dst)
    shutil.rmtree(work, ignore_errors=True)
    print("图标墙: %s" % os.path.abspath(dst))
    return 0


def main():
    if "--list" in sys.argv or len(sys.argv) == 1:
        total = 0
        for name, ids in groups(load()):
            total += len(ids)
            print("\n[%s] %d" % (name, len(ids)))
            for i in range(0, len(ids), 5):
                print("  " + "  ".join(ids[i:i + 5]))
        print("\n共 %d 枚" % total)
        return 0
    if "--preview" in sys.argv:
        i = sys.argv.index("--preview")
        dst = sys.argv[i + 1] if len(sys.argv) > i + 1 else "icons-preview.png"
        return preview(dst)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
