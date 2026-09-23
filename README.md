<div align="center">

# oc-simple-starter

**OpenCode 简易启动器 —— 系统文件选择器新建会话，跨项目搜索并恢复历史会话**

[简体中文](README.md) | [English](README_EN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](pyproject.toml)
[![CI](https://github.com/huangchen/oc-simple-starter/actions/workflows/ci.yml/badge.svg)](https://github.com/huangchen/oc-simple-starter/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/huangchen/oc-simple-starter)](https://github.com/huangchen/oc-simple-starter/releases)

纯 Python 标准库实现，单文件，零第三方依赖。

</div>

## 为什么做这个

[OpenCode](https://opencode.ai) 是很棒的终端 AI 编程助手，但：

- 想在某个目录开新会话，得先 `cd` 过去再启动 —— 习惯了 GUI 文件选择器的话不够顺手；
- `opencode session list` **只能列出当前项目**的会话，想找"上周在另一个仓库聊的那个问题"
  只能去翻 SQLite。

`ocs` 把这两步变成两次回车：一个入口弹系统文件选择器选目录开工，另一个入口在**全部历史
会话**里直接打字搜索、回车恢复。

## 功能

- **新建 session** —— 调起系统文件选择器（macOS `osascript`，Linux `zenity`）选择工作
  目录后启动 `opencode`，并记住上次目录作为下次默认位置
- **搜索 / 恢复 session** —— 只读查询 OpenCode v2 本地数据库 `opencode.db`，跨项目列出
  全部顶层会话（按最近更新排序），输入即过滤（多关键词、命中标题/目录/id/模型），
  回车以 `opencode -s <id> <目录>` 恢复
- **非交互子命令** —— 方便脚本化：`list` / `new` / `resume`
- 中文按显示宽度对齐，不会错位；数据库 WAL 模式下边用 OpenCode 边查也安全

## 安装

```bash
# 方式一: 一键脚本 (macOS / Linux)
curl -fsSL https://raw.githubusercontent.com/huangchen/oc-simple-starter/main/install.sh | bash

# 方式二: 从源码
git clone https://github.com/huangchen/oc-simple-starter.git
cd oc-simple-starter && ./install.sh

# 方式三: pipx (依赖 pyproject.toml, 自动创建隔离环境)
pipx install git+https://github.com/huangchen/oc-simple-starter.git
```

要求：Python ≥ 3.8、已安装 [OpenCode v2](https://opencode.ai)（`opencode --version` ≥ 2.x）。
卸载：`./install.sh --uninstall`。

## 使用

```bash
ocs          # 交互界面
```

```
 OpenCode 启动器 (oc-simple-starter)
   ◆ 新建 session  — 选择工作目录开始
   ↺ 恢复 session  — 搜索并进入历史会话
 ↑↓/jk 选择  Enter 确认  Esc 退出   |   共 12 个 session
```

进入"恢复"后：

```
 恢复 session — 共 12 个 (跨项目, 按最近更新排序)
 2小时前  09-23 10:21  修复会话列表的分页逻辑        ~/code/webapp
 3天前    09-20 18:40  调研 SQLite WAL 并发读取        ~/code/dbdoc
 输入关键词过滤 (空格分隔多词, 命中标题/目录/id)  ↑↓/jk 选择  Enter 恢复  Esc 返回
 搜索: _
```

| 按键 | 作用 |
| --- | --- |
| `↑` `↓` / `k` `j` | 移动选择 |
| `PgUp` `PgDn` | 翻页 |
| 直接输入 | 实时过滤（空格分隔多关键词） |
| `Enter` | 确认 / 恢复选中会话 |
| `Esc` | 清空搜索词 → 返回上级 → 退出 |

### 非交互子命令

```bash
ocs list [关键词]      # 列出全部 session（可带搜索词）
ocs new [目录]         # 新建 session；省略目录则弹系统文件选择器
ocs resume <id前缀>    # 按 id（可只写前缀）恢复
ocs --version
```

## 工作原理

- 只以**只读模式**打开 `~/.local/share/opencode/opencode.db`（OpenCode v2 的会话库），
  合并 `session_v2` 与遗留 `session` 表并去重，排除子会话与已归档会话 —— 与 OpenCode
  自身的列表口径一致；不向 OpenCode 写入任何数据
- 唯一的本地状态是 `~/.config/oc-simple-starter/state.json`（记住上次工作目录）
- 启动即替换当前进程（`execvp`），退出 opencode 后终端干净如初

## 开发

```bash
python3 tests/test_units.py        # 单元测试（纯函数 + 数据读取 + 子命令）
python3 tests/test_tui_smoke.py    # TUI 冒烟测试（pty 驱动，自带数据夹具，CI 可跑）
./release.sh -n                    # 发布演练：跑测试、检查版本，不写任何变更
./release.sh minor                 # 发布：自增版本 → 提交打标签 → dist/ 打包 → 可选 --publish
```

测试不依赖本机真实会话数据；`OC_SIMPLE_DRY_RUN` / `OC_SIMPLE_FAKE_PICKER` 两个环境变量
用于自动化注入。

## 路线图

- [ ] `ocs delete`（封装 `opencode session delete`）
- [ ] zsh / bash 补全
- [ ] Homebrew formula

## 贡献

Issue 和 PR 都欢迎。提交 PR 前请跑一遍上面的测试；提交信息建议遵循
[Conventional Commits](https://www.conventionalcommits.org/zh-hans/)。

## 许可证

[MIT](LICENSE)
