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
    echo "  all       启动后端和前端服务（默认）"
    echo "  backend   仅启动后端服务"
    echo "  frontend  仅启动前端服务"
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
check_env_file

if ! check_dependencies "${TARGET}"; then
    exit 1
fi

start_backend() {
    log_info "正在启动后端服务 (绑定 ${BIND_HOST}:${BACKEND_PORT})..."
    local existing_pid
    existing_pid="$(get_service_pid "${BACKEND_PID_FILE}" || true)"
    if [ -n "${existing_pid}" ]; then
        log_warn "后端服务已在运行 (PID: ${existing_pid})"
        return 0
    fi

    # 清除旧的重定向文件并追加启动日志记录
    echo -e "\n=== 启动于 $(date '+%Y-%m-%d %H:%M:%S') ===" >> "${BACKEND_LOG_FILE}"
    echo "监听地址: ${BIND_HOST}:${BACKEND_PORT}" >> "${BACKEND_LOG_FILE}"
    echo "本地访问: ${BACKEND_LOCAL_URL}" >> "${BACKEND_LOG_FILE}"
    if [ -n "${BACKEND_LAN_URL}" ]; then
        echo "局域网访问: ${BACKEND_LAN_URL}" >> "${BACKEND_LOG_FILE}"
    else
        echo "局域网访问: 未检测到有效局域网 IP" >> "${BACKEND_LOG_FILE}"
    fi

    nohup uv run --project "${PROJECT_ROOT}/backend" --locked uvicorn zhenagent.api:app --host "${BIND_HOST}" --port "${BACKEND_PORT}" >> "${BACKEND_LOG_FILE}" 2>&1 &
    local new_pid=$!
    echo "${new_pid}" > "${BACKEND_PID_FILE}"
    log_info "后端服务已启动 (PID: ${new_pid})，日志记录至 ${BACKEND_LOG_FILE}"

    if ! wait_for_service_ready "后端服务" "${new_pid}" "${BACKEND_CHECK_URL}" "${BACKEND_LOG_FILE}" 15; then
        return 1
    fi
    return 0
}

start_frontend() {
    log_info "正在启动前端服务 (绑定 ${BIND_HOST}:${FRONTEND_PORT})..."
    local existing_pid
    existing_pid="$(get_service_pid "${FRONTEND_PID_FILE}" || true)"
    if [ -n "${existing_pid}" ]; then
        log_warn "前端服务已在运行 (PID: ${existing_pid})"
        return 0
    fi

    if [ ! -d "${PROJECT_ROOT}/frontend/node_modules" ]; then
        log_warn "未检测到 frontend/node_modules，首次运行建议先执行: pnpm --dir frontend install --frozen-lockfile"
    fi

    # 追加启动日志记录
    echo -e "\n=== 启动于 $(date '+%Y-%m-%d %H:%M:%S') ===" >> "${FRONTEND_LOG_FILE}"
    echo "监听地址: ${BIND_HOST}:${FRONTEND_PORT}" >> "${FRONTEND_LOG_FILE}"
    echo "本地访问: ${FRONTEND_LOCAL_URL}" >> "${FRONTEND_LOG_FILE}"
    if [ -n "${FRONTEND_LAN_URL}" ]; then
        echo "局域网访问: ${FRONTEND_LAN_URL}" >> "${FRONTEND_LOG_FILE}"
    else
        echo "局域网访问: 未检测到有效局域网 IP" >> "${FRONTEND_LOG_FILE}"
    fi

    nohup pnpm --dir "${PROJECT_ROOT}/frontend" dev --host "${BIND_HOST}" >> "${FRONTEND_LOG_FILE}" 2>&1 &
    local new_pid=$!
    echo "${new_pid}" > "${FRONTEND_PID_FILE}"
    log_info "前端服务已启动 (PID: ${new_pid})，日志记录至 ${FRONTEND_LOG_FILE}"

    if ! wait_for_service_ready "前端服务" "${new_pid}" "${FRONTEND_CHECK_URL}" "${FRONTEND_LOG_FILE}" 15; then
        return 1
    fi
    return 0
}

has_failed=0

if [ "${TARGET}" = "backend" ] || [ "${TARGET}" = "all" ]; then
    if ! start_backend; then
        has_failed=1
    fi
fi

if [ "${TARGET}" = "frontend" ] || [ "${TARGET}" = "all" ]; then
    if ! start_frontend; then
        has_failed=1
    fi
fi

if [ "${has_failed}" -ne 0 ]; then
    log_error "服务启动遇到异常，请查看上方日志或检查 .local/logs/"
    exit 1
fi

echo ""
echo -e "${COLOR_BOLD}${COLOR_GREEN}=======================================${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}          zhenAgent 服务已就绪          ${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}=======================================${COLOR_RESET}"
echo -e "监听绑定:   ${COLOR_BOLD}${BIND_HOST} (本地与局域网均可访问)${COLOR_RESET}"

ALL_LAN_IPS=($(get_all_lan_ips || true))

if [ "${TARGET}" = "all" ] || [ "${TARGET}" = "frontend" ]; then
    echo -e "\n${COLOR_BOLD}前端控制台:${COLOR_RESET}"
    echo -e "  - 本地访问: ${COLOR_CYAN}${FRONTEND_LOCAL_URL}${COLOR_RESET}"
    if [ ${#ALL_LAN_IPS[@]} -gt 0 ]; then
        for lan_ip in "${ALL_LAN_IPS[@]}"; do
            echo -e "  - 局域网访问: ${COLOR_GREEN}http://${lan_ip}:${FRONTEND_PORT}${COLOR_RESET}"
        done
    else
        echo -e "  - 局域网访问: ${COLOR_YELLOW}未检测到局域网 IP${COLOR_RESET}"
    fi
fi

if [ "${TARGET}" = "all" ] || [ "${TARGET}" = "backend" ]; then
    echo -e "\n${COLOR_BOLD}后端接口:${COLOR_RESET}"
    echo -e "  - 本地访问: ${COLOR_CYAN}${BACKEND_LOCAL_URL}${COLOR_RESET}"
    if [ ${#ALL_LAN_IPS[@]} -gt 0 ]; then
        for lan_ip in "${ALL_LAN_IPS[@]}"; do
            echo -e "  - 局域网访问: ${COLOR_GREEN}http://${lan_ip}:${BACKEND_PORT}${COLOR_RESET}"
        done
    else
        echo -e "  - 局域网访问: ${COLOR_YELLOW}未检测到局域网 IP${COLOR_RESET}"
    fi
fi

echo ""
echo -e "日志目录:   ${COLOR_CYAN}${LOG_DIR}${COLOR_RESET}"
echo -e "停止服务:   ${COLOR_YELLOW}./stop.sh${COLOR_RESET}"
echo -e "重启服务:   ${COLOR_YELLOW}./restart.sh${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_GREEN}=======================================${COLOR_RESET}"
