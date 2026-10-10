import type { ToolPreview } from './api'

export const isNewFile = (preview: ToolPreview) => preview.operation === 'create'
  || (preview.operation === undefined && 'fingerprint' in preview && preview.fingerprint === null)

function diffClass(line: string) {
  if (line.startsWith('+++ ') || line.startsWith('--- ')) return 'diff-header'
  if (line.startsWith('@@')) return 'diff-hunk'
  if (line.startsWith('+')) return 'diff-added'
  if (line.startsWith('-')) return 'diff-removed'
  return 'diff-context'
}

export default function FilePreview({ preview }: { preview: ToolPreview }) {
  const create = isNewFile(preview)
  const content = preview.content
  const lines = typeof content === 'string' && content ? content.split('\n') : []
  if (content?.endsWith('\n')) lines.pop()
  const diff = preview.diff || ''
  const diffLines = diff ? diff.replace(/\n$/, '').split('\n') : []
  const added = diffLines.filter(line => line.startsWith('+') && !line.startsWith('+++ ')).length
  const removed = diffLines.filter(line => line.startsWith('-') && !line.startsWith('--- ')).length

  return <section className={`file-preview ${create ? 'file-create' : 'file-update'}`} aria-label={create ? '新建文件内容预览' : '文件修改差异'}>
    <header className="file-preview-header"><span className="file-operation">{create ? '＋ 新建文件' : '修改文件'}</span><code>{preview.path}</code>{create ? <span className="file-preview-mode">完整内容</span> : <span className="file-change-count"><b>+{added}</b><i>−{removed}</i></span>}</header>
    {create && typeof content === 'string' ? <>
      <div className="file-code"><div className="file-lines">{lines.length ? lines.map((line, index) => <div className="file-line" key={index}><span className="line-number" aria-hidden="true">{index + 1}</span><code>{line || ' '}</code></div>) : <p className="empty-file">将创建一个空文件</p>}</div></div>
      <footer className="file-preview-footer">{lines.length} 行 · UTF-8{content && !content.endsWith('\n') ? ' · 末尾无换行' : ''}</footer>
    </> : <div className="file-diff">{diffLines.length ? diffLines.map((line, index) => <code className={`diff-line ${diffClass(line)}`} key={index}>{line || ' '}</code>) : <p className="empty-file">内容没有变化</p>}</div>}
  </section>
}
