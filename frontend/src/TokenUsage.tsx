import type { Attempt } from './api'

const count = (value: number | undefined) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : null
const display = (value: number | null) => value === null ? '未提供' : value.toLocaleString()

export default function TokenUsage({ attempt }: { attempt: Attempt }) {
  const usage = attempt.usage
  if (!usage) return attempt.status === 'completed' ? <div className="usage">服务未返回 token 用量，无法判断上下文是否达到上限。</div> : null
  const input = count(usage.input_tokens)
  const output = count(usage.output_tokens)
  const cached = count(usage.input_tokens_details?.cached_tokens)
  const reasoning = count(usage.output_tokens_details?.reasoning_tokens)
  const total = count(usage.total_tokens) ?? (input !== null && output !== null ? input + output : null)
  return <div className="usage" title="服务返回的本次调用实际用量。缓存是输入的一部分，推理是输出的一部分，均不重复计数。此统计不包含之后新增的消息和工具结果。">
    <div>输入 {display(input)} · 输出 {display(output)} · 总计 {display(total)} tokens</div>
    <div>缓存命中 {display(cached)} · 推理 {display(reasoning)} tokens</div>
    {attempt.context_limit != null && <div>本次调用用量 / 上下文上限：{display(total)} / {attempt.context_limit.toLocaleString()} tokens{total === null ? ' · 用量未提供，无法判断是否达到上限' : total >= attempt.context_limit ? ' · 已达到上限' : ''}</div>}
  </div>
}
