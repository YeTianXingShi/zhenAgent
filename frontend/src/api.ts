export const API = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API + path, {
      ...options,
      headers: { ...(options?.body ? { 'Content-Type': 'application/json' } : {}), ...options?.headers },
    })
  } catch {
    throw new Error('无法连接后端，请确认 Python 后端已启动。')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败（${response.status}）`)
  }
  return response.status === 204 ? undefined as T : await response.json() as T
}

export const send = (method: string, value: unknown): RequestInit => ({ method, body: JSON.stringify(value) })

export type ModelProfile = { id: string; label: string; reasoning_effort: string; max_output_tokens: number }
export type Provider = { id: string; name: string; base_url: string; models: ModelProfile[]; has_api_key: boolean }
export type Session = { id: string; title: string; provider_id: string; model_id: string; provider_name?: string; updated_at: string; last_status?: string }
export type Attempt = { id: string; round: number; attempt: number; status: string; text: string; reasoning: string; error: string | null; usage: { input_tokens?: number; output_tokens?: number } | null }
export type ToolPreview = { command?: string; cwd?: string; warning?: string; path?: string; diff?: string; content?: string; fingerprint?: string | null; operation?: 'create' | 'update' }
export type Tool = { id: string; round: number; name: string; arguments: string; status: string; error: string | null; approval_status: string | null; preview: ToolPreview | null; result: Record<string, unknown> | null; live_output: string }
export type Run = { id: string; input_text: string; status: string; error: string | null; call_count: number; attempts: Attempt[]; tools: Tool[]; created_at: string; legacy_reasoning: string }
export type Detail = Session & { runs: Run[]; event_cursor: number }
export type Limits = { max_model_calls: number; command_timeout: number; request_timeout: number; max_retries: number; retry_delay: number; command_output_bytes: number; model_output_bytes: number; read_file_bytes: number; tool_context_bytes: number }
export type Settings = { workspace_root: string; limits: Limits; active_run: { id: string } | null }

export const running = (status: string) => status === 'running' || status === 'awaiting_approval'
export const statuses: Record<string, string> = { running: '执行中', awaiting_approval: '等待审批', completed: '已完成', interrupted: '已中断', cancelled: '已停止', failed: '失败', denied: '已拒绝', limited: '达到上限', pending: '待执行' }
export const toolNames: Record<string, string> = { list_directory: '列目录', read_file: '读取文件', search_files: '搜索文件', write_file: '写入文件', edit_file: '编辑文件', execute_command: '执行命令' }
