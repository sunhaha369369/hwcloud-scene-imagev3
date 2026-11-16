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

--pack 的两个前提，别顺手改掉：
  1. 定位一律在「屏蔽掉 <!-- --> 之后」的文本上做。注释里常写着 `<svg>…</svg>`
     用法示例，直接 find("</svg>") 会切在注释中间，把 sprite 截断、留下孤立的 symbol。
  2. sprite 的结尾靠 <svg> 标签配平来找，不是找第一个 </svg>——正文里到处是小 svg。
写完会做一次结构自检（配平 / symbol 是否都在 svg 内 / 数目是否等于引用数），
不通过就报错、原文件不动。
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

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
SVG_TAG_RE = re.compile(r"<svg\b[^>]*>|</svg>")


def mask_comments(text):
    """返回与 text 等长的副本，把 <!-- --> 里的字符换成空格（换行保留）。

    页面顶部的使用说明注释里常常写着 `<svg>…</svg>` 的用法示例，
    在原文上 text.index("</svg>") 会撞进注释，把 sprite 块截断在半路——
    pack 第一版就是这么把 50 枚 symbol 留在 svg 外面的。
    所以一切定位都必须在 mask 过的文本上做，再用相同下标去切原文。
    """
    out = list(text)
    for m in COMMENT_RE.finditer(text):
        for i in range(m.start(), m.end()):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def sprite_span(text):
    """找「内部含 <symbol> 的最外层 <svg> 元素」，返回 (start, end)；没有则 None。

    用标签配平来找结尾，而不是找第一个 </svg>——symbol 里可能嵌着 <svg>，
    模板正文里也有一堆独立的小 svg，找第一个必然切错。
    """
    masked = mask_comments(text)
    depth, start = 0, None
    for m in SVG_TAG_RE.finditer(masked):
        if m.group(0) == "</svg>":
            depth -= 1
            if depth == 0 and start is not None:
                if "<symbol" in masked[start:m.end()]:
                    return start, m.end()
                start = None
            elif depth < 0:          # 多余的 </svg>，重新开始配对
                depth, start = 0, None
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return None


def check_markup(text, expect_symbols):
    """打包后的结构自检，返回出错描述；没问题返回空串。"""
    opens = len(re.findall(r"<svg\b", text))
    closes = len(re.findall(r"</svg>", text))
    if opens != closes:
        return "svg 开/闭标签不平衡（%d 开 / %d 闭）" % (opens, closes)
    masked = mask_comments(text)
    stray = 0
    # 逐枚确认 symbol 都落在某个 svg 元素内
    for m in re.finditer(r"<symbol\b", masked):
        depth = 0
        for t in SVG_TAG_RE.finditer(masked, 0, m.start()):
            depth += -1 if t.group(0) == "</svg>" else 1
        if depth <= 0:
            stray += 1
    if stray:
        return "%d 枚 symbol 落在 svg 之外" % stray
    got = len(re.findall(r"<symbol\b", masked))
    if got != expect_symbols:
        return "symbol 数 %d，应为 %d" % (got, expect_symbols)
    return ""


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
        for m in re.finditer(r'href="#(i-[a-z0-9-]+)"', mask_comments(text)):
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
        else:
            span = sprite_span(text)
            if span is None:
                print("[!] %s 里既没有 sprite 也没有 %s 占位，跳过"
                      % (os.path.basename(path), PLACEHOLDER))
                continue
            new = text[:span[0]] + block + text[span[1]:]

        problem = check_markup(new, len(used))
        if problem:
            print("[x] %s 打包后结构异常：%s；已跳过，原文件未改"
                  % (os.path.basename(path), problem))
            rc = 1
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
