// The shell's glyphs, one component each. Every path is the shell's own; `className`
// defaults to the shell's `.ic` so the stroke rules in ui2.css apply unchanged.
import { createLucideIcon } from 'lucide-react'
import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>
function I({ className = 'ic', children, ...rest }: P) {
  return <svg className={className} viewBox="0 0 24 24" aria-hidden="true" {...rest}>{children}</svg>
}

/* the brand: a hexagon with a neuron inside. Unstyled here; the parent sizes and colours it. */
export const BRAND_PATHS = [
  'M12 3.4 5 7.3v9.4l7 3.9 7-3.9V7.3z',
  'M12 6.2v3.2M12 14.6v3.2M8.2 9.4l2.2 1.3M13.6 13.3l2.2 1.3M15.8 9.4l-2.2 1.3M10.4 13.3l-2.2 1.3',
]
export const BrandGlyph = (p: P) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...p}>
    <path d={BRAND_PATHS[0]} /><circle cx="12" cy="12" r="2.6" /><path d={BRAND_PATHS[1]} />
  </svg>
)
/** The rail entry, in lucide's own shape so AppShell and the tab strip take it like any other. */
export const Ui2Icon = createLucideIcon('Ui2', [
  ['path', { d: BRAND_PATHS[0], key: 'hex' }],
  ['circle', { cx: '12', cy: '12', r: '2.6', key: 'core' }],
  ['path', { d: BRAND_PATHS[1], key: 'spokes' }],
])

/* Anthropic's mark: ten tapered blades from a common centre. The mark carries the vendor,
   not the accent. */
const BLADE = 'M12 2.7c.63 0 1.14.51 1.14 1.14l-.29 6.4a.85.85 0 0 1-1.7 0l-.29-6.4c0-.63.51-1.14 1.14-1.14z'
export const Anthropic = ({ className = 'provider', ...rest }: P) => (
  <svg className={className} viewBox="0 0 24 24" aria-hidden="true" {...rest}>
    <g fill="currentColor">
      {[0, 36, 72, 108, 144, 180, 216, 252, 288, 324].map(a => <path key={a} d={BLADE} transform={`rotate(${a} 12 12)`} />)}
    </g>
  </svg>
)

export const ChevDown = (p: P) => <I {...p}><path d="m6 9.5 6 5 6-5" /></I>
export const ChevUp = (p: P) => <I {...p}><path d="m6 14.5 6-5 6 5" /></I>
export const Tick = (p: P) => <I {...p}><path d="m5 12.5 4.5 4.5L19 7" /></I>
export const Cross = (p: P) => <I {...p}><path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" /></I>
export const Clock = (p: P) => <I {...p}><path d="M3.2 12a8.8 8.8 0 1 0 2.9-6.5L3 8.2" /><path d="M3 3.4v4.9h4.9" /><path d="M12 7.4V12l3 1.8" /></I>
export const Plus = (p: P) => <I {...p}><path d="M12 5.5v13M5.5 12h13" /></I>
export const Paperclip = (p: P) => <I {...p}><path d="M20.4 11.2 12 19.6a5 5 0 0 1-7.1-7.1l8.5-8.4a3.3 3.3 0 0 1 4.7 4.7l-8.4 8.4a1.7 1.7 0 0 1-2.4-2.3l7.8-7.8" /></I>
export const Plug = (p: P) => <I {...p}><path d="M9 3.5v5M15 3.5v5" /><path d="M7 8.5h10v3.6a5 5 0 0 1-10 0z" /><path d="M12 17.1v3.4" /></I>
export const SpeakerLoud = (p: P) => <I {...p}><path d="M11.5 4.6 6.9 8.4H3.6v7.2h3.3l4.6 3.8z" /><path d="M15.4 9.1a4.1 4.1 0 0 1 0 5.8" /><path d="M18.1 6.4a7.9 7.9 0 0 1 0 11.2" /></I>
export const SpeakerOff = (p: P) => <I {...p}><path d="M11.5 4.6 6.9 8.4H3.6v7.2h3.3l4.6 3.8z" /><path d="m15.6 9.8 5 4.4M20.6 9.8l-5 4.4" /></I>
export const Send = (p: P) => <I {...p}><path d="M12 19V5M6 11l6-6 6 6" /></I>
export const MicLock = (p: P) => (
  <I {...p}>
    <rect x="7.4" y="2.6" width="5.8" height="10.2" rx="2.9" /><path d="M4.2 10.9a6.1 6.1 0 0 0 8 5.8" />
    <path d="M10.3 18.3V20.9" /><path d="M7.2 20.9h6.2" />
    <path d="M16.7 15.5v-1.4a2.15 2.15 0 0 1 4.3 0v1.4" strokeWidth="1.5" />
    <rect x="15.5" y="15.5" width="6.7" height="5.5" rx="1.6" fill="currentColor" stroke="none" />
  </I>
)
export const Mic = (p: P) => <I {...p}><rect x="9.1" y="2.6" width="5.8" height="10.2" rx="2.9" /><path d="M5.9 10.9a6.1 6.1 0 0 0 12.2 0" /><path d="M12 17.1v3.2" /><path d="M8.9 20.3h6.2" /></I>
export const MicMute = (p: P) => <I {...p}><rect x="9.1" y="2.6" width="5.8" height="10.2" rx="2.9" /><path d="M5.9 10.9a6.1 6.1 0 0 0 12.2 0" /><path d="M12 17.1v3.2" /><path d="M8.9 20.3h6.2" /><path d="M4.4 3.4 19.6 20.6" /></I>
export const Power = (p: P) => <I {...p}><path d="M12 3.9v8.2" /><path d="M6.9 6.6a7.2 7.2 0 1 0 10.2 0" /></I>
export const ArrowDown = (p: P) => <I {...p}><path d="M12 5v14M6 13l6 6 6-6" /></I>
export const Corners = (p: P) => <I {...p}><path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15" /></I>
export const Files = (p: P) => <I {...p}><path d="M14 2.8H7.5a2 2 0 0 0-2 2v14.4a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7.6z" /><path d="M14 2.8V7.6h4.5" /><path d="M3 7.5v11.8A2.2 2.2 0 0 0 5.2 21.5H14" /></I>
export const Book = (p: P) => <I {...p}><path d="M6.5 3.5h11a2 2 0 0 1 2 2V18a2.5 2.5 0 0 1-2.5 2.5H7A2.5 2.5 0 0 1 4.5 18V5.5a2 2 0 0 1 2-2z" /><path d="M8.5 8h7M8.5 12h7" /></I>
export const Sliders = (p: P) => <I {...p}><path d="M4 7.5h7M15.5 7.5H20M4 16.5h3.5M12 16.5H20" /><circle cx="13.2" cy="7.5" r="2.3" /><circle cx="9.7" cy="16.5" r="2.3" /></I>
export const Doc = (p: P) => <I {...p}><path d="M14 2.8H7.5a2 2 0 0 0-2 2v14.4a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7.6z" /><path d="M14 2.8V7.6h4.5" /></I>
export const Frame = (p: P) => <I {...p}><rect x="3" y="4.5" width="18" height="15" rx="2.2" /><path d="M3 9.5h18" /></I>
export const Tool = (p: P) => (
  <I {...p}>
    <path d="M12 4.2a3.1 3.1 0 0 0-3 2.3 2.9 2.9 0 0 0-2.4 4.4A3 3 0 0 0 7 15.8a3 3 0 0 0 2.9 3.9 2.6 2.6 0 0 0 2.1-1" />
    <path d="M12 4.2a3.1 3.1 0 0 1 3 2.3 2.9 2.9 0 0 1 2.4 4.4 3 3 0 0 1-.4 4.9 3 3 0 0 1-2.9 3.9 2.6 2.6 0 0 1-2.1-1" />
    <path d="M12 4.2v14.6" />
  </I>
)
export const Retry = (p: P) => <I {...p}><path d="M20.5 12a8.5 8.5 0 1 1-2.8-6.3" /><path d="M20.8 4.4v4.8h-4.8" /></I>
export const Stop = (p: P) => <I {...p}><rect x="6.5" y="6.5" width="11" height="11" rx="2" /></I>
export const ImageDoc = (p: P) => <I {...p}><rect x="3" y="4.5" width="18" height="15" rx="2.2" /><path d="M4 18.5 9.5 11l4 5 2.5-3.2 4 5.7z" /><circle cx="8.4" cy="9" r="1.3" /></I>
export const SheetDoc = (p: P) => <I {...p}><rect x="3" y="4.5" width="18" height="15" rx="2.2" /><path d="M4.5 9.5h15M4.5 14.5h15M9.5 4.5v15" /></I>
export const ChartAct = (p: P) => <I {...p}><rect x="3" y="4.5" width="18" height="15" rx="2.2" /><path d="M7 15.5l3.4-4 2.6 3 4-5.5" /></I>
export const LogAct = (p: P) => <I {...p}><path d="M4 5.5h6a2.5 2.5 0 0 1 2 2.5v11a2 2 0 0 0-1.6-1.5H4z" /><path d="M20 5.5h-6a2.5 2.5 0 0 0-2 2.5v11a2 2 0 0 1 1.6-1.5H20z" /></I>

/* file tiles, tinted by what they are */
export const TileDoc = (p: P) => <I {...p}><path d="M13.5 3H7.6A2.1 2.1 0 0 0 5.5 5.1v13.8A2.1 2.1 0 0 0 7.6 21h8.8a2.1 2.1 0 0 0 2.1-2.1V8z" /><path d="M13.5 3v5h5" /><path d="M8.7 12.9h6.6M8.7 16.5h4.4" /></I>
export const TileImg = (p: P) => <I {...p}><rect x="3" y="4.6" width="18" height="14.8" rx="2.6" /><circle cx="8.7" cy="9.7" r="1.5" /><path d="M3.5 17.6 9 12.1l3.5 3.5 3.2-2.8 4.8 4.4" /></I>
export const TileSheet = (p: P) => (
  <I {...p}>
    <rect x="3" y="4.6" width="18" height="14.8" rx="2.6" />
    <rect x="3" y="4.6" width="18" height="4.6" rx="2.6" fill="currentColor" stroke="none" opacity=".24" />
    <path d="M3 9.2h18M3 14.3h18M9.4 9.2v10.2M15 9.2v10.2" />
  </I>
)
export const TileLog = (p: P) => <I {...p}><path d="M13.5 3H7.6A2.1 2.1 0 0 0 5.5 5.1v13.8A2.1 2.1 0 0 0 7.6 21h8.8a2.1 2.1 0 0 0 2.1-2.1V8z" /><path d="M13.5 3v5h5" /><path d="m8.9 12.7 2.1 2-2.1 2M12.9 16.7h3" /></I>

import type { ActIcon, FileKind } from './model'
export function ActGlyph({ icon, className }: { icon: ActIcon; className?: string }) {
  switch (icon) {
    case 'canvas': return <Frame className={className} />
    case 'doc': return <Doc className={className} />
    case 'chart': return <ChartAct className={className} />
    case 'sheet': return <SheetDoc className={className} />
    case 'log': return <LogAct className={className} />
    default: return <Tool className={className} />
  }
}
export function FileGlyph({ kind, className }: { kind: FileKind | 'recap'; className?: string }) {
  switch (kind) {
    case 'image': return <ImageDoc className={className} />
    case 'sheet': return <SheetDoc className={className} />
    case 'log': return <Book className={className} />
    case 'recap': return <Clock className={className} />
    default: return <Doc className={className} />
  }
}
export function TileGlyph({ kind, className }: { kind: FileKind | 'recap'; className?: string }) {
  switch (kind) {
    case 'image': return <TileImg className={className} />
    case 'sheet': return <TileSheet className={className} />
    case 'log': return <TileLog className={className} />
    case 'recap': return <Clock className={className} />
    default: return <TileDoc className={className} />
  }
}
export const tileClass = (kind: FileKind | 'recap') =>
  kind === 'image' ? 'f-img' : kind === 'sheet' ? 'f-sheet' : kind === 'log' ? 'f-log' : kind === 'recap' ? 'f-time' : 'f-doc'
