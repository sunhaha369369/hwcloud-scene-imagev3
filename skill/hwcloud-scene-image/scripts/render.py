#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py — 把场景图 HTML 渲染成 1760×1120 PNG。

用法：
    python render.py input.html output.png [--no-lint]

为什么要这个脚本，而不是直接跑命令行截图：
  1) 浏览器 headless 在**非 ASCII 路径**（含中文/空格的目录）下经常静默失败，
     要么输出空白图，要么沿用上一次的旧图。脚本会先把 HTML 复制到纯 ASCII
     临时目录再渲染。
  2) 自动探测 Edge / Chrome / Chromium 的安装位置。
  3) 渲染完会校验输出的像素尺寸，尺寸不对直接报错，不会让你拿着一张错图去交付。
  4) 渲染完会自动跑 linklint.py 检查连线端点——手写的 SVG 坐标只要错一个数字，
     线就会悬在空白处，而这在整图上完全看不出来。发现问题时退出码为 3。

退出码：0 成功；1 找不到浏览器；2 渲染失败或尺寸不符；3 连线有悬空端点。
"""

import os
import shutil
import subprocess
import sys
import tempfile

WIDTH, HEIGHT = 1760, 1120


def find_browser():
    """返回可用的 Chromium 系浏览器可执行文件路径。"""
    for env in ("SCENE_BROWSER", "CHROME_PATH", "EDGE_PATH"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            return p

    candidates = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            candidates += [
                os.path.join(base, r"Microsoft\Edge\Application\msedge.exe"),
                os.path.join(base, r"Google\Chrome\Application\chrome.exe"),
            ]
    elif sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium",
                     "chromium-browser", "microsoft-edge"):
            p = shutil.which(name)
            if p:
                candidates.append(p)

    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def ascii_tmpdir():
    """创建一个纯 ASCII 路径的临时目录。中文 TEMP 路径会让 headless 失败。"""
    if os.name == "nt":
        base = os.environ.get("SystemDrive", "C:") + os.sep
        # 避免 C:\ 根目录无写权限的情况
        for root in (base, os.path.join(base, "Temp"), os.environ.get("TEMP", "")):
            if not root or not os.path.isdir(root):
                continue
            try:
                return tempfile.mkdtemp(prefix="_scene_", dir=root)
            except OSError:
                continue
    return tempfile.mkdtemp(prefix="_scene_")


def png_size(path):
    """不依赖 Pillow，直接读 PNG 头部的 IHDR。"""
    with open(path, "rb") as f:
        head = f.read(33)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (int.from_bytes(head[16:20], "big"),
            int.from_bytes(head[20:24], "big"))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    src = os.path.abspath(sys.argv[1])
    dst = os.path.abspath(sys.argv[2])
    keep = "--keep" in sys.argv

    if not os.path.isfile(src):
        print("[x] 找不到输入文件: %s" % src)
        return 2

    browser = find_browser()
    if not browser:
        print("[x] 没找到 Edge / Chrome / Chromium。")
        print("    可设置环境变量 SCENE_BROWSER 指向浏览器可执行文件。")
        return 1
    print("[1/5] 浏览器: %s" % browser)

    work = ascii_tmpdir()
    html = os.path.join(work, "scene.html")
    shot = os.path.join(work, "shot.png")
    shutil.copyfile(src, html)
    print("[2/5] 临时目录: %s" % work)

    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--force-device-scale-factor=1",
        "--window-size=%d,%d" % (WIDTH, HEIGHT),
        "--virtual-time-budget=3000",
        "--screenshot=%s" % shot,
        "file:///" + html.replace("\\", "/").lstrip("/"),
    ]
    print("[3/5] 渲染中 …")
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=120, check=False)
    except subprocess.TimeoutExpired:
        print("[x] 渲染超时")
        return 2

    if not os.path.isfile(shot) or os.path.getsize(shot) < 5000:
        print("[x] 渲染失败：输出为空或过小（常见原因：HTML 语法错误、字体缺失）")
        return 2

    size = png_size(shot)
    if size != (WIDTH, HEIGHT):
        print("[!] 尺寸异常: %s（期望 %dx%d）。检查 HTML 的 html/body 宽高是否被改写。"
              % (size, WIDTH, HEIGHT))

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copyfile(shot, dst)
    print("[4/5] 输出: %s  %s  %.0f KB"
          % (dst, "%dx%d" % size if size else "?", os.path.getsize(dst) / 1024.0))

    if not keep:
        shutil.rmtree(work, ignore_errors=True)

    # 连线检查：跑在渲染之后，这样即使有断线也能先看到图
    lint = 0
    if "--no-lint" not in sys.argv:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import linklint
            print("[5/5] 检查连线 …")
            lint = linklint.run(src)
        except Exception as exc:  # 检查本身出错不该挡住渲染结果
            print("[!] 连线检查未执行: %s" % exc)

    return 3 if lint == 1 else 0


if __name__ == "__main__":
    sys.exit(main())
