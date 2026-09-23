#!/usr/bin/env bash
# oc-simple 维护者发布脚本
#
# 用法:
#   ./release.sh                 # 默认 patch 版本号自增 (0.1.0 -> 0.1.1)
#   ./release.sh minor           # minor 自增 (0.1.0 -> 0.2.0)
#   ./release.sh major           # major 自增 (0.1.0 -> 1.0.0)
#   ./release.sh 0.3.0           # 指定版本号
#   ./release.sh -n              # 演练: 只跑检查/测试, 不改版本、不提交、不打标签
#   ./release.sh 0.3.0 --publish # 打包后用 gh CLI 创建 GitHub Release 并推送
#
# 流程: 前置检查 -> 跑测试 -> 更新 ocs.py __version__ -> git 提交 -> 打 tag
#       -> git archive 生成 dist/ 下的 tar.gz + zip 与 sha256 -> (--publish) 推送并建 Release
#
# 首次在未初始化 git 的目录运行时, 会自动 `git init` 并做一次初始提交。
set -euo pipefail

cd "$(dirname "$0")"

PUBLISH=0
DRY_RUN=0
BUMP="patch"
for arg in "$@"; do
  case "$arg" in
    -n|--dry-run) DRY_RUN=1 ;;
    --publish)    PUBLISH=1 ;;
    -h|--help)    sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    patch|minor|major) BUMP="$arg" ;;
    [0-9]*.[0-9]*.[0-9]*) BUMP="$arg" ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m 警告:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m错误:\033[0m %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1     || die "未找到 git"
command -v python3 >/dev/null 2>&1 || die "未找到 python3"

current_version() {
  python3 -c 'import re,sys; m=re.search(r"^__version__ = \"([^\"]+)\"", open("ocs.py").read(), re.M); print(m.group(1) if m else "")'
}

CUR_VER="$(current_version)"
[ -n "$CUR_VER" ] || die "无法从 ocs.py 解析 __version__"

if [ "$BUMP" = "$(printf '%s' "$BUMP" | tr -cd '0-9.')" ] && [ "$(printf '%s' "$BUMP" | tr -cd '.' | wc -c | tr -d ' ')" = "2" ]; then
  NEW_VER="$BUMP"
else
  NEW_VER="$(python3 -c '
import sys
ver, part = sys.argv[1], sys.argv[2]
a, b, c = (int(x) for x in ver.split("."))
print({"patch": f"{a}.{b}.{c+1}", "minor": f"{a}.{b+1}.0", "major": f"{a+1}.0.0"}[part])
' "$CUR_VER" "$BUMP")"
fi
say "版本: $CUR_VER -> $NEW_VER"

# ---- 前置检查 ------------------------------------------------------------

if [ ! -d .git ]; then
  if [ "$DRY_RUN" = 1 ]; then
    say "(演练) 将执行 git init + 初始提交"
  else
    say "未初始化 git, 执行 git init + 初始提交"
    git init -b main >/dev/null
    git add -A
    git commit -qm "chore: initial import"
  fi
fi

git config user.name  >/dev/null 2>&1 || die "git user.name 未配置 (git config --global user.name ...)"
git config user.email >/dev/null 2>&1 || die "git user.email 未配置"

if git rev-parse -q --verify "refs/tags/v$NEW_VER" >/dev/null; then
  die "标签 v$NEW_VER 已存在, 如需重发请先删除: git tag -d v$NEW_VER"
fi

# ---- 测试 ----------------------------------------------------------------

say "编译检查"
python3 -m py_compile ocs.py

say "单元测试 + TUI 冒烟测试"
python3 tests/test_units.py
python3 tests/test_tui_smoke.py

if [ "$DRY_RUN" = 1 ]; then
  say "演练结束 (未写入任何变更), 将发布 v$NEW_VER"
  exit 0
fi

# ---- 版本号写入 ------------------------------------------------------------

say "写入版本号 $NEW_VER 到 ocs.py"
python3 - "$CUR_VER" "$NEW_VER" <<'EOF'
import sys
old, new = sys.argv[1], sys.argv[2]
s = open("ocs.py").read()
assert '__version__ = "%s"' % old in s, "版本号不匹配"
open("ocs.py", "w").write(s.replace('__version__ = "%s"' % old, '__version__ = "%s"' % new, 1))
EOF

grep -q "^## \[v$NEW_VER\]" CHANGELOG.md || \
  warn "CHANGELOG.md 还没有 v$NEW_VER 的条目, 建议补充后再发布 (不阻塞)"

git add -A
git commit -qm "chore(release): v$NEW_VER"
git tag -a "v$NEW_VER" -m "oc-simple v$NEW_VER"

# ---- 打包 ------------------------------------------------------------------

say "生成发布包"
mkdir -p dist
rm -f "dist/oc-simple-$NEW_VER.tar.gz" "dist/oc-simple-$NEW_VER.zip" dist/sha256sums.txt
git archive --format=tar.gz --prefix="oc-simple-$NEW_VER/" -o "dist/oc-simple-$NEW_VER.tar.gz" "v$NEW_VER"
git archive --format=zip   --prefix="oc-simple-$NEW_VER/" -o "dist/oc-simple-$NEW_VER.zip"   "v$NEW_VER"
(cd dist && shasum -a 256 "oc-simple-$NEW_VER.tar.gz" "oc-simple-$NEW_VER.zip" > sha256sums.txt)
ls -lh dist/

# ---- 发布 ------------------------------------------------------------------

if [ "$PUBLISH" = 1 ]; then
  command -v gh >/dev/null 2>&1 || die "--publish 需要 gh CLI (https://cli.github.com), 或手动: git push origin main --follow-tags 后在 GitHub Releases 页面上传 dist/"
  say "推送到远端并创建 GitHub Release"
  git remote get-url origin >/dev/null 2>&1 || die "未配置 origin 远端 (git remote add origin git@github.com:<owner>/oc-simple.git)"
  git push origin HEAD --follow-tags
  NOTES="$(mktemp)"
  trap 'rm -f "$NOTES"' EXIT
  # 从 CHANGELOG 提取当前版本段落作为 Release Notes, 失败则用占位
  awk "/^## \[v$NEW_VER\]/{flag=1;next} /^## \[/{flag=0} flag" CHANGELOG.md > "$NOTES" || true
  [ -s "$NOTES" ] || echo "oc-simple v$NEW_VER" > "$NOTES"
  gh release create "v$NEW_VER" dist/oc-simple-$NEW_VER.tar.gz dist/oc-simple-$NEW_VER.zip \
    --title "v$NEW_VER" --notes-file "$NOTES"
  say "已发布: $(git remote get-url origin)/releases/tag/v$NEW_VER"
else
  say "打包完成。后续手动发布:"
  echo "    git push origin main --follow-tags"
  echo "    并在 GitHub Releases 上传 dist/ 下的文件 (或用 --publish 自动完成)"
fi
say "完成 🎉"
