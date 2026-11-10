#!/usr/bin/env bash

# 解析项目根目录路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 运行时目录与文件
RUN_DIR="${PROJECT_ROOT}/.local/run"
LOG_DIR="${PROJECT_ROOT}/.local/logs"
BACKEND_PID_FILE="${RUN_DIR}/backend.pid"
FRONTEND_PID_FILE="${RUN_DIR}/frontend.pid"
BACKEND_LOG_FILE="${LOG_DIR}/backend.log"
FRONTEND_LOG_FILE="${LOG_DIR}/frontend.log"

# 获取当前设备在局域网中的 IPv4 地址
get_all_lan_ips() {
    local ips=()

    # 1. macOS 遍历物理网卡（如 en0, en1 等）
    if command -v ipconfig >/dev/null 2>&1 && command -v ifconfig >/dev/null 2>&1; then
        for iface in $(ifconfig -l 2>/dev/null); do
            if [[ "${iface}" =~ ^en[0-9]+$ ]]; then
                local ip
                ip="$(ipconfig getifaddr "${iface}" 2>/dev/null || true)"
                if [ -n "${ip}" ] && [ "${ip}" != "127.0.0.1" ]; then
                    ips+=("${ip}")
                fi
            fi
        done
    fi

    # 2. Linux hostname -I
    if [ ${#ips[@]} -eq 0 ] && command -v hostname >/dev/null 2>&1; then
        for ip in $(hostname -I 2>/dev/null); do
            if [ -n "${ip}" ] && [ "${ip}" != "127.0.0.1" ] && [[ ! "${ip}" =~ ^198\.18\. ]]; then
                ips+=("${ip}")
            fi
        done
    fi

    # 3. 兜底：ifconfig
    if [ ${#ips[@]} -eq 0 ] && command -v ifconfig >/dev/null 2>&1; then
        for ip in $(ifconfig 2>/dev/null | grep 'inet ' | awk '{print $2}'); do
            if [ -n "${ip}" ] && [ "${ip}" != "127.0.0.1" ] && [[ ! "${ip}" =~ ^198\.18\. ]] && [[ ! "${ip}" =~ ^169\.254\. ]]; then
                ips+=("${ip}")
            fi
        done
    fi

    if [ ${#ips[@]} -gt 0 ]; then
        printf "%s\n" "${ips[@]}" | sort -u
    fi
}

get_lan_ip() {
    get_all_lan_ips | head -n 1
}

# 监听与地址配置（绑定 0.0.0.0 同时监听本地与局域网）
BIND_HOST="0.0.0.0"
BACKEND_PORT=8000
FRONTEND_PORT=5173
LOCAL_HOST="127.0.0.1"
LAN_IP="$(get_lan_ip)"

BACKEND_LOCAL_URL="http://${LOCAL_HOST}:${BACKEND_PORT}"
FRONTEND_LOCAL_URL="http://${LOCAL_HOST}:${FRONTEND_PORT}"
BACKEND_CHECK_URL="${BACKEND_LOCAL_URL}/api/settings"
FRONTEND_CHECK_URL="${FRONTEND_LOCAL_URL}"

if [ -n "${LAN_IP}" ]; then
    BACKEND_LAN_URL="http://${LAN_IP}:${BACKEND_PORT}"
    FRONTEND_LAN_URL="http://${LAN_IP}:${FRONTEND_PORT}"
else
    BACKEND_LAN_URL=""
    FRONTEND_LAN_URL=""
fi

# 终端颜色输出
if [ -t 1 ]; then
    COLOR_RESET="\033[0m"
    COLOR_RED="\033[31m"
    COLOR_GREEN="\033[32m"
    COLOR_YELLOW="\033[33m"
    COLOR_BLUE="\033[34m"
    COLOR_CYAN="\033[36m"
    COLOR_BOLD="\033[1m"
else
    COLOR_RESET=""
    COLOR_RED=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_BLUE=""
    COLOR_CYAN=""
    COLOR_BOLD=""
fi

log_info() {
    echo -e "${COLOR_BLUE}[INFO]${COLOR_RESET} $*"
}

log_success() {
    echo -e "${COLOR_GREEN}[SUCCESS]${COLOR_RESET} $*"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $*"
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $*"
}

# 确保运行时目录存在
ensure_runtime_dirs() {
    mkdir -p "${RUN_DIR}" "${LOG_DIR}"
    chmod 700 "${RUN_DIR}" 2>/dev/null || true
}

# 检查依赖环境
check_dependencies() {
    local target="$1"
    local has_error=0

    if [ "${target}" = "backend" ] || [ "${target}" = "all" ]; then
        if ! command -v uv >/dev/null 2>&1; then
            log_error "未检测到 uv 命令。后端启动需要 uv，请先安装 uv (https://docs.astral.sh/uv/)"
            has_error=1
        fi
    fi

    if [ "${target}" = "frontend" ] || [ "${target}" = "all" ]; then
        if ! command -v pnpm >/dev/null 2>&1; then
            log_error "未检测到 pnpm 命令。前端启动需要 pnpm，请先安装 pnpm (https://pnpm.io/)"
            has_error=1
        fi
    fi

    if [ "${has_error}" -ne 0 ]; then
        return 1
    fi
    return 0
}

# 检查配置文件
check_env_file() {
    if [ ! -f "${PROJECT_ROOT}/.env" ]; then
        if [ -f "${PROJECT_ROOT}/.env.example" ]; then
            log_warn "未检测到 .env 配置文件，已从 .env.example 自动创建"
            cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
        fi
    fi
}

# 进程是否存活
is_running() {
    local pid="$1"
    [ -z "${pid}" ] && return 1
    local output
    output="$(kill -0 "${pid}" 2>&1)"
    local res=$?
    if [ "${res}" -eq 0 ]; then
        return 0
    fi
    # 若返回权限受限（如沙箱环境或跨权限），说明进程确实存在
    if echo "${output}" | grep -iqE "operation not permitted|permission denied"; then
        return 0
    fi
    return 1
}

# 获取服务 PID
get_service_pid() {
    local pid_file="$1"
    if [ -f "${pid_file}" ]; then
        local pid
        pid="$(cat "${pid_file}" 2>/dev/null | tr -d '[:space:]')"
        if is_running "${pid}"; then
            echo "${pid}"
            return 0
        else
            # 进程已不存在，清除陈旧 PID 文件
            rm -f "${pid_file}"
        fi
    fi
    return 1
}

# 获取进程的全部子孙进程 PID
get_descendant_pids() {
    local parent="$1"
    local children
    children="$(pgrep -P "${parent}" 2>/dev/null || true)"
    for child in ${children}; do
        get_descendant_pids "${child}"
        echo "${child}"
    done
}

# 停止服务及其进程树
stop_service_process() {
    local service_name="$1"
    local pid_file="$2"
    local pid
    pid="$(get_service_pid "${pid_file}" || true)"

    if [ -z "${pid}" ]; then
        log_info "${service_name} 未在运行"
        rm -f "${pid_file}"
        return 0
    fi

    log_info "正在停止 ${service_name} (PID: ${pid})..."
    local all_pids
    all_pids="$(get_descendant_pids "${pid}") ${pid}"

    # 发送优雅终止信号 SIGTERM
    kill -TERM ${all_pids} 2>/dev/null || true

    local timeout=10
    local count=0
    while is_running "${pid}" && [ "${count}" -lt "${timeout}" ]; do
        sleep 0.5
        count=$((count + 1))
    done

    # 超时仍未退出则强制杀死 SIGKILL
    if is_running "${pid}"; then
        log_warn "${service_name} 优雅退出超时，正在强制停止..."
        all_pids="$(get_descendant_pids "${pid}") ${pid}"
        kill -KILL ${all_pids} 2>/dev/null || true
        sleep 0.5
    fi

    if is_running "${pid}"; then
        log_error "无法停止 ${service_name} (PID: ${pid})"
        return 1
    fi

    rm -f "${pid_file}"
    log_success "${service_name} 已停止"
    return 0
}

# 等待服务就绪（健康检查）
wait_for_service_ready() {
    local name="$1"
    local pid="$2"
    local url="$3"
    local log_file="$4"
    local max_wait="${5:-15}"
    local waited=0

    log_info "等待 ${name} 响应就绪..."
    while [ "${waited}" -lt "${max_wait}" ]; do
        # 检测进程是否提前异常退出
        if ! is_running "${pid}"; then
            log_error "${name} 启动失败，进程已退出！"
            if [ -f "${log_file}" ]; then
                echo -e "${COLOR_RED}--- ${name} 错误日志 (${log_file}) ---${COLOR_RESET}"
                tail -n 25 "${log_file}"
                echo -e "${COLOR_RED}------------------------------------------------${COLOR_RESET}"
            fi
            return 1
        fi

        # 尝试 HTTP 探测
        if curl -s -f -m 1 "${url}" >/dev/null 2>&1; then
            log_success "${name} 已就绪"
            return 0
        fi

        sleep 1
        waited=$((waited + 1))
    done

    if is_running "${pid}"; then
        log_warn "${name} 在 ${max_wait} 秒内未完成 HTTP 响应探测，但进程仍存活 (PID: ${pid})"
        log_warn "可通过日志查看启动细节: tail -f ${log_file}"
        return 0
    else
        log_error "${name} 启动超时且进程已退出"
        return 1
    fi
}
