import { useState } from 'react'

type Props = {
  onSend: (command: string) => Promise<void>
}

export default function TaskCommandBox({ onSend }: Props) {
  const [command, setCommand] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    const value = command.trim()
    if (!value || loading) return
    setLoading(true)
    try {
      await onSend(value)
      setCommand('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded border border-border bg-bg p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Task Command</p>
      <div className="flex gap-2">
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="Send instruction for this task..."
          className="flex-1 rounded border border-border bg-surface px-2 py-1.5 text-xs text-text outline-none focus:border-accent"
        />
        <button
          onClick={submit}
          className="rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"
        >
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  )
}
