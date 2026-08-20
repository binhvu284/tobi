import { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, Save } from 'lucide-react'
import { runtimeStore, useRuntimeStore } from '../../stores/runtime'

export default function DeveloperRuntimeLoop() {
  const { loops, loopSelection, connection } = useRuntimeStore()
  const selectedValue = loopSelection ? `${loopSelection.recipe_id}@${loopSelection.version}` : ''
  const [draft, setDraft] = useState(selectedValue)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => setDraft(selectedValue), [selectedValue])
  const recipes = useMemo(() => loops.map(recipe => ({
    ...recipe,
    value: `${recipe.recipe_id}@${recipe.version}`,
  })), [loops])

  const save = async () => {
    const recipe = recipes.find(item => item.value === draft)
    if (!recipe) return
    setSaving(true)
    setSaved(false)
    try {
      await runtimeStore.saveLoopSelection({ recipe_id: recipe.recipe_id, version: recipe.version })
      setSaved(true)
      window.setTimeout(() => setSaved(false), 1600)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="border border-border bg-surface">
      <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-heading">Default loop</h2>
          <p className="mt-0.5 text-[10px] uppercase text-muted">Developer preference</p>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <select
            aria-label="Default Developer loop"
            value={draft}
            disabled={connection === 'loading' || recipes.length === 0}
            onChange={event => { setDraft(event.target.value); setSaved(false) }}
            className="h-9 min-w-0 flex-1 border border-border bg-bg px-2 text-xs text-text outline-none focus:border-accent sm:w-72"
          >
            <option value="">Select loop</option>
            {recipes.map(recipe => (
              <option key={recipe.value} value={recipe.value}>{recipe.name} - {recipe.version}</option>
            ))}
          </select>
          <button
            type="button"
            title="Save default loop"
            aria-label="Save default loop"
            disabled={!draft || draft === selectedValue || saving}
            onClick={() => void save()}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center border border-border text-muted transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : saved ? <Check size={15} className="text-success" /> : <Save size={15} />}
          </button>
        </div>
      </div>
    </section>
  )
}
