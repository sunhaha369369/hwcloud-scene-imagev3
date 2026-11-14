#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""linklint.py — 检查场景图里每一根连接线的端点是否真的接上了。

为什么需要它：
  连线是用绝对坐标手写的 SVG path。只要有一个数字写错，线就会悬在空白处，
  但**整张图看起来依然"像那么回事"**——尤其在 1760 尺寸下，一段 4px 的断线
  不放大根本看不出来，缩到 240px 更是完全看不见，直到图已经交付出去才发现。

  手写坐标靠眼睛查是不可靠的。这个脚本让浏览器自己算布局：把每条 path/line
  离散成采样点，检查每个端点是否
    (a) 贴着某个元素矩形的边缘，或
    (b) 与另一条线相交 / 端点重合。
  两者都不满足，就是悬空的线头，报出坐标并让退出码非 0。

用法：
    python linklint.py scene.html            # 只检查
    python linklint.py scene.html -v         # 同时列出通过的端点

退出码：0 全部接好；1 有问题；2 运行失败。
"""

import html as html_mod
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render import find_browser, ascii_tmpdir  # noqa: E402

import shutil  # noqa: E402

# 端点距元素矩形边缘多少像素内算"贴住了"
RECT_TOL = 8.0
# 端点距另一条线多少像素内算"接上了"
LINK_TOL = 3.0

JS = r"""
(function () {
  var canvas = document.querySelector('.canvas') || document.body;

  // ---- 1. 实体：画布下绝对定位的矩形块（卡片、瓦片、气泡……） ----
  var solids = [];
  canvas.querySelectorAll('div').forEach(function (d) {
    if (d.classList.contains('canvas')) return;
    var cs = getComputedStyle(d);
    if (cs.position !== 'absolute') return;
    var r = d.getBoundingClientRect();
    if (r.width < 24 || r.height < 24) return;
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    solids.push({
      cls: (d.className || 'div').toString().split(' ')[0],
      l: r.left, t: r.top, r: r.right, b: r.bottom
    });
  });

  // ---- 2. 连接线：画布直属 svg 里的 path / line（图标内部的 svg 不算） ----
  //      填充图形（箭头三角、关系菱形）不检查端点——它们的底边本来就贴在
  //      线端点上、尖端指向目标，单独检查只会产生一堆误报。但它们仍然要
  //      进入"可连接池"，因为别的线是接在它们身上的。
  var lines = [];
  canvas.querySelectorAll(':scope > svg').forEach(function (svg) {
    svg.querySelectorAll('path,line').forEach(function (p) {
      if (!p.getTotalLength) return;
      var total = p.getTotalLength();
      if (total <= 0.5) return;
      var m = p.getScreenCTM();
      if (!m) return;
      var cs = getComputedStyle(p);
      // 有描边 = 连接线；只有填充 = 箭头三角、关系菱形之类。用 stroke 判断，
      // 不能用 fill 判断：path 不写 fill 时默认是黑色，会被误判成填充图形。
      var stroked = !!(cs.stroke && cs.stroke !== 'none' && cs.stroke !== 'transparent');
      if (stroked && !(parseFloat(cs.strokeWidth) > 0)) stroked = false;
      var n = Math.max(2, Math.min(600, Math.ceil(total / 6)));
      var pts = [];
      for (var i = 0; i <= n; i++) {
        var q = p.getPointAtLength(total * i / n);
        pts.push({ x: q.x * m.a + q.y * m.c + m.e, y: q.x * m.b + q.y * m.d + m.f });
      }
      lines.push({
        check: stroked,
        d: (p.getAttribute('d') || (p.getAttribute('x1') + ',' + p.getAttribute('y1'))),
        pts: pts
      });
    });
  });

  function distToRect(p, R) {
    var dx = Math.max(R.l - p.x, 0, p.x - R.r);
    var dy = Math.max(R.t - p.y, 0, p.y - R.b);
    if (dx === 0 && dy === 0) {
      // 点在矩形内部：算到最近边界的距离。否则任何画在大卡片里的线头
      // 都会被判成"贴着 .content"，检查就失效了。
      return Math.min(p.x - R.l, R.r - p.x, p.y - R.t, R.b - p.y);
    }
    return Math.hypot(dx, dy);
  }
  function distToSeg(p, a, b) {
    var vx = b.x - a.x, vy = b.y - a.y;
    var L = vx * vx + vy * vy;
    if (L < 1e-9) return Math.hypot(p.x - a.x, p.y - a.y);
    var t = Math.max(0, Math.min(1, ((p.x - a.x) * vx + (p.y - a.y) * vy) / L));
    return Math.hypot(p.x - (a.x + t * vx), p.y - (a.y + t * vy));
  }

  var RECT_TOL = %RECT_TOL%, LINK_TOL = %LINK_TOL%;
  var bad = [], ok = [];

  // 给描边线编号，报告里用；箭头等填充图形不编号
  var no = 0;
  lines.forEach(function (l) { if (l.check) { no++; l.no = no; } });

  lines.forEach(function (ln, i) {
    if (!ln.check) return;
    [{ p: ln.pts[0], end: '起点' },
     { p: ln.pts[ln.pts.length - 1], end: '终点' }].forEach(function (cur) {
      var p = cur.p, best = 1e9, why = '';

      solids.forEach(function (R) {
        var d = distToRect(p, R);
        if (d < best) { best = d; why = '贴 ' + R.cls; }
      });

      if (best > RECT_TOL) {
        var b2 = 1e9, who = null;
        lines.forEach(function (o, j) {
          if (j === i) return;
          for (var k = 1; k < o.pts.length; k++) {
            var d = distToSeg(p, o.pts[k - 1], o.pts[k]);
            if (d < b2) { b2 = d; who = o; }
            if (b2 < 0.5) break;
          }
        });
        if (b2 < LINK_TOL) {
          best = b2;
          why = who.no ? '接 第' + who.no + '条线' : '接 箭头/图形';
        }
      }

      var rec = {
        line: ln.no, end: cur.end, d: ln.d,
        x: Math.round(p.x), y: Math.round(p.y),
        gap: Math.round(best * 10) / 10, why: why
      };
      if (best > RECT_TOL) bad.push(rec); else ok.push(rec);
    });
  });

  var out = document.createElement('pre');
  out.id = '__linklint';
  out.textContent = JSON.stringify({
    lines: no, solids: solids.length, bad: bad, ok: ok
  });
  document.body.appendChild(out);
})();
""".replace("%RECT_TOL%", str(RECT_TOL)).replace("%LINK_TOL%", str(LINK_TOL))


def run(src, verbose=False):
    if not os.path.isfile(src):
        print("[x] 找不到文件: %s" % src)
        return 2

    browser = find_browser()
    if not browser:
        print("[x] 没找到 Edge / Chrome / Chromium。可设置 SCENE_BROWSER。")
        return 1

    with open(src, "r", encoding="utf-8") as f:
        doc = f.read()

    if "</body>" not in doc:
        print("[x] HTML 里没有 </body>，无法注入检查脚本")
        return 2
    doc = doc.replace("</body>", "<script>%s</script>\n</body>" % JS, 1)

    work = ascii_tmpdir()
    probe = os.path.join(work, "probe.html")
    with open(probe, "w", encoding="utf-8") as f:
        f.write(doc)

    cmd = [
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--no-first-run", "--no-default-browser-check",
        "--force-device-scale-factor=1",
        "--window-size=1760,1120", "--virtual-time-budget=3000",
        "--dump-dom",
        "file:///" + probe.replace("\\", "/").lstrip("/"),
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=120)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work, ignore_errors=True)
        print("[x] 超时")
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)

    dom = r.stdout.decode("utf-8", "replace")
    m = re.search(r'<pre id="__linklint">(.*?)</pre>', dom, re.S)
    if not m:
        print("[x] 页面里没有拿到检查结果（注入脚本可能报错）。")
        return 2

    data = json.loads(html_mod.unescape(m.group(1)))
    name = os.path.basename(src)
    print("linklint: %s  —  %d 条线，%d 个实体"
          % (name, data["lines"], data["solids"]))

    if verbose:
        for o in data["ok"]:
            print("    ok   第%d条 %s (%d,%d)  %s  间距 %.1f"
                  % (o["line"], o["end"], o["x"], o["y"], o["why"], o["gap"]))

    if not data["bad"]:
        print("    所有端点都接上了")
        return 0

    print("    [x] 发现 %d 个悬空端点：" % len(data["bad"]))
    for b in data["bad"]:
        print('        第%d条线 %s 在 (%d,%d)，最近的物体还差 %.0fpx  d="%s"'
              % (b["line"], b["end"], b["x"], b["y"], b["gap"], b["d"]))
    print("    → 连线端点必须贴在卡片边缘，或与另一条线的端点/交点重合。")
    return 1


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 2
    return run(args[0], verbose=("-v" in sys.argv or "--verbose" in sys.argv))


if __name__ == "__main__":
    sys.exit(main())
