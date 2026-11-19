#!/usr/bin/env python3
"""汉化 Herdr 的设置窗口。

设置窗口在 ~/.config/herdr-app/frame/settings/main.js。它是 Herdr 自己的文件，
**每次启动都会被重写回英文**。它支持热加载，所以做法是启动后重新打补丁：

  python3 patch_settings.py          # 打一次补丁
  python3 patch_settings.py --watch  # 常驻，发现被还原就重打

配合 launchd（见 README）可以在每次登录后自动生效。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
TRANSLATIONS = HERE / "translations" / "settings.json"

# Present only after patching: the window title.
MARKER = 'child("设置")'


def app_home() -> pathlib.Path:
    env = os.environ.get("HERDR_APP_HOME")
    return pathlib.Path(env).expanduser() if env else pathlib.Path.home() / ".config" / "herdr-app"


def target() -> pathlib.Path:
    return app_home() / "frame" / "settings" / "main.js"


def parses(path: pathlib.Path) -> tuple[bool, str]:
    """Validate as an ES module (a .js path is checked as CommonJS and would
    silently pass, so probe with a .mjs copy)."""
    node = shutil.which("node")
    if not node:
        return False, "找不到 node，拒绝写入未经验证的文件"
    probe = path.with_name(path.stem + ".__probe.mjs")
    try:
        shutil.copyfile(path, probe)
        r = subprocess.run([node, "--check", str(probe)], capture_output=True, text=True)
    finally:
        probe.unlink(missing_ok=True)
    return r.returncode == 0, (r.stderr or "").strip()[:500]


def apply_copy(text: str, pairs: list[dict]) -> tuple[str, int, list[str]]:
    applied, problems = 0, []
    for e in pairs:
        old, new = e["old"], e["new"]
        if '"' in new or new.endswith("\\"):
            problems.append(f"译文含引号或反斜杠，跳过：{new[:40]!r}")
            continue
        lit = old if old.startswith("`") else f'"{old}"'
        want = new if new.startswith("`") else f'"{new}"'
        n = text.count(lit)
        if n == 0:
            problems.append(f"找不到（Herdr 改过文案？）：{old[:50]!r}")
            continue
        text = text.replace(lit, want)
        applied += 1
    return text, applied, problems


def patch_once(quiet: bool = False) -> int:
    path = target()
    if not path.exists():
        if not quiet:
            print(f"找不到 {path} —— Herdr 启动过吗？", file=sys.stderr)
        return 1

    text = path.read_text()
    if MARKER in text:
        if not quiet:
            print("已经是中文，无需处理")
        return 0

    pairs = json.loads(TRANSLATIONS.read_text())
    new_text, applied, problems = apply_copy(text, pairs)
    if applied == 0:
        print(f"0/{len(pairs)} 条译文命中：Herdr 的文案变了", file=sys.stderr)
        for p in problems:
            print("  !", p, file=sys.stderr)
        return 1

    # Atomic write: Herdr may rewrite this file at any moment, and a
    # half-written file would leave the Settings window unrenderable.
    tmp = path.with_name(f".{path.stem}.zh-{os.getpid()}.js")
    try:
        tmp.write_text(new_text)
        ok, err = parses(tmp)
        if not ok:
            print("补丁后语法错误，保留 Herdr 的原文：", file=sys.stderr)
            print(err, file=sys.stderr)
            return 1
        os.chmod(tmp, path.stat().st_mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

    if not quiet:
        print(f"已汉化 {applied}/{len(pairs)} 条")
        for p in problems:
            print("  !", p)
    return 0


def watch(interval: float) -> None:
    print(f"监视 {target()}，每 {interval:g} 秒检查一次（Ctrl+C 结束）")
    while True:
        try:
            patch_once(quiet=True)
        except Exception as exc:                 # keep the watcher alive
            print(f"出错：{exc}", file=sys.stderr)
        time.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description="汉化 Herdr 设置窗口")
    ap.add_argument("--watch", action="store_true", help="常驻监视，被还原就重打")
    ap.add_argument("--interval", type=float, default=5.0, help="监视间隔秒数")
    args = ap.parse_args()

    if not TRANSLATIONS.exists():
        print(f"找不到 {TRANSLATIONS}", file=sys.stderr)
        return 1
    if args.watch:
        try:
            watch(args.interval)
        except KeyboardInterrupt:
            print("\n已停止")
        return 0
    return patch_once()


if __name__ == "__main__":
    sys.exit(main())
