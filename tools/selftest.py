#!/usr/bin/env python3
"""自测：在临时目录里模拟一次全新安装，检查结果。

不需要改动你自己的 Herdr 配置——它把官方面板复制到临时目录再装一遍。

  python3 tools/selftest.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
PANELS = ["spaces", "agents", "tabs", "pane", "files", "changes", "toast"]


def main() -> int:
    real_home = pathlib.Path.home() / ".config" / "herdr-app"
    if not (real_home / "mods").is_dir():
        print(f"找不到 {real_home}/mods", file=sys.stderr)
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        home = pathlib.Path(tmp) / "home"
        (home / "layouts").mkdir(parents=True)
        shutil.copytree(real_home / "mods", home / "mods",
                        ignore=shutil.ignore_patterns("zh-*", "__pycache__"))
        shutil.copy2(real_home / "layouts" / "main.json", home / "layouts")

        env = dict(os.environ, HERDR_APP_HOME=str(home))
        r = subprocess.run([sys.executable, str(HERE / "tools/install.py")],
                           capture_output=True, text=True, env=env)
        if r.returncode != 0:
            failures.append(f"安装器失败：\n{r.stdout}\n{r.stderr}")

        for name in PANELS:
            panel = home / "mods" / f"zh-{name}"
            if not (panel / "main.js").exists():
                failures.append(f"zh-{name} 没有生成")
                continue
            body = (panel / "main.js").read_text()
            if not re.search(r"[一-鿿]", body):
                failures.append(f"zh-{name} 里没有中文")

            # Must parse as an ES module.
            probe = pathlib.Path(tmp) / "probe.mjs"
            probe.write_text(body)
            node = shutil.which("node")
            if node:
                chk = subprocess.run([node, "--check", str(probe)],
                                     capture_output=True, text=True)
                if chk.returncode != 0:
                    failures.append(f"zh-{name} 语法错误：{chk.stderr[:300]}")
                probe.unlink()

            # Code structure must equal the official panel's.
            official = home / "mods" / name / "main.js"
            if official.exists():
                if skeleton(official.read_text()) != skeleton(body):
                    failures.append(f"zh-{name} 代码结构被改动")

        layout = home / "layouts" / "zh.json"
        if not layout.exists():
            failures.append("layouts/zh.json 没有生成")
        else:
            data = json.loads(layout.read_text())
            if data.get("terminal_menu") != "zh-menu":
                failures.append("zh.json 没有指向 zh-menu")
            if data.get("toast") != "zh-toast":
                failures.append("zh.json 没有指向 zh-toast")

    if failures:
        print(f"FAILED ({len(failures)})")
        for f in failures:
            print("  -", f)
        return 1

    print(f"ok: 安装器在临时目录复现了 {len(PANELS)} 个面板，"
          f"语法与代码结构均正确")
    return 0


STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')


def skeleton(text: str) -> str:
    """Code with every string literal blanked out."""
    return STRING.sub("·S·", text)


if __name__ == "__main__":
    sys.exit(main())
