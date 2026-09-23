#!/usr/bin/env bash
# oc-simple 用户安装脚本
#
# 用法:
#   从仓库根目录安装:   ./install.sh
#   远程一键安装:       curl -fsSL https://raw.githubusercontent.com/huangchen/oc-simple/main/install.sh | bash
#   自定义前缀:         PREFIX=~/.local ./install.sh
#   卸载:               ./install.sh --uninstall
set -euo pipefail

# TODO: 项目迁移后改成实际 owner/仓库名
REPO_RAW="https://raw.githubusercontent.com/huangchen/oc-simple/main"
PREFIX="${PREFIX:-$HOME/.local}"
LIB_DIR="$PREFIX/share/oc-simple"
BIN_DIR="$PREFIX/bin"
MODE="install"

for arg in "$@"; do
  case "$arg" in
    --uninstall) MODE="uninstall" ;;
    -h|--help)
      sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数: $arg (支持 --uninstall / --help)" >&2; exit 2 ;;
  esac
done

uninstall() {
  rm -f "$BIN_DIR/ocs" "$LIB_DIR/ocs.py"
  rmdir "$LIB_DIR" 2>/dev/null || true
  echo "已卸载: $BIN_DIR/ocs 与 $LIB_DIR/"
}

if [ "$MODE" = "uninstall" ]; then
  uninstall
  exit 0
fi

command -v python3 >/dev/null 2>&1 || { echo "错误: 未找到 python3 (需要 Python 3.8+)" >&2; exit 1; }

SRC="ocs.py"
if [ ! -f "$SRC" ]; then
  # curl|bash 远程安装: 先把脚本下载到临时目录
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  echo "从 $REPO_RAW/ocs.py 下载..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$REPO_RAW/ocs.py" -o "$TMP/ocs.py"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP/ocs.py" "$REPO_RAW/ocs.py"
  else
    echo "错误: 需要 curl 或 wget 之一" >&2
    exit 1
  fi
  SRC="$TMP/ocs.py"
fi

mkdir -p "$LIB_DIR" "$BIN_DIR"
install -m 644 "$SRC" "$LIB_DIR/ocs.py"
cat > "$BIN_DIR/ocs" <<EOF
#!/bin/sh
exec python3 "$LIB_DIR/ocs.py" "\$@"
EOF
chmod +x "$BIN_DIR/ocs"

VER="$(python3 "$LIB_DIR/ocs.py" --version)"
echo "已安装: $VER"
echo "  程序:  $LIB_DIR/ocs.py"
echo "  命令:  $BIN_DIR/ocs"

command -v opencode >/dev/null 2>&1 || \
  echo "提示: 未检测到 opencode 命令, 请先安装 OpenCode v2: https://opencode.ai"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "注意: $BIN_DIR 不在 PATH 中, 请在 shell 配置里添加: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac
echo "运行 'ocs' 开始使用。"
