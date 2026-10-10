import { useEffect, useRef, useState } from 'react'
import { DropdownMenu } from 'radix-ui'
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { running, type Session } from './api'

export default function SessionMenu({ session, onAction }: {
  session: Session; onAction: (session: Session, kind: 'rename' | 'delete') => void
}) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pointerOpened = useRef(false)
  const actionTaken = useRef(false)
  const clearTimer = () => { clearTimeout(timer.current) }
  const leave = () => { clearTimer(); timer.current = setTimeout(() => setOpen(false), 180) }
  useEffect(() => () => clearTimeout(timer.current), [])
  const act = (kind: 'rename' | 'delete') => {
    clearTimer(); actionTaken.current = true
    trigger.current?.focus()
    setOpen(false); onAction(session, kind)
  }
  return <DropdownMenu.Root modal={false} open={open} onOpenChange={value => {
    clearTimer(); setOpen(value)
    if (value) actionTaken.current = false
  }}>
    <DropdownMenu.Trigger asChild>
      <Button ref={trigger} type="button" variant="ghost" size="icon" className="session-menu-trigger"
        aria-label={`会话操作：${session.title}`}
        onPointerEnter={event => { if (event.pointerType === 'mouse') { clearTimer(); pointerOpened.current = true; actionTaken.current = false; setOpen(true) } }}
        onPointerLeave={event => { if (event.pointerType === 'mouse') leave() }}
        onPointerDown={() => { pointerOpened.current = false }}
        onKeyDown={() => { pointerOpened.current = false }}>
        <MoreHorizontal size={18} aria-hidden="true" />
      </Button>
    </DropdownMenu.Trigger>
    <DropdownMenu.Portal><DropdownMenu.Content className="session-menu" side="right" align="start" sideOffset={6} collisionPadding={12}
      onPointerEnter={clearTimer} onPointerLeave={leave}
      onCloseAutoFocus={event => { if (actionTaken.current || pointerOpened.current) event.preventDefault() }}
      onFocusOutside={() => { pointerOpened.current = false }}>
      <DropdownMenu.Item className="session-menu-option" onSelect={() => act('rename')}><Pencil size={15} aria-hidden="true" />重命名</DropdownMenu.Item>
      <DropdownMenu.Separator className="session-menu-separator" />
      <DropdownMenu.Item className="session-menu-option session-menu-delete" disabled={running(session.last_status || '')} onSelect={() => act('delete')}><Trash2 size={15} aria-hidden="true" />删除会话</DropdownMenu.Item>
      {running(session.last_status || '') && <div className="session-menu-note">先停止任务再删除</div>}
    </DropdownMenu.Content></DropdownMenu.Portal>
  </DropdownMenu.Root>
}
