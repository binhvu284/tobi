// News V2 (#23): overlapping round source logos — every section header carries one
// so the owner can see at a glance which connected sources feed that data.
import SourceLogo from '../SourceLogo'

export default function SourceIconGroup({ sources, size = 18 }: { sources: string[]; size?: number }) {
  if (!sources.length) return null
  return (
    <span className="flex items-center -space-x-1.5" title={`Data from: ${sources.join(', ')}`}>
      {sources.map(name => (
        <span key={name} style={{ width: size, height: size }}
          className="flex items-center justify-center rounded-full border border-border bg-background ring-1 ring-background">
          <SourceLogo name={name} size={Math.max(9, size - 8)} variant="inline" />
        </span>
      ))}
    </span>
  )
}
