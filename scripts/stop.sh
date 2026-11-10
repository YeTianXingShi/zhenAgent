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
    echo "  all       停止后端和前端服务（默认）"
    echo "  backend   仅停止后端服务"
    echo "  frontend  仅停止前端服务"
    exit 1
}

case "${TARGET}" in
    all|backend|frontend)
        ;;
    *)
        usage
        ;;
esac

ensure_runtime_dirs

has_failed=0

if [ "${TARGET}" = "backend" ] || [ "${TARGET}" = "all" ]; then
    if ! stop_service_process "后端服务" "${BACKEND_PID_FILE}"; then
        has_failed=1
    fi
fi

if [ "${TARGET}" = "frontend" ] || [ "${TARGET}" = "all" ]; then
    if ! stop_service_process "前端服务" "${FRONTEND_PID_FILE}"; then
        has_failed=1
    fi
fi

if [ "${has_failed}" -ne 0 ]; then
    log_error "部分服务停止失败，请手动检查相关进程"
    exit 1
fi

log_success "目标服务停止操作完成"
