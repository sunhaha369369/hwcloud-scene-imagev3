#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview.py — 生成「缩略预览图」，用于验收图在网页卡片里的可读性。

用法：
    python preview.py out.png                 # 默认缩到 240px 宽（网页卡片实际尺寸）
    python preview.py out.png --width 190     # 更极端的列表缩略
    python preview.py out.png -o preview.png

为什么必须做这一步：
    1760px 的图看着很舒服，缩到 240px 经常糊成一片灰。设计阶段就要按 240px 验收，
    而不是等图上线了才发现看不清。默认输出 <原名>_preview.png。

实现上不依赖 Pillow：用同一套 headless 浏览器把 PNG 按目标宽度画在页面里再截图，
所以整个 skill 的脚本依赖仍然是 0。
"""

import os
import shutil
import subprocess
import sys

W, H = 1760, 1120


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
            if not base:
                continue
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
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def ascii_tmpdir():
    if os.name == "nt":
        base = os.environ.get("SystemDrive", "C:") + os.sep
        for root in (base, os.path.join(base, "Temp"), os.environ.get("TEMP", "")):
            if root and os.path.isdir(root):
                try:
                    import tempfile
                    return tempfile.mkdtemp(prefix="_prev_", dir=root)
                except OSError:
                    continue
    import tempfile
    return tempfile.mkdtemp(prefix="_prev_")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    src = os.path.abspath(args[0])
    if not os.path.isfile(src):
        print("[x] 找不到图片: %s" % src)
        return 2

    width = 240
    if "--width" in sys.argv:
        try:
            width = int(sys.argv[sys.argv.index("--width") + 1])
        except (IndexError, ValueError):
            pass
    height = round(width * H / W)

    dst = os.path.splitext(src)[0] + "_preview.png"
    if "-o" in sys.argv:
        dst = os.path.abspath(sys.argv[sys.argv.index("-o") + 1])

    browser = find_browser()
    if not browser:
        print("[x] 没找到 Edge / Chrome / Chromium。")
        return 1

    work = ascii_tmpdir()
    img = os.path.join(work, "src.png")
    html = os.path.join(work, "p.html")
    shot = os.path.join(work, "p.png")
    shutil.copyfile(src, img)
    with open(html, "w", encoding="utf-8") as f:
        f.write('<html><body style="margin:0;background:#fff">'
                '<img src="src.png" style="width:%dpx;display:block">'
                "</body></html>" % width)

    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--no-first-run", "--force-device-scale-factor=1",
                    "--window-size=%d,%d" % (width, height),
                    "--screenshot=%s" % shot,
                    "file:///" + html.replace("\\", "/").lstrip("/")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=60, check=False)

    if not os.path.isfile(shot):
        print("[x] 缩略图生成失败")
        return 2
    shutil.copyfile(shot, dst)
    shutil.rmtree(work, ignore_errors=True)
    print("缩略预览: %s  (%dx%d)" % (dst, width, height))
    print("→ 打开它判断：标题、每个标签的大意、重点块，还读得出来吗？")
    return 0


if __name__ == "__main__":
    sys.exit(main())
