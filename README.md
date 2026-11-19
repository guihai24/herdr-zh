# Herdr 汉化

把 [Herdr](https://herdr.dev) 的界面变成简体中文。

Herdr 的界面不是编译进程序的字符串，而是 `~/.config/herdr-app/mods/` 下一组
JavaScript 面板（用 [gpui-kit](https://gpui-kit.com) 描述原生 UI）。所以汉化
不必改二进制，只要**换掉这些面板里的显示文字**。

这个仓库只包含**译文对照表和工具**，不含任何 Herdr 源码——安装时从你本机
已装好的 Herdr 读取官方面板，复制成 `zh-*` 副本再套用译文。

```
官方 mods/spaces/main.js  ──克隆──▶  mods/zh-spaces/main.js（套用译文）
官方 layouts/main.json    ──复制──▶  layouts/zh.json（指向 zh-* 面板）
```

你的原 `main` 布局和官方文件完全不动，随时可以切回英文。

## 安装

需要 Herdr（0.1.x）和 Python 3.9+。

```sh
git clone <this-repo> herdr-zh
cd herdr-zh
python3 tools/install.py
```

然后切到中文布局：

```sh
herdr-app do layout.switch --name zh     # 中文
herdr-app do layout.switch --name main   # 英文
```

也可以用 `ctrl-shift-l` 在布局间循环。选择会被记住，重启后仍是中文。

安装器会：

- 逐个克隆 14 个官方面板到 `mods/zh-*`
- 按位置套用译文（只改字符串字面量，代码一字不动）
- 把面板之间的跳转改指到 `zh-*`（右键菜单、+ 菜单、搜索、工作树、添加机器）
- 生成 `layouts/zh.json`
- 每个面板写盘前用 `node --check` 按 ES module 校验语法，不通过就不写

选项：

```sh
python3 tools/install.py --dry-run          # 只报告，不改文件
python3 tools/install.py --only spaces,tabs # 只装几个面板
python3 tools/install.py --uninstall        # 移除汉化
```

Herdr 配置不在默认位置时，用 `HERDR_APP_HOME` 指定：

```sh
HERDR_APP_HOME=/path/to/config python3 tools/install.py
```

## 设置窗口（可选）

设置窗口在 `frame/settings/main.js`，是 Herdr 自己的文件，**每次启动都会被
重写回英文**。它支持热加载，所以用一个小守护在启动后重新打补丁：

```sh
python3 tools/patch_settings.py          # 打一次
python3 tools/patch_settings.py --watch  # 常驻，发现被还原就重打
```

想开机自动生效，加一个 launchd 服务（macOS）：

```sh
cat > ~/Library/LaunchAgents/dev.herdr.zh-settings.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>dev.herdr.zh-settings</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>$PWD/tools/patch_settings.py</string>
    <string>--watch</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
EOF
launchctl load ~/Library/LaunchAgents/dev.herdr.zh-settings.plist
```

这一步是可选的，而且是整个方案里最“不受支持”的部分：它在和 Herdr 抢文件。
不想折腾的话跳过，主界面的汉化不受影响。

## 没汉化的部分

| 位置 | 原因 |
|---|---|
| 命令面板（⌘P） | `frame/palette`，启动时重写；可以用同样的补丁思路处理，但改动面大，暂未做 |
| 欢迎页 / What's new / 反馈窗 | 同上，在 `frame/` 下 |
| 快捷键列表（`app.help`） | 官方 `mods/help`，只读；删掉后应用会沿用上次加载的版本，无法用自建版替代 |
| 确认框、新建标签页输入框 | 官方 `mods/confirm`、`mods/prompt`，只读 |
| macOS 系统菜单栏 | `Herdr.app` 的 Info.plist 已签名，改不了 |

## 升级 Herdr 之后

Herdr 更新会替换官方 mod，而 `zh-*` 是你自己的文件、不会被更新——可能落后。
升级后重跑安装器即可重新生成：

```sh
python3 tools/install.py
```

如果某个面板报「位置对不上」，说明官方改了结构，去
`translations/mods.json` 里更新对应的 `i`（字符偏移）和 `old`。看看哪个面板
变了：

```sh
diff ~/.config/herdr-app/mods/tabs/main.js ~/.config/herdr-app/mods/zh-tabs/main.js
```

每次改完都要校验：

```sh
for d in ~/.config/herdr-app/mods/zh-*/; do herdr-app check "$d"; done
```

## 参与翻译

译文在 `translations/`：

- `mods.json` — 每个面板一组按位置的补丁 `{i, old, new, len, quote}`
  （`i` 是官方文件里该字面量的字符偏移）
- `settings.json` — 设置窗口的 `{old, new}` 对照

改译文只需改 `new` 字段，然后重装：

```sh
python3 tools/install.py && python3 tools/patch_settings.py
```

**不要改 `i`**，除非官方文件也变了。补丁按位置而非纯文本匹配，是因为同一个
词在不同位置含义不同——`"worktree"` 既可能是菜单文字，也可能是命令名。

## 关于授权

Herdr 以 Apache-2.0 发布，允许修改与再分发。本仓库分发的是译文对照表和工具，
不含 Herdr 的源代码副本；汉化结果是 `zh-*` 面板，由你本机的 Herdr 文件与译文
组合生成。Herdr 及其界面原作者的著作权归其所有。

本仓库的工具与译文以 MIT 发布，见 [LICENSE](LICENSE)。
