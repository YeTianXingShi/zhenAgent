import { useState } from 'react'
import { request, send, type Provider, type ModelProfile, type Settings as RuntimeSettings, type Limits } from './api'

type Props = { providers: Provider[]; settings: RuntimeSettings | null; refresh: () => Promise<void>; close: () => void; error: (message: string) => void }

const emptyModel = (): ModelProfile => ({ id: '', label: '', reasoning_effort: 'high', max_output_tokens: 8192 })
const limitFields: Record<keyof Limits, { label: string; min: number; max: number; step: number | 'any' }> = {
  max_model_calls: { label: '任务模型调用上限', min: 1, max: 200, step: 1 },
  command_timeout: { label: '单条命令超时（秒）', min: 1, max: 3600, step: 1 },
  request_timeout: { label: '模型请求超时（秒）', min: 1, max: 1800, step: 1 },
  max_retries: { label: '额外重试次数', min: 0, max: 10, step: 1 },
  retry_delay: { label: '初次重试等待（秒）', min: 0.1, max: 30, step: 'any' },
  command_output_bytes: { label: '命令输出上限（字节）', min: 1024, max: 16777216, step: 1 },
  model_output_bytes: { label: '模型响应上限（字节）', min: 1024, max: 16777216, step: 1 },
  read_file_bytes: { label: '文件读取与写入上限（字节）', min: 1024, max: 4194304, step: 1 },
  tool_context_bytes: { label: '送入模型的工具结果上限（字节）', min: 1024, max: 262144, step: 1 },
}

export default function SettingsPanel({ providers, settings, refresh, close, error }: Props) {
  const [tab, setTab] = useState('models')
  const [selected, setSelected] = useState<string | null>(providers[0]?.id || null)
  const initial = providers.find(provider => provider.id === selected)
  const [name, setName] = useState(initial?.name || '')
  const [base, setBase] = useState(initial?.base_url || '')
  const [key, setKey] = useState('')
  const [models, setModels] = useState<ModelProfile[]>(initial?.models.map(model => ({ ...model })) || [emptyModel()])
  const [limits, setLimits] = useState(settings?.limits)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [problem, setProblem] = useState('')
  const report = (message: string) => { setProblem(message); error(message) }

  function choose(provider: Provider | null) {
    setSelected(provider?.id || null)
    setName(provider?.name || '')
    setBase(provider?.base_url || '')
    setKey('')
    setModels(provider?.models.map(model => ({ ...model })) || [emptyModel()])
    setNotice('')
    setProblem('')
  }

  function modelField(index: number, field: keyof ModelProfile, value: string | number) {
    setModels(entries => entries.map((entry, at) => at === index ? { ...entry, [field]: value } : entry))
  }

  async function saveProvider(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setProblem(''); setNotice('')
    try {
      const saved = await request<Provider>(`/api/providers${selected ? '/' + selected : ''}`, send(selected ? 'PUT' : 'POST', {
        name, base_url: base, api_key: key || null, models,
      }))
      await refresh()
      choose(saved)
      setNotice('配置已保存，之后启动的任务使用新配置。')
    } catch (failure) { report((failure as Error).message) }
    finally { setBusy(false) }
  }

  async function removeProvider() {
    if (!selected || !window.confirm('删除此服务配置？已有会话引用的服务不能删除。')) return
    setBusy(true)
    try { await request(`/api/providers/${selected}`, { method: 'DELETE' }); await refresh(); choose(null); setNotice('服务已删除。') }
    catch (failure) { report((failure as Error).message) }
    finally { setBusy(false) }
  }

  async function saveLimits(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try { await request('/api/settings', send('PUT', limits)); await refresh(); setNotice('运行上限已保存，对之后启动的任务生效。') }
    catch (failure) { report((failure as Error).message) }
    finally { setBusy(false) }
  }

  return <div className="modal-backdrop" onClick={event => event.target === event.currentTarget && close()}>
    <section className="settings modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header className="modal-header"><div><span className="eyebrow">工作台设置</span><h2 id="settings-title">模型与运行配置</h2></div><button className="icon-button" onClick={close} aria-label="关闭设置">×</button></header>
      <nav className="tabs"><button className={tab === 'models' ? 'active' : ''} onClick={() => { setTab('models'); setNotice('') }}>模型服务</button><button className={tab === 'runtime' ? 'active' : ''} onClick={() => { setTab('runtime'); setNotice('') }}>运行上限</button></nav>
      {notice && <div className="success notice">{notice}</div>}
      {problem && <div className="inline-error notice" role="alert">{problem}</div>}
      {tab === 'models' ? <div className="settings-grid">
        <aside className="provider-list">{providers.map(provider => <button key={provider.id} className={selected === provider.id ? 'selected' : ''} onClick={() => choose(provider)}><strong>{provider.name}</strong><span>{provider.has_api_key ? '密钥已设置' : '待设置密钥'}</span></button>)}<button className="add-provider" onClick={() => choose(null)}>＋ 添加服务</button></aside>
        <form onSubmit={saveProvider} className="provider-form">
          <div className="form-intro"><h3>{selected ? '编辑服务' : '添加 Responses 服务'}</h3><p>会话固定服务与模型。运行中的任务保持启动时的配置。</p></div>
          <label>服务名称<input value={name} required maxLength={100} onChange={event => setName(event.target.value)} placeholder="例如 DeepSeek" /></label>
          <label>服务地址<input value={base} required onChange={event => setBase(event.target.value)} placeholder="https://api.deepseek.com" /><span className="field-note">填写 base_url，末尾不含 /responses。OpenAI 官方地址包含 /v1。</span></label>
          <label>API key<input type="password" value={key} autoComplete="new-password" onChange={event => setKey(event.target.value)} placeholder={providers.find(provider => provider.id === selected)?.has_api_key ? '已设置，留空保留原密钥' : '输入服务的 API key'} /><span className="field-note">仅在本机保存，保存后不回显。</span></label>
          <div className="section-label"><h3>模型</h3><button type="button" className="text-button" onClick={() => setModels(entries => [...entries, emptyModel()])}>＋ 添加模型</button></div>
          {models.map((model, index) => <div className="model-fields" key={index}>
            <div className="form-row"><label>模型 ID<input value={model.id} required onChange={event => modelField(index, 'id', event.target.value)} placeholder="deepseek-flash" /></label><label>显示名称<input value={model.label} onChange={event => modelField(index, 'label', event.target.value)} placeholder="可选" /></label></div>
            <div className="form-row"><label>思考强度<select value={model.reasoning_effort} onChange={event => modelField(index, 'reasoning_effort', event.target.value)}><option value="none">关闭 · none</option><option value="low">低 · low</option><option value="high">高 · high</option><option value="max">最高 · max</option></select></label><label>输出 token 上限<input type="number" min={128} max={131072} required value={model.max_output_tokens} onChange={event => modelField(index, 'max_output_tokens', Number(event.target.value))} /></label></div>
            {models.length > 1 && <button className="text-button danger" type="button" onClick={() => setModels(entries => entries.filter((_, at) => at !== index))}>移除此模型</button>}
          </div>)}
          <p className="field-note">思考 token 计入输出上限。其他服务需实际支持所选思考强度。</p>
          <footer className="form-actions">{selected && <button type="button" className="text-button danger" disabled={busy} onClick={removeProvider}>删除服务</button>}<button className="primary" disabled={busy}>{busy ? '保存中…' : '保存配置'}</button></footer>
        </form>
      </div> : <form className="runtime-form" onSubmit={saveLimits}>
        <div className="workspace-note"><span className="eyebrow">当前工作目录</span><code>{settings?.workspace_root || '后端未连接'}</code><p>工作目录在后端启动配置中设置。命令在本机执行，目录不是沙箱。</p></div>
        {limits && <div className="limits-grid">{Object.entries(limitFields).map(([field, rule]) => <label key={field}>{rule.label}<input required type="number" min={rule.min} max={rule.max} step={rule.step} value={limits[field as keyof Limits]} onChange={event => setLimits({ ...limits, [field]: Number(event.target.value) })} /></label>)}</div>}
        <p className="field-note">请求重试也计入模型调用次数。重试等待按倍数增加，最长 30 秒。</p>
        <footer className="form-actions"><button className="primary" disabled={busy || !limits}>{busy ? '保存中…' : '保存运行上限'}</button></footer>
      </form>}
    </section>
  </div>
}
