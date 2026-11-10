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
    echo "  all       查看后端和前端服务状态（默认）"
    echo "  backend   仅查看后端服务状态"
    echo "  frontend  仅查看前端服务状态"
    exit 1
}

case "${TARGET}" in
    all|backend|frontend)
        ;;
    *)
        usage
        ;;
esac

check_status() {
    local name="$1"
    local pid_file="$2"
    local port="$3"
    local local_url="$4"
    local log_file="$5"

    local pid
    pid="$(get_service_pid "${pid_file}" || true)"

    echo "---------------------------------------"
    echo "服务名称: ${name}"
    if [ -n "${pid}" ]; then
        echo -e "运行状态: ${COLOR_GREEN}RUNNING${COLOR_RESET}"
        echo "进程 PID: ${pid}"
        echo "监听地址: ${BIND_HOST}:${port}"
        echo "本地访问: ${local_url}"
        local all_ips=($(get_all_lan_ips || true))
        if [ ${#all_ips[@]} -gt 0 ]; then
            for ip in "${all_ips[@]}"; do
                echo -e "局域网访问: ${COLOR_GREEN}http://${ip}:${port}${COLOR_RESET}"
            done
        else
            echo "局域网访问: 未检测到局域网 IP"
        fi
        echo "日志路径: ${log_file}"
    else
        echo -e "运行状态: ${COLOR_YELLOW}STOPPED${COLOR_RESET}"
        if [ -f "${pid_file}" ]; then
            echo -e "异常提示: ${COLOR_RED}PID 文件存在但进程未存活 (已清理)${COLOR_RESET}"
            rm -f "${pid_file}"
        fi
        echo "配置端口: ${port}"
        echo "日志路径: ${log_file}"
    fi
}

echo -e "${COLOR_BOLD}=== zhenAgent 服务运行状态 ===${COLOR_RESET}"

if [ "${TARGET}" = "backend" ] || [ "${TARGET}" = "all" ]; then
    check_status "后端服务 (FastAPI)" "${BACKEND_PID_FILE}" "${BACKEND_PORT}" "${BACKEND_LOCAL_URL}" "${BACKEND_LOG_FILE}"
fi

if [ "${TARGET}" = "frontend" ] || [ "${TARGET}" = "all" ]; then
    check_status "前端服务 (Vite/React)" "${FRONTEND_PID_FILE}" "${FRONTEND_PORT}" "${FRONTEND_LOCAL_URL}" "${FRONTEND_LOG_FILE}"
fi

echo "---------------------------------------"
