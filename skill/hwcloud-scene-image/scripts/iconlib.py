#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iconlib.py — 图标库工具：列 id、生成图标墙预览。

用法：
    python iconlib.py --list                 打印所有图标 id（按分组）
    python iconlib.py --list 图表             只打印匹配的分组
    python iconlib.py --preview icons.png    生成图标墙 PNG，用于挑图标 / 核对画得对不对
    python iconlib.py --preview a.png --group AI   只画某一组
    python iconlib.py --pack a.html b.html   把页面实际引用的图标内联进去（只打包用到的）

图标定义在 assets/icons.svg。它是 sprite（<symbol>）而不是普通 svg：
模板里要**内联**这段 sprite 才能用 `<use href="#i-xxx"/>`——外部文件引用在
file:// 下会被浏览器按跨域拦掉，headless 截图直接没有图标。
所以改完图标库、或模板里换了图标，都要跑一次 --pack 让内联副本跟上；
页面里预先写 `<!--SPRITE-->` 占位也行，--pack 会把它替换掉。
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


def pick(groups_list, key):
    """按关键字筛组；key 为空则返回全部。"""
    if not key:
        return groups_list
    hit = [(n, ids) for n, ids in groups_list if key in n]
    if not hit:
        print("[!] 没有匹配的分组：%s（可用：%s）"
              % (key, " / ".join(n for n, _ in groups_list)))
    return hit


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{width:1760px;background:#fff;font-family:"Segoe UI","Microsoft YaHei",sans-serif;padding:44px}
.grid{display:grid;grid-template-columns:repeat(8,1fr);gap:16px}
.c{background:#F7FBFF;border:1px solid #E3EFFC;border-radius:22px;padding:14px;
   display:flex;flex-direction:column;align-items:center}
.g{width:118px;height:118px;color:#2E6FCB;stroke-width:1.7}
.n{font:14px/1.4 monospace;color:#7A848F;margin-top:8px;text-align:center;word-break:break-all}
</style></head><body>{svg}<div class="grid">{cells}</div></body></html>"""

COLS = 8
ROW_H = 190          # 单行实测高度（cell 173.6 + gap 16），留了点余量


def preview(dst, key=""):
    svg = load()
    sel = pick(groups(svg), key)
    cells = "".join(
        '<div class="c"><svg class="g"><use href="#%s"/></svg>'
        '<div class="n">%s</div></div>' % (i, i)
        for _, ids in sel for i in ids)
    n = sum(len(ids) for _, ids in sel)
    if not n:
        print("[x] 没有图标可画")
        return 2
    rows = (n + COLS - 1) // COLS
    height = 88 + rows * ROW_H - 16
    html = PAGE.replace("{svg}", svg).replace("{cells}", cells)
    print("图标墙: %d 枚 · %d 行 · %dx%d" % (n, rows, 1760, height))

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
                    "--window-size=1760,%d" % height, "--screenshot=" + shot,
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


def symbol_map(svg):
    return [(m.group(1), m.group(0)) for m in
            re.finditer(r'<symbol id="([^"]+)"[^>]*>.*?</symbol>', svg, re.S)]


SPRITE_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" style="display:none"'
PLACEHOLDER = "<!--SPRITE-->"


def pack(paths):
    """把每个 html 里 <use href="#i-xxx"> 真正引用到的图标内联进去。"""
    smap = dict(symbol_map(load()))
    rc = 0
    for path in paths:
        if not os.path.isfile(path):
            print("[x] 文件不存在: %s" % path)
            rc = 1
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        used = []
        for m in re.finditer(r'href="#(i-[a-z0-9-]+)"', text):
            if m.group(1) not in used:
                used.append(m.group(1))
        unknown = [i for i in used if i not in smap]
        if unknown:
            print("[x] %s 引用了不存在的图标: %s" % (os.path.basename(path), unknown))
            rc = 1
            continue
        if not used:
            print("[!] %s 没有引用任何图标，跳过" % os.path.basename(path))
            continue

        block = (SPRITE_OPEN + ' aria-hidden="true">\n'
                 '<!-- 本文件只用 %d 枚图标；由 scripts/iconlib.py --pack 生成，'
                 '改图标请重跑 --pack -->\n' % len(used))
        block += "\n".join(smap[i].strip() for i in used)
        block += "\n</svg>"

        if PLACEHOLDER in text:
            new = text.replace(PLACEHOLDER, block)
        elif SPRITE_OPEN in text:
            start = text.index(SPRITE_OPEN)
            end = text.index("</svg>", start) + len("</svg>")
            new = text[:start] + block + text[end:]
        else:
            print("[!] %s 里既没有 sprite 也没有 %s 占位，跳过"
                  % (os.path.basename(path), PLACEHOLDER))
            continue
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        print("pack: %-24s %2d 枚  %s" % (os.path.basename(path), len(used),
                                          " ".join(used)))
    return rc


def main():
    argv = [a for a in sys.argv[1:]]
    group = ""
    if "--group" in argv:
        i = argv.index("--group")
        group = argv[i + 1] if len(argv) > i + 1 else ""
        del argv[i:i + 2]

    if "--pack" in argv:
        i = argv.index("--pack")
        return pack([a for a in argv[i + 1:] if not a.startswith("-")])

    if "--list" in argv or not argv:
        rest = [a for a in argv if not a.startswith("-")]
        total = 0
        for name, ids in pick(groups(load()), group or (rest[0] if rest else "")):
            total += len(ids)
            print("\n[%s] %d" % (name, len(ids)))
            for i in range(0, len(ids), 5):
                print("  " + "  ".join(ids[i:i + 5]))
        print("\n共 %d 枚" % total)
        return 0
    if "--preview" in argv:
        i = argv.index("--preview")
        dst = argv[i + 1] if len(argv) > i + 1 else "icons-preview.png"
        return preview(dst, group)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
