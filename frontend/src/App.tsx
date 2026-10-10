import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { NativeSelect } from "@/components/ui/native-select"
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { API, request, send, running, statuses, toolNames, type Provider, type Session, type Detail, type Run, type Tool, type Settings } from './api'
import SettingsPanel from './Settings'
import FilePreview, { isNewFile } from './FilePreview'
import Reasoning from './Reasoning'
import TokenUsage from './TokenUsage'

const activeRun = (detail: Detail | null) => detail?.runs.find(run => running(run.status))

function ToolCard({ tool, act, busy }: { tool: Tool; act: (id: string, value: boolean) => void; busy: string | null }) {
  const awaiting = tool.approval_status === 'pending' && tool.status === 'awaiting_approval'
  let args: Record<string, unknown> = {}
  try { args = JSON.parse(tool.arguments) } catch { /* 参数错误由后端报告 */ }
  const output = tool.result?.output as string | undefined || tool.live_output
  const create = tool.preview?.diff !== undefined && isNewFile(tool.preview)
  return <details className={`tool-card ${awaiting ? 'approval-card' : ''}`} open={awaiting || undefined}>
    <summary><span className="tool-symbol">{tool.name === 'execute_command' ? '›_' : create ? '+' : '↳'}</span><span className="tool-name">{create ? '新建文件' : toolNames[tool.name] || tool.name}<small>{String(args.path || args.command || args.pattern || '').slice(0, 100)}</small></span><span className={`status ${tool.status}`}>{statuses[tool.status] || tool.status}</span></summary>
    <div className="tool-body">
      {tool.preview?.command && <><div className="command-label"><span>将在本机执行</span><code>{tool.preview.cwd}</code></div><pre className="command"><code>{tool.preview.command}</code></pre><p className="field-note">{tool.preview.warning}</p></>}
      {tool.preview?.diff !== undefined && <FilePreview preview={tool.preview} />}
      {!tool.preview && <pre className="tool-args">{JSON.stringify(args, null, 2)}</pre>}
      {output && <pre className="command-output">{output}</pre>}
      {tool.result && !output && <pre className="tool-result">{JSON.stringify(tool.result, null, 2)}</pre>}
      {tool.error && <p className="inline-error">{tool.error}</p>}
      {awaiting && <div className="approval-actions"><span>拒绝会结束本次任务。</span><Button variant="ghost" className="secondary" disabled={busy === tool.id} onClick={() => act(tool.id, false)}>拒绝</Button><Button className="primary" disabled={busy === tool.id} onClick={() => act(tool.id, true)}>批准执行</Button></div>}
    </div>
  </details>
}

function RunView({ run, act, approvalBusy }: { run: Run; act: (id: string, value: boolean) => void; approvalBusy: string | null }) {
  const rounds = [...new Set([...run.attempts.map(attempt => attempt.round), ...run.tools.map(tool => tool.round)])].sort((a, b) => a - b)
  return <article className="run">
    <div className="user-message"><span className="message-label">你</span><div>{run.input_text}</div></div>
    <div className="agent-message"><div className="agent-avatar">z</div><div className="agent-content"><div className="agent-label">zhenAgent <span className={`status ${run.status}`}>{statuses[run.status]}</span></div>
      {run.legacy_reasoning && <Reasoning text={run.legacy_reasoning} status="completed" legacy />}
      {rounds.map(round => <Fragment key={round}>{run.attempts.filter(attempt => attempt.round === round).map(attempt => <div key={attempt.id} className={`attempt ${attempt.status}`}>
        {attempt.reasoning && <Reasoning text={attempt.reasoning} status={attempt.status} />}
        {attempt.text && <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a> }}>{attempt.text}</ReactMarkdown></div>}
        {attempt.status === 'running' && <span className="working"><i />{attempt.reasoning && !attempt.text ? '模型思考中' : '模型生成中'}</span>}
        {attempt.error && <p className="attempt-error">尝试 {attempt.attempt} 已中断：{attempt.error}</p>}
        <TokenUsage attempt={attempt} />
      </div>)}
      {run.tools.filter(tool => tool.round === round).map(tool => <ToolCard key={tool.id} tool={tool} act={act} busy={approvalBusy} />)}</Fragment>)}
      {run.error && <div className="run-error">{run.error}</div>}
      <div className="run-meta">模型调用 {run.call_count} 次 · {new Date(run.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</div>
    </div></div>
  </article>
}

export default function App() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [settings, setSettings] = useState<Settings | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [connected, setConnected] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [sessionAction, setSessionAction] = useState<{ session: Session; kind: 'rename' | 'delete' } | null>(null)
  const [sessionTitle, setSessionTitle] = useState('')
  const [sessionBusy, setSessionBusy] = useState(false)
  const [sessionProblem, setSessionProblem] = useState('')
  const dialogOpener = useRef<HTMLElement | null>(null)
  const rememberOpener = () => { dialogOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null }
  const restoreDialogFocus = () => { if (dialogOpener.current?.isConnected) dialogOpener.current.focus() }
  const openSettings = () => { rememberOpener(); setShowSettings(true) }
  const [newProvider, setNewProvider] = useState('')
  const [newModel, setNewModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [approvalBusy, setApprovalBusy] = useState<string | null>(null)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const detailRef = useRef(detail)
  detailRef.current = detail
  const scroll = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const submission = useRef<{ session: string; text: string; id: string } | null>(null)
  const currentRun = activeRun(detail)

  const refresh = useCallback(async () => {
    const [nextProviders, nextSessions, nextSettings] = await Promise.all([
      request<Provider[]>('/api/providers'), request<Session[]>('/api/sessions'), request<Settings>('/api/settings'),
    ])
    setProviders(nextProviders); setSessions(nextSessions); setSettings(nextSettings); setConnected(true)
  }, [])

  const load = useCallback(async (id: string) => {
    const snapshot = await request<Detail>(`/api/sessions/${id}`)
    if (selectedRef.current === id && (!detailRef.current || detailRef.current.id !== id || snapshot.event_cursor >= detailRef.current.event_cursor)) {
      detailRef.current = snapshot
      setDetail(snapshot)
    }
  }, [])

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        await refresh()
        if (alive && selectedRef.current) await load(selectedRef.current)
      } catch { if (alive) setConnected(false) }
    }
    void poll()
    const timer = window.setInterval(poll, 2500)
    return () => { alive = false; clearInterval(timer) }
  }, [refresh, load])

  useEffect(() => {
    setDetail(null); setText(''); setError(''); stick.current = true
    if (selected) void load(selected).catch(failure => setError(failure.message))
  }, [selected, load])

  useEffect(() => {
    if (!selected || !currentRun) return
    const stream = new EventSource(`${API}/api/runs/${currentRun.id}/events?after=${detailRef.current?.event_cursor || 0}`)
    let timer: number | undefined
    let closed = false
    const update = () => {
      if (timer !== undefined) return
      timer = window.setTimeout(() => {
        timer = undefined
        if (!closed) void load(selected).catch(failure => setError(failure.message))
      }, 120)
    }
    stream.onmessage = update
    stream.addEventListener('end', () => { stream.close(); void load(selected).catch(failure => setError(failure.message)); void refresh().catch(() => setConnected(false)) })
    stream.onerror = () => { setConnected(false); update() }
    stream.onopen = () => { setConnected(true); update() }
    return () => { closed = true; stream.close(); if (timer !== undefined) clearTimeout(timer) }
  }, [selected, currentRun?.id, load, refresh])

  useEffect(() => {
    if (stick.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }, [detail])

  function chooseProvider(id: string) {
    setNewProvider(id)
    setNewModel(providers.find(provider => provider.id === id)?.models[0]?.id || '')
  }

  function manageSession(session: Session, kind: 'rename' | 'delete') {
    rememberOpener(); setSessionTitle(session.title); setSessionProblem(''); setSessionAction({ session, kind })
  }

  async function saveSessionAction(event: React.FormEvent) {
    event.preventDefault()
    if (!sessionAction || sessionBusy) return
    const { session, kind } = sessionAction
    setSessionBusy(true); setSessionProblem('')
    try {
      if (kind === 'rename') {
        await request(`/api/sessions/${session.id}`, send('PUT', { title: sessionTitle.trim() }))
        setSessions(entries => entries.map(entry => entry.id === session.id ? { ...entry, title: sessionTitle.trim() } : entry))
        if (selectedRef.current === session.id) await load(session.id)
      } else {
        await request(`/api/sessions/${session.id}`, { method: 'DELETE' })
        setSessions(entries => entries.filter(entry => entry.id !== session.id))
        if (selectedRef.current === session.id) {
          selectedRef.current = null; detailRef.current = null
          setSelected(null); setDetail(null); setText(''); submission.current = null
        }
      }
      setSessionAction(null)
      await refresh()
    } catch (failure) { setSessionProblem((failure as Error).message) }
    finally { setSessionBusy(false) }
  }

  function openNew() {
    rememberOpener()
    setError('')
    if (!providers.length) { setShowSettings(true); return }
    chooseProvider(providers[0]?.id || '')
    setShowNew(true)
  }

  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true)
    try {
      const session = await request<Session>('/api/sessions', send('POST', { provider_id: newProvider, model_id: newModel }))
      await refresh(); setSelected(session.id); setShowNew(false)
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }

  async function submit(event?: React.FormEvent) {
    event?.preventDefault()
    if (!selected || !text.trim() || busy || currentRun || settings?.active_run) return
    setBusy(true); setError(''); stick.current = true
    if (!submission.current || submission.current.session !== selected || submission.current.text !== text) {
      submission.current = { session: selected, text, id: crypto.randomUUID() }
    }
    try {
      await request(`/api/sessions/${selected}/runs`, send('POST', { text, client_request_id: submission.current.id }))
      submission.current = null
      setText(''); await load(selected); await refresh()
    } catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }

  async function stop() {
    if (!currentRun) return
    setBusy(true)
    try { await request(`/api/runs/${currentRun.id}/cancel`, { method: 'POST' }); await load(selected!); await refresh() }
    catch (failure) { setError((failure as Error).message) }
    finally { setBusy(false) }
  }

  async function approve(id: string, value: boolean) {
    setApprovalBusy(id)
    try { await request(`/api/approvals/${id}`, send('POST', { approve: value })); if (selected) await load(selected); await refresh() }
    catch (failure) { setError((failure as Error).message) }
    finally { setApprovalBusy(null) }
  }

  const boundProvider = providers.find(provider => provider.id === detail?.provider_id)
  const boundModel = boundProvider?.models.find(model => model.id === detail?.model_id)
  const otherBusy = settings?.active_run && settings.active_run.id !== currentRun?.id

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon">z</span><div><strong>zhenAgent</strong><small>本地工作台</small></div><span className="version">0.1</span></div>
      <Button variant="ghost" className="new-session" onClick={openNew} disabled={!connected || !providers.length}>＋ 新建会话</Button>
      <div className="sidebar-label">会话记录 <span>{sessions.length}</span></div>
      <nav className="session-list">{sessions.map(session => <div className="session-row" key={session.id}><Button variant="ghost" className={`session-item ${selected === session.id ? 'active' : ''}`} onClick={() => setSelected(session.id)}><span className={running(session.last_status || '') ? 'session-dot busy-dot' : 'session-dot'} /><div><strong>{session.title}</strong><small>{session.provider_name} · {session.model_id}</small></div></Button><div className="session-controls"><Button variant="ghost" size="icon" aria-label={`重命名会话：${session.title}`} title="重命名" onClick={() => manageSession(session, 'rename')}>✎</Button><Button variant="ghost" size="icon" aria-label={`删除会话：${session.title}`} title={running(session.last_status || '') ? '先停止任务再删除' : '删除会话'} disabled={running(session.last_status || '')} onClick={() => manageSession(session, 'delete')}>×</Button></div></div>)}{!sessions.length && <p className="sidebar-empty">创建第一个会话，<br />从一个明确的任务开始。</p>}</nav>
      <footer className="sidebar-footer"><Button variant="ghost" onClick={openSettings} disabled={!connected}><span>⚙</span>模型与运行设置 <span className="chevron">›</span></Button><div className="sidebar-state"><i className={connected ? 'online' : ''} />{connected ? '后端已连接' : '等待后端连接'}</div></footer>
    </aside>
    <main className="main-panel">
      <header className="topbar"><div><span className="eyebrow">LOCAL AGENT</span><h1>{detail?.title || '开始你的下一项任务'}</h1></div><div className="topbar-right">{detail && <span className="model-chip">{boundModel?.resolved_label || boundModel?.label || detail.model_id}</span>}<span className="local-badge">本机 · 单任务</span></div></header>
      {error && <div className="error-banner" role="alert"><span>{error}</span><Button variant="ghost" onClick={() => setError('')} aria-label="关闭错误提示">×</Button></div>}
      <div className="conversation" ref={scroll} onScroll={() => { const area = scroll.current!; stick.current = area.scrollHeight - area.scrollTop - area.clientHeight < 100 }}>
        {!detail || detail.runs.length === 0 ? <div className="welcome">
          <div className="welcome-symbol">z<span>✦</span></div><span className="eyebrow">想法，从这里开始执行</span><h2>{selected ? '给这个会话一个任务' : '把任务交给你的 agent'}</h2><p>读取文件、处理内容、编写并运行脚本。<br />每次写入和命令执行前，由你批准。</p>
          <div className="capabilities"><div><span>01</span><strong>读懂工作目录</strong><p>读取与搜索文件，找到任务所需信息。</p></div><div><span>02</span><strong>看清每次操作</strong><p>修改差异和命令在执行前展示。</p></div><div><span>03</span><strong>留下任务过程</strong><p>会话与结果保存在本机，随时回看。</p></div></div>
          {!selected && <div className="welcome-actions"><Button className="primary" onClick={openNew} disabled={!connected || !providers.length}>新建会话 <span>↗</span></Button><Button variant="ghost" className="text-button" disabled={!connected} onClick={openSettings}>配置模型服务</Button></div>}
          {!connected && <p className="offline-note">等待 Python 后端启动后即可开始。</p>}
        </div> : <div className="timeline">{detail.runs.map(run => <RunView key={run.id} run={run} act={approve} approvalBusy={approvalBusy} />)}</div>}
      </div>
      <div className="composer-wrap"><div className="workspace-bar"><span>⌁ 工作目录</span><code title={settings?.workspace_root}>{settings?.workspace_root || '等待后端配置'}</code>{currentRun && <span className="working"><i />{statuses[currentRun.status]}</span>}</div>
        <form className="composer" onSubmit={submit}><Textarea value={text} onChange={event => setText(event.target.value)} disabled={!selected || !connected} placeholder={selected ? '描述你希望完成的任务…' : '新建会话后，描述你希望完成的任务…'} rows={3} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); void submit() } }} /><div className="composer-actions"><span>{otherBusy ? '其他会话正在执行，结束后可发送' : '⌘ / Ctrl + Enter 发送'}</span>{currentRun ? <Button variant="ghost" type="button" className="stop-button" onClick={stop} disabled={busy}>■ 停止任务</Button> : <Button className="primary send-button" disabled={!selected || !text.trim() || busy || !connected || Boolean(settings?.active_run)}>发送 <span>↑</span></Button>}</div></form>
        <p className="composer-note">页面关闭后任务继续执行。点击停止会保留已完成的操作。</p>
      </div>
    </main>
    {sessionAction && <Dialog open onOpenChange={open => { if (!open && !sessionBusy) setSessionAction(null) }}><DialogContent className="modal new-dialog" showCloseButton={false} onCloseAutoFocus={event => { event.preventDefault(); restoreDialogFocus() }}><form onSubmit={saveSessionAction}><header className="modal-header"><DialogTitle>{sessionAction.kind === 'rename' ? '重命名会话' : '删除会话'}</DialogTitle></header><DialogDescription className="new-description">{sessionAction.kind === 'rename' ? '修改会话显示名称，不改变消息内容。' : `将永久删除“${sessionAction.session.title}”及其消息、任务、工具结果和事件记录，无法撤销。工作目录文件和模型服务配置会保留。`}</DialogDescription>{sessionAction.kind === 'rename' && <label>会话名称<Input autoFocus required maxLength={100} value={sessionTitle} disabled={sessionBusy} onChange={event => setSessionTitle(event.target.value)} /></label>}{sessionProblem && <p role="alert" className="inline-error">{sessionProblem}</p>}<footer className="form-actions"><Button type="button" variant="outline" disabled={sessionBusy} onClick={() => setSessionAction(null)}>取消</Button><Button type="submit" variant={sessionAction.kind === 'delete' ? 'destructive' : 'default'} disabled={sessionBusy || (sessionAction.kind === 'rename' && !sessionTitle.trim())}>{sessionBusy ? '处理中…' : sessionAction.kind === 'rename' ? '保存名称' : '永久删除'}</Button></footer></form></DialogContent></Dialog>}
    {showSettings && <SettingsPanel providers={providers} settings={settings} refresh={refresh} close={() => setShowSettings(false)} error={setError} restoreFocus={restoreDialogFocus} />}
    {showNew && <Dialog open onOpenChange={setShowNew}><DialogContent className="modal new-dialog" showCloseButton={false} onCloseAutoFocus={event => { event.preventDefault(); restoreDialogFocus() }}><form onSubmit={create}><header className="modal-header"><div><span className="eyebrow">新的开始</span><DialogTitle>新建会话</DialogTitle></div><Button variant="ghost" type="button" className="icon-button" aria-label="关闭新建会话" onClick={() => setShowNew(false)}>×</Button></header>{error && <p className="inline-error" role="alert">{error}</p>}<DialogDescription className="new-description">每个会话固定服务和模型，需要切换时新建会话。</DialogDescription><label>模型服务<NativeSelect value={newProvider} required onChange={event => chooseProvider(event.target.value)}>{providers.map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</NativeSelect></label><label>模型<NativeSelect value={newModel} required onChange={event => setNewModel(event.target.value)}>{providers.find(provider => provider.id === newProvider)?.models.map(model => <option key={model.id} value={model.id}>{model.resolved_label || model.label || model.id}</option>)}</NativeSelect></label><footer className="form-actions"><Button className="primary" disabled={busy || !newProvider || !newModel}>创建会话</Button></footer></form></DialogContent></Dialog>}
  </div>
}
