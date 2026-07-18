import { Code2, ShieldCheck } from 'lucide-react'
import codexSvg from '@lobehub/icons-static-svg/icons/codex-color.svg?raw'
import openCodeSvg from '@lobehub/icons-static-svg/icons/opencode.svg?raw'
import claudeCodeSvg from '@lobehub/icons-static-svg/icons/claudecode-color.svg?raw'

export type DeveloperTool = 'native' | 'codex' | 'opencode' | 'model_review' | 'claude'

const TOOL_META: Record<DeveloperTool, { name: string; color: string; svg?: string }> = {
  native: { name: 'Mission Control', color: '#38BDF8' },
  codex: { name: 'Codex CLI', color: '#10A37F', svg: codexSvg },
  opencode: { name: 'OpenCode CLI', color: '#F4F4F5', svg: openCodeSvg },
  model_review: { name: 'Independent review', color: '#A78BFA' },
  claude: { name: 'Claude Code', color: '#D97757', svg: claudeCodeSvg },
}

export function developerToolName(tool: DeveloperTool) {
  return TOOL_META[tool].name
}

export default function DeveloperToolLogo({ tool, size = 18 }: { tool: DeveloperTool; size?: number }) {
  const meta = TOOL_META[tool]
  return (
    <span
      title={meta.name}
      className="inline-flex shrink-0 items-center justify-center rounded-md"
      style={{
        width: size + 14,
        height: size + 14,
        color: meta.color,
        background: `color-mix(in srgb, ${meta.color} 13%, rgb(var(--surface)))`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${meta.color} 26%, transparent)`,
      }}
    >
      {meta.svg
        ? <span aria-hidden className="inline-flex items-center justify-center leading-none" style={{ width: size, height: size }} dangerouslySetInnerHTML={{ __html: meta.svg }} />
        : tool === 'model_review' ? <ShieldCheck size={size} /> : <Code2 size={size} />}
    </span>
  )
}
