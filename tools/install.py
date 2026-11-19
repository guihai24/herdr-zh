#!/usr/bin/env python3
"""Herdr 界面汉化安装器。

Herdr 的界面由 ~/.config/herdr-app/mods/*/main.js 里的面板拼成。这里的做法是：
从你本机**已安装**的 Herdr 读取官方面板 → 复制成 zh-* 副本 → 套用译文。
仓库里不含任何 Herdr 源码，只含译文对照表和工具。

用法：
  python3 install.py              # 安装/更新全部汉化
  python3 install.py --dry-run    # 只报告会做什么
  python3 install.py --only spaces,tabs
  python3 install.py --uninstall  # 移除 zh-* 面板和 zh 布局
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent   # repo root
TRANSLATIONS = HERE / "translations"

# Panels we translate. Each official mods/<name>/ gets cloned to mods/zh-<name>/.
PANELS = [
    "spaces", "agents", "tabs", "pane", "workspace-chrome", "workspace-status",
    "files", "changes", "worktree", "machine-add", "new-menu", "picker",
    "menu", "toast",
]

# Inside a clone, references to sibling panels must point at the zh copy,
# otherwise clicking through the Chinese UI drops you back into English.
# Ordered: the run("mod.open", {name}) form first, then the plain ones.
REWIRE = [
    ('name: "machine-add" }', 'name: "zh-machine-add" }'),
    ('name: "picker" }', 'name: "zh-picker" }'),
    ('mod: "agents"', 'mod: "zh-agents"'),
    ('mod: "machine-add"', 'mod: "zh-machine-add"'),
    ('mod: "menu"', 'mod: "zh-menu"'),
    ('mod: "new-menu"', 'mod: "zh-new-menu"'),
    ('mod: "worktree"', 'mod: "zh-worktree"'),
    ('mods/pane/', 'mods/zh-pane/'),
    ('mods/tabs/', 'mods/zh-tabs/'),
]

LAYOUT_MOD_SUFFIX = ""   # set in main() from CLI


def app_home() -> pathlib.Path:
    """Where Herdr keeps its config. HERDR_APP_HOME overrides it."""
    env = os.environ.get("HERDR_APP_HOME")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path.home() / ".config" / "herdr-app"


def find_official_mods() -> pathlib.Path | None:
    """The mods folder Herdr ships its own panels in."""
    home = app_home()
    if (home / "mods").is_dir():
        return home / "mods"
    return None


def load_json(path: pathlib.Path):
    return json.loads(path.read_text())


def is_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def apply_copy(text: str, pairs: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Replace each original string literal with its translation.

    A label can legitimately appear more than once (the same word in two
    menus), so every occurrence is replaced. The literal is matched in every
    quoting style — "…", `…`, and '…' — because template strings carry copy
    too ("Agents on ${m.name} …"), and a word that only appears inside a
    command name or as a substring is left alone.
    """
    problems = []
    for old, new in pairs:
        replaced = False
        for q in ('"', "`", "'"):
            lit, target = f"{q}{old}{q}", f"{q}{new}{q}"
            if lit in text:
                text = text.replace(lit, target)
                replaced = True
        if not replaced:
            problems.append(f"not found: {old[:60]!r}")
    return text, problems


def parses(path: pathlib.Path) -> tuple[bool, str]:
    """Validate as an ES module.

    Herdr mods use `import`; `node --check` on a .js path treats it as
    CommonJS and silently passes, so check a .mjs copy instead.
    """
    node = shutil.which("node")
    if not node:
        return True, "node 不存在，跳过语法检查"
    probe = path.with_name(path.stem + ".__probe.mjs")
    try:
        shutil.copyfile(path, probe)
        r = shutil.which("sh") and __import__("subprocess").run(
            [node, "--check", str(probe)], capture_output=True, text=True)
    finally:
        probe.unlink(missing_ok=True)
    return r.returncode == 0, (r.stderr or "").strip()[:500]


def apply_patches(text: str, entry: dict) -> tuple[str, list[str]]:
    """Apply positional literal patches, then structural rewrites.

    Positional, not textual: the same word can be a label in one place and a
    command name in another ("worktree"), and only its position tells them
    apart. Patches are applied from the end backwards so earlier offsets stay
    valid while the text shifts.
    """
    problems = []

    # Rewrites first: they target fragments of the official text, which the
    # positional patches below may already have replaced.
    for r in entry.get("rewrites", []):
        n = text.count(r["old"])
        if not n:
            problems.append(f"结构改写找不到：{r['old'][:40]!r}")
            continue
        # `all: true` marks a fragment that appears in more than one place and
        # means the same thing each time (e.g. the " of <repo>" tail).
        if n > 1 and not r.get("all"):
            problems.append(f"结构改写不唯一：{r['old'][:40]!r}")
            continue
        text = text.replace(r["old"], r["new"])

    patches = sorted(entry.get("patches", []), key=lambda p: p["i"], reverse=True)
    for p in patches:
        start, length = p["i"], p["len"]
        found = text[start:start + length]
        expect = f'{p["quote"]}{p["old"]}{p["quote"]}'
        if found != expect:
            problems.append(f"位置对不上（Herdr 升级了？）：{p['old'][:50]!r}")
            continue
        text = text[:start] + f'{p["quote"]}{p["new"]}{p["quote"]}' + text[start + length:]

    for r in entry.get("rewrites", []):
        n = text.count(r["old"])
        if not n:
            problems.append(f"结构改写找不到：{r['old'][:40]!r}")
            continue
        # `all: true` marks a fragment that appears in more than one place and
        # means the same thing each time (e.g. the " of <repo>" tail).
        if n > 1 and not r.get("all"):
            problems.append(f"结构改写不唯一：{r['old'][:40]!r}")
            continue
        text = text.replace(r["old"], r["new"])

    return text, problems


def install_panel(name: str, mods: pathlib.Path, entry: dict,
                  dry: bool) -> tuple[bool, list[str]]:
    """Clone mods/<name> to mods/zh-<name> and apply the translation to it."""
    official = mods / name
    source = official / "main.js"
    if not source.exists():
        return False, [f"官方面板 {name} 不存在（Herdr 版本不同？）"]

    text = source.read_text()
    text, problems = apply_patches(text, entry)
    if not is_cjk(text):
        return False, problems + ["译文没有生效"]

    dest_dir = mods / f"zh-{name}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy the whole mod folder (icons, mod.json), then overwrite main.js.
    for item in official.iterdir():
        if item.name == "main.js":
            continue
        target = dest_dir / item.name
        if item.is_dir():
            if not dry:
                shutil.copytree(item, target, dirs_exist_ok=True)
        elif not dry:
            shutil.copy2(item, target)

    # mod.json's title is display copy; translate it and nothing else.
    mod_json = dest_dir / "mod.json"
    if not dry and mod_json.exists():
        try:
            meta = load_json(mod_json)
            title = meta.get("title")
            zh_title = entry.get("title")
            if title and zh_title:
                meta["title"] = zh_title
                mod_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        except json.JSONDecodeError:
            problems.append("mod.json 解析失败，保持原样")

    tmp = dest_dir / "main.js.new"
    if not dry:
        tmp.write_text(text)
        ok, err = parses(tmp)
        if not ok:
            tmp.unlink(missing_ok=True)
            return False, problems + ["生成的代码语法错误，已放弃写入", err]
        os.replace(tmp, dest_dir / "main.js")

    return True, problems


def install_layout(dry: bool) -> tuple[bool, list[str]]:
    """Create layouts/zh.json from the official main layout, pointing at zh-* mods."""
    home = app_home()
    source = home / "layouts" / "main.json"
    if not source.exists():
        return False, ["找不到 layouts/main.json"]

    data = load_json(source)

    def walk(node):
        content = node.get("content") or {}
        mod = content.get("mod")
        if mod and mod in PANELS:
            content["mod"] = f"zh-{mod}"
        pane = node.get("pane") or {}
        header_mod = (pane.get("header") or {}).get("content", {}).get("mod")
        if header_mod in PANELS:
            pane["header"]["content"]["mod"] = f"zh-{header_mod}"
        for child in node.get("children") or []:
            walk(child)

    walk(data)
    data["toast"] = "zh-toast"
    data["terminal_menu"] = "zh-menu"

    dest = home / "layouts" / "zh.json"
    if not dry:
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return True, []


def uninstall(dry: bool) -> None:
    mods = find_official_mods()
    if mods:
        for name in PANELS:
            target = mods / f"zh-{name}"
            if target.exists():
                print(f"  移除 {target}")
                if not dry:
                    shutil.rmtree(target)
    layout = app_home() / "layouts" / "zh.json"
    if layout.exists():
        print(f"  移除 {layout}")
        if not dry:
            layout.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="汉化 Herdr 界面")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不改动")
    ap.add_argument("--only", help="只处理这些面板，逗号分隔")
    ap.add_argument("--uninstall", action="store_true", help="移除汉化")
    args = ap.parse_args()

    if not TRANSLATIONS.exists():
        print("找不到 translations/ 目录", file=sys.stderr)
        return 1

    if args.uninstall:
        uninstall(args.dry_run)
        print("完成。切回英文：herdr-app do layout.switch --name main")
        return 0

    official = find_official_mods()
    if not official:
        print(f"找不到 {app_home()}/mods —— Herdr 装好了吗？", file=sys.stderr)
        print("若配置不在默认位置，设置 HERDR_APP_HOME。", file=sys.stderr)
        return 1

    wanted = PANELS
    if args.only:
        wanted = [p.strip() for p in args.only.split(",") if p.strip()]
        unknown = [p for p in wanted if p not in PANELS]
        if unknown:
            print(f"未知面板：{', '.join(unknown)}", file=sys.stderr)
            return 1

    all_translations = load_json(TRANSLATIONS / "mods.json")

    failed = 0
    for name in wanted:
        entry = all_translations.get(name, {})
        if not entry.get("patches"):
            print(f"[跳过] {name}: 没有译文")
            continue
        ok, problems = install_panel(name, official, entry, args.dry_run)
        status = "ok  " if ok else "FAIL"
        print(f"[{status}] zh-{name}  ({len(entry['patches'])} 条译文)")
        for p in problems:
            print(f"        · {p}")
        if not ok:
            failed += 1

    ok, problems = install_layout(args.dry_run)
    print(f"[{'ok  ' if ok else 'FAIL'}] layouts/zh.json")
    for p in problems:
        print(f"        · {p}")

    print()
    if args.dry_run:
        print("（--dry-run：未写入任何文件）")
    else:
        print("完成。切到中文：herdr-app do layout.switch --name zh")
        print("切回英文：    herdr-app do layout.switch --name main")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
