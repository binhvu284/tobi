import { useEffect, useState } from 'react'
import type { OwnerInputChecklistItem } from '../api'

type Props = {
  items: OwnerInputChecklistItem[]
  onSubmit: (items: OwnerInputChecklistItem[]) => Promise<void>
  onEvaluate: () => Promise<void>
}

export default function OwnerInputChecklist({ items, onSubmit, onEvaluate }: Props) {
  const [draft, setDraft] = useState<OwnerInputChecklistItem[]>(items)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setDraft(items)
  }, [items])

  const update = (index: number, patch: Partial<OwnerInputChecklistItem>) => {
    setDraft((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  const submit = async () => {
    setLoading(true)
    try {
      await onSubmit(draft)
      await onEvaluate()
    } finally {
      setLoading(false)
    }
  }

  if (draft.length === 0) {
    return (
      <div className="rounded border border-border bg-bg p-3 text-xs text-muted">
        No checklist requirements on this task.
      </div>
    )
  }

  return (
    <div className="rounded border border-border bg-bg p-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Owner Input Checklist</p>
      <div className="space-y-2">
        {draft.map((item, idx) => (
          <div key={item.item_key} className="rounded border border-border bg-surface p-2">
            <p className="mb-1 text-xs font-medium text-text">
              {item.label} {item.required ? <span className="text-danger">*</span> : null}
            </p>
            {item.input_type === 'file' ? (
              <input
                value={item.file_path || ''}
                onChange={(e) => update(idx, { file_path: e.target.value, status: e.target.value ? 'submitted' : 'pending' })}
                placeholder={item.placeholder || 'Path to file'}
                className="w-full rounded border border-border bg-bg px-2 py-1 text-xs text-text"
              />
            ) : (
              <textarea
                value={item.value_text || ''}
                onChange={(e) => update(idx, { value_text: e.target.value, status: e.target.value ? 'submitted' : 'pending' })}
                placeholder={item.placeholder || 'Enter text'}
                rows={3}
                className="w-full rounded border border-border bg-bg px-2 py-1 text-xs text-text"
              />
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-end">
        <button
          onClick={submit}
          className="rounded border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20"
        >
          {loading ? 'Submitting...' : 'Submit and evaluate'}
        </button>
      </div>
    </div>
  )
}
