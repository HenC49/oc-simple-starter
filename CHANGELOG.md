# Changelog

本项目的全部重要变更记录于此文件。
格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-09-23

首个开源版本。

### Added

- 交互式启动器：新建 session（调起系统文件选择器选工作目录，记住上次目录）/
  恢复 session 两个入口。
- 跨项目 session 浏览器：只读查询 OpenCode v2 的 `opencode.db`，按最近更新排序，
  支持多关键词实时过滤（命中标题/目录/id/模型），选中后以
  `opencode -s <id> <目录>` 恢复。
- 非交互子命令：`ocs list [关键词]`、`ocs new [目录]`、`ocs resume <id前缀>`。
- 测试：单元测试 + 基于 pty 的 TUI 冒烟测试（自带会话数据夹具，不依赖真实数据）。
- 发布流水线：`release.sh`（版本号自增 / 打标签 / git archive 打包 / 校验和 /
  可选 gh release 发布）、`install.sh` 用户安装脚本。
- CI：GitHub Actions，Python 3.9–3.13 矩阵跑测试。

[Unreleased]: https://github.com/HenC49/oc-simple-starter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/HenC49/oc-simple-starter/releases/tag/v0.1.0
