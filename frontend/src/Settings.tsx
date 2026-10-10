import { useEffect, useState } from 'react'
import { request, send, type Provider, type ModelProfile, type Catalog, type CatalogModel, type CatalogProvider, type Settings as RuntimeSettings, type Limits } from './api'

type Props = { providers: Provider[]; settings: RuntimeSettings | null; refresh: () => Promise<void>; close: () => void; error: (message: string) => void }

const emptyModel = (): ModelProfile => ({ id: '', label: '', reasoning_effort: null, max_output_tokens: null, context_tokens: null, temperature: null })
const editableModel = (model: ModelProfile): ModelProfile => ({ id: model.id, label: model.label, reasoning_effort: model.reasoning_effort ?? null, max_output_tokens: model.max_output_tokens ?? null, context_tokens: model.context_tokens ?? null, temperature: model.temperature ?? null })
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
  const [models, setModels] = useState<ModelProfile[]>(initial?.models.map(editableModel) || [emptyModel()])
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogId, setCatalogId] = useState(initial?.catalog_provider_id || '')
  const [catalogModels, setCatalogModels] = useState<CatalogModel[]>([])
  const [catalogBusy, setCatalogBusy] = useState(false)
  const [catalogProblem, setCatalogProblem] = useState('')
  const [limits, setLimits] = useState(settings?.limits)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [problem, setProblem] = useState('')
  const report = (message: string) => { setProblem(message); error(message) }

  useEffect(() => {
    let active = true
    request<Catalog>('/api/model-catalog').then(value => { if (active) setCatalog(value) })
      .catch(failure => { if (active) setCatalogProblem((failure as Error).message) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    setCatalogModels([])
    setCatalogProblem('')
    if (catalogId) request<CatalogProvider & { models: CatalogModel[] }>(`/api/model-catalog/providers/${encodeURIComponent(catalogId)}`)
      .then(value => { if (active) setCatalogModels(value.models) })
      .catch(failure => { if (active) setCatalogProblem((failure as Error).message) })
    return () => { active = false }
  }, [catalogId, catalog?.fetched_at])

  async function updateCatalog() {
    setCatalogBusy(true)
    setCatalogProblem('')
    try {
      const value = await request<Catalog>('/api/model-catalog/refresh', { method: 'POST' })
      setCatalog(value)
      await refresh()
    } catch (failure) { setCatalogProblem((failure as Error).message) }
    finally { setCatalogBusy(false) }
  }

  function choose(provider: Provider | null) {
    setSelected(provider?.id || null)
    setName(provider?.name || '')
    setBase(provider?.base_url || '')
    setKey('')
    setModels(provider?.models.map(editableModel) || [emptyModel()])
    setCatalogId(provider?.catalog_provider_id || '')
    setNotice('')
    setProblem('')
  }

  function modelField(index: number, field: keyof ModelProfile, value: string | number | null) {
    setModels(entries => entries.map((entry, at) => at === index
      ? field === 'id' ? { ...emptyModel(), id: String(value ?? '') } : { ...entry, [field]: value }
      : entry))
  }

  function chooseCatalog(id: string) {
    setCatalogId(id)
    const provider = catalog?.providers.find(entry => entry.id === id)
    if (provider && !selected) {
      setName(provider.name)
      setBase(provider.api || '')
      setModels([emptyModel()])
    }
  }

  function restoreDefaults(index: number) {
    setModels(entries => entries.map((entry, at) => at === index
      ? { ...entry, reasoning_effort: null, max_output_tokens: null, context_tokens: null, temperature: null } : entry))
  }

  async function saveProvider(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setProblem(''); setNotice('')
    try {
      const saved = await request<Provider>(`/api/providers${selected ? '/' + selected : ''}`, send(selected ? 'PUT' : 'POST', {
        name, base_url: base, api_key: key || null, catalog_provider_id: catalogId || null, models,
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
          <div className="catalog-status">
            <div><strong>Models.dev 模型信息</strong><button type="button" className="text-button" disabled={catalogBusy} onClick={updateCatalog}>{catalogBusy ? '更新中…' : '更新模型信息'}</button></div>
            <p>来源：{catalog?.source_url || 'https://models.dev/api.json'}<br />{catalog?.fetched_at ? `更新于 ${new Date(catalog.fetched_at).toLocaleString()}${catalog.stale ? ' · 缓存已过期' : ''}` : '尚未获取模型信息'}</p>
            {(catalog?.error || catalogProblem) && <p role="alert">{catalogProblem || catalog?.error}。已有缓存会继续使用，也可手动填写。</p>}
          </div>
          <label>参数来源<select value={catalogId} onChange={event => chooseCatalog(event.target.value)}><option value="">手动配置 · 使用服务端默认参数</option>{catalogId && !catalog?.providers.some(entry => entry.id === catalogId) && <option value={catalogId}>{catalogId} · 模型信息暂不可用</option>}{catalog?.providers.map(provider => <option value={provider.id} key={provider.id}>{provider.name} · {provider.id}</option>)}</select><span className="field-note">选择与实际服务对应的 Models.dev 模型信息。收录不代表支持 Responses，请确认服务支持此接口。</span></label>
          <label>服务名称<input value={name} required maxLength={100} onChange={event => setName(event.target.value)} placeholder="例如 DeepSeek" /></label>
          <label>服务地址<input value={base} required onChange={event => setBase(event.target.value)} placeholder="https://api.deepseek.com" /><span className="field-note">填写 base_url，末尾不含 /responses。OpenAI 官方地址包含 /v1。</span></label>
          <label>API key<input type="password" value={key} autoComplete="new-password" onChange={event => setKey(event.target.value)} placeholder={providers.find(provider => provider.id === selected)?.has_api_key ? '已设置，留空保留原密钥' : '输入服务的 API key'} /><span className="field-note">仅在本机保存，保存后不回显。</span></label>
          <div className="section-label"><h3>模型</h3><button type="button" className="text-button" onClick={() => setModels(entries => [...entries, emptyModel()])}>＋ 添加模型</button></div>
          {models.map((model, index) => {
            const metadata = catalogModels.find(entry => entry.id === model.id)
            const efforts = metadata?.reasoning_efforts || []
            return <div className="model-fields" key={index}>
              {catalogId && <label>从模型列表选择<select value={metadata ? model.id : ''} onChange={event => modelField(index, 'id', event.target.value)}><option value="">选择模型，或在下面填写 ID</option>{catalogModels.map(entry => <option key={entry.id} value={entry.id}>{entry.name} · {entry.id}{entry.status === 'deprecated' ? '（已弃用）' : ''}</option>)}</select></label>}
              <div className="form-row"><label>模型 ID<input value={model.id} required onChange={event => modelField(index, 'id', event.target.value)} placeholder="填写服务支持的模型 ID" /></label><label>显示名称<input value={model.label} onChange={event => modelField(index, 'label', event.target.value)} placeholder={metadata?.name || '使用模型 ID'} /></label></div>
              <p className="field-note">{metadata ? `上下文上限：${metadata.context_tokens?.toLocaleString() || '未提供'} tokens · 输出上限：${metadata.output_tokens?.toLocaleString() || '未提供'} tokens` : 'Models.dev 未收录此模型，留空参数将使用服务端默认值。'}{metadata && !metadata.tool_call && ' · Models.dev 未声明工具调用能力'}{metadata?.status === 'deprecated' && ' · 模型已标记弃用'}</p>
              <div className="form-row"><label>思考强度{efforts.length ? <select value={model.reasoning_effort ?? ''} onChange={event => modelField(index, 'reasoning_effort', event.target.value || null)}><option value="">服务端默认 · 不指定</option>{model.reasoning_effort && !efforts.includes(model.reasoning_effort) && <option value={model.reasoning_effort}>{model.reasoning_effort} · 已保存，Models.dev 未声明</option>}{efforts.map(effort => <option key={effort} value={effort}>{effort === 'none' ? '关闭 · none' : effort}</option>)}</select> : <input value={model.reasoning_effort ?? ''} onChange={event => modelField(index, 'reasoning_effort', event.target.value || null)} placeholder="留空使用服务端默认" pattern="[a-z][a-z0-9_-]{0,49}" />}<span className="field-note">Models.dev 提供可选档位，没有指定默认强度。</span></label><label>输出 token 上限<input type="number" min={1} step={1} value={model.max_output_tokens ?? ''} onChange={event => modelField(index, 'max_output_tokens', event.target.value === '' ? null : Number(event.target.value))} placeholder={metadata?.output_tokens ? `跟随模型信息：${metadata.output_tokens}` : '留空使用服务端默认'} /><span className="field-note">{model.max_output_tokens !== null ? '当前使用手动覆盖值。' : metadata?.output_tokens ? '当前跟随 Models.dev，模型信息更新后新任务采用新值。' : '当前不发送输出上限参数。'}</span></label></div>
              <div className="form-row">
                <label>上下文 token 上限<input type="number" min={1} step={1} value={model.context_tokens ?? ''} onChange={event => modelField(index, 'context_tokens', event.target.value === '' ? null : Number(event.target.value))} placeholder={metadata?.context_tokens ? `跟随模型信息：${metadata.context_tokens}` : '留空不设置本地上限'} /><span className="field-note">{model.context_tokens !== null ? '当前使用手动覆盖值。' : metadata?.context_tokens ? '当前跟随 Models.dev。' : '模型信息未提供上限，当前不设置本地上限。'}按最近一次响应的实际输入与输出总量判断，达到上限时停止并保留历史。</span></label>
                <label>温度<input type="number" min={0} max={2} step="any" value={model.temperature ?? ''} onChange={event => modelField(index, 'temperature', event.target.value === '' ? null : Number(event.target.value))} placeholder="留空使用服务端默认" /><span className="field-note">范围 0–2。Models.dev 未提供数值默认值，留空不发送 temperature。{catalogId === 'deepseek' && 'DeepSeek 思考模式下此参数不生效。'}</span></label>
              </div>
              <p className="field-note">用量只取服务返回的 usage，不做本地估算。缓存命中计入输入；新消息和工具结果的 token 数要等下一次响应才能得知。</p>
              <div className="model-actions"><button className="text-button" type="button" onClick={() => restoreDefaults(index)}>恢复默认参数</button>{models.length > 1 && <button className="text-button danger" type="button" onClick={() => setModels(entries => entries.filter((_, at) => at !== index))}>移除此模型</button>}</div>
            </div>
          })}
          <p className="field-note">思考 token 计入输出上限。Models.dev 描述的能力可能与 Responses 接口限制不同；服务不接受这些参数值时，可手动覆盖。</p>
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
