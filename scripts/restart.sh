#!/usr/bin/env bash
set -e

# 加载公共配置与函数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "${SCRIPT_DIR}/common.sh"

TARGET="${1:-all}"

usage() {
    echo "用法: $0 [all|backend|frontend]"
    echo ""
    echo "参数说明:"
    echo "  all       重启后端和前端服务（默认）"
    echo "  backend   仅重启后端服务"
    echo "  frontend  仅重启前端服务"
    exit 1
}

case "${TARGET}" in
    all|backend|frontend)
        ;;
    *)
        usage
        ;;
esac

log_info "=== 正在执行停止流程 ==="
"${SCRIPT_DIR}/stop.sh" "${TARGET}"

# 等待端口与系统资源释放
sleep 1

log_info "=== 正在执行启动流程 ==="
"${SCRIPT_DIR}/start.sh" "${TARGET}"
