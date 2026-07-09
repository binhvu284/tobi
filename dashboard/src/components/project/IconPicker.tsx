import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { X, Upload, Loader2 } from 'lucide-react'
import { pmUploadIcon } from '../../api'
import { ICON_PACK } from './ProjectIcon'
import { useToast } from '../../context/ToastProvider'

const EMOJIS = [
  '📁','🚀','💡','🎯','📊','🛠','🌱','🔬','📱','💼','🎨','🏗','⚡','🔐','🌍','🧪','📝','🤖',
  '🎮','🎧','🎬','📚','🧠','🛒','🏪','✈️','🚗','🏠','💰','📈','🩺','🏋️','☕','🍜','🌟','🔥',
  '🧭','🗺️','🎁','🪄','🧩','⚙️','🖥️','📷','🎤','🌈','🐉','🦾',
]

export type IconChoice = { icon_type: 'emoji' | 'icon' | 'custom'; icon_value: string }

/** Icon picker (#12 D53/D56): emoji tab + curated lucide pack + upload-your-own.
 * Rendered as a small popover card; the parent positions/anchors it. */
export default function IconPicker({ projectId, onPick, onClose }: {
  projectId?: number
  onPick: (choice: IconChoice) => void
  onClose: () => void
}) {
  const { toast } = useToast()
  const [tab, setTab] = useState<'emoji' | 'icon' | 'upload'>('emoji')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function uploadFile(f: File) {
    if (!f.type.startsWith('image/')) { toast({ kind: 'error', title: 'Pick an image file' }); return }
    setBusy(true)
    try {
      // Downscale to ≤128px so stored icons stay tiny (DB-backed).
      const dataUrl = await downscale(f, 128)
      const r = await pmUploadIcon(dataUrl, projectId)
      onPick({ icon_type: 'custom', icon_value: String(r.id) })
    } catch (e) {
      toast({ kind: 'error', title: 'Icon upload failed', detail: (e as Error).message })
    } finally { setBusy(false) }
  }

  return (
    <motion.div initial={{ opacity: 0, scale: 0.96, y: 6 }} animate={{ opacity: 1, scale: 1, y: 0 }}
      className="w-72 rounded-xl border border-border bg-surface p-3 shadow-2xl">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex gap-1 rounded-lg border border-border p-0.5 text-[11px]">
          {(['emoji', 'icon', 'upload'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`rounded px-2 py-1 capitalize transition-colors ${tab === t ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text'}`}>
              {t === 'icon' ? 'Icons' : t === 'upload' ? 'Upload' : 'Emoji'}
            </button>
          ))}
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted hover:text-text"><X size={14} /></button>
      </div>

      {tab === 'emoji' && (
        <div className="grid max-h-48 grid-cols-8 gap-1 overflow-y-auto">
          {EMOJIS.map(e => (
            <button key={e} onClick={() => onPick({ icon_type: 'emoji', icon_value: e })}
              className="flex h-8 w-8 items-center justify-center rounded text-lg transition-colors hover:bg-accent/15">
              {e}
            </button>
          ))}
        </div>
      )}

      {tab === 'icon' && (
        <div className="grid max-h-48 grid-cols-8 gap-1 overflow-y-auto">
          {Object.entries(ICON_PACK).map(([key, Icon]) => (
            <button key={key} onClick={() => onPick({ icon_type: 'icon', icon_value: key })} title={key}
              className="flex h-8 w-8 items-center justify-center rounded text-muted transition-colors hover:bg-accent/15 hover:text-accent">
              <Icon size={17} />
            </button>
          ))}
        </div>
      )}

      {tab === 'upload' && (
        <div className="py-2">
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f) }} />
          <button onClick={() => fileRef.current?.click()} disabled={busy}
            className="flex w-full flex-col items-center gap-2 rounded-lg border border-dashed border-border py-5 text-muted transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50">
            {busy ? <Loader2 size={20} className="animate-spin" /> : <Upload size={20} />}
            <span className="text-xs">{busy ? 'Uploading…' : 'Upload an image (PNG/SVG/JPG)'}</span>
            <span className="text-[10px] text-muted">Stored in the TOBI database, resized to 128px</span>
          </button>
        </div>
      )}
    </motion.div>
  )
}

async function downscale(file: File, max: number): Promise<string> {
  // SVGs stay as-is (vector, small); raster images get downscaled through a canvas.
  if (file.type === 'image/svg+xml') {
    const text = await file.text()
    return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(text)))}`
  }
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((res, rej) => {
      const i = new Image()
      i.onload = () => res(i); i.onerror = rej; i.src = url
    })
    const scale = Math.min(1, max / Math.max(img.width, img.height))
    const w = Math.max(1, Math.round(img.width * scale))
    const h = Math.max(1, Math.round(img.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = w; canvas.height = h
    canvas.getContext('2d')!.drawImage(img, 0, 0, w, h)
    return canvas.toDataURL('image/png')
  } finally {
    URL.revokeObjectURL(url)
  }
}
