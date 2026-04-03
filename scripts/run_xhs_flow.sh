#!/bin/bash
# 小红书 + 飞书一键运行脚本
# 用法：./scripts/run_xhs_flow.sh "主题" ["受众"]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

# 检查虚拟环境
if [ ! -f "$VENV_PYTHON" ]; then
  echo "❌ 虚拟环境未找到，正在创建..."
  python3 -m venv "$PROJECT_DIR/.venv"
  "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt" -q
  echo "✅ 虚拟环境已创建"
fi

# 参数
TOPIC="${1:-教培机构如何用 AI 节省内容运营时间}"
AUDIENCE="${2:-教育行业运营负责人}"

echo "🍠 小红书 + 飞书自动化流程"
echo "   主题: $TOPIC"
echo "   受众: $AUDIENCE"
echo ""

FLOW_ARGS=(
  --topic "$TOPIC"
  --audience "$AUDIENCE"
  --mode draft
)

if [ "${XHS_SKIP_IMAGE:-0}" = "1" ]; then
  echo "   生图: 占位图（XHS_SKIP_IMAGE=1）"
  FLOW_ARGS+=(--skip-image)
else
  echo "   生图: 真实封面图"
fi

"$VENV_PYTHON" "$SCRIPT_DIR/xhs_feishu_flow.py" "${FLOW_ARGS[@]}"
