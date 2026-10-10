import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function Reasoning({ text, status, legacy = false }: { text: string; status: string; legacy?: boolean }) {
  return <details className="reasoning-card">
    <summary><span className="reasoning-symbol" aria-hidden="true">◇</span><span>{legacy ? '历史思考记录' : '思考过程'}</span><small>{status === 'running' ? '生成中' : status === 'interrupted' ? '已中断' : '模型返回'} · {text.length.toLocaleString('zh-CN')} 字符</small><span className="reasoning-chevron" aria-hidden="true">⌄</span></summary>
    <div className="reasoning-body">{legacy && <p className="reasoning-note">旧版已保存的推理文本，按任务汇总显示。</p>}<div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a> }}>{text}</ReactMarkdown></div></div>
  </details>
}
