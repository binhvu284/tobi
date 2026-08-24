/**
 * Official LLM brand logos — sourced from LobeHub's icon set via the dependency-free
 * static-svg distribution (@lobehub/icons-static-svg; the React package needs React 19).
 * Mono marks (OpenAI, Grok, Ollama, OpenRouter) use currentColor so they adapt to the
 * theme; `-color` variants carry their real brand colors.
 */
import openaiSvg from '@lobehub/icons-static-svg/icons/openai.svg?raw'
import claudeSvg from '@lobehub/icons-static-svg/icons/claude-color.svg?raw'
import zhipuSvg from '@lobehub/icons-static-svg/icons/zhipu-color.svg?raw'
import grokSvg from '@lobehub/icons-static-svg/icons/grok.svg?raw'
import geminiSvg from '@lobehub/icons-static-svg/icons/gemini-color.svg?raw'
import openrouterSvg from '@lobehub/icons-static-svg/icons/openrouter.svg?raw'
import ollamaSvg from '@lobehub/icons-static-svg/icons/ollama.svg?raw'
import deepseekSvg from '@lobehub/icons-static-svg/icons/deepseek-color.svg?raw'
import qwenSvg from '@lobehub/icons-static-svg/icons/qwen-color.svg?raw'
import mistralSvg from '@lobehub/icons-static-svg/icons/mistral-color.svg?raw'
import metaSvg from '@lobehub/icons-static-svg/icons/meta-color.svg?raw'
import codexSvg from '@lobehub/icons-static-svg/icons/codex-color.svg?raw'

export type Brand =
  | 'claude' | 'openai' | 'zhipu' | 'grok' | 'gemini' | 'openrouter'
  | 'ollama' | 'deepseek' | 'qwen' | 'mistral' | 'meta' | 'codex' | 'custom'

const SVGS: Record<Exclude<Brand, 'custom'>, string> = {
  claude: claudeSvg, openai: openaiSvg, zhipu: zhipuSvg, grok: grokSvg,
  gemini: geminiSvg, openrouter: openrouterSvg, ollama: ollamaSvg,
  deepseek: deepseekSvg, qwen: qwenSvg, mistral: mistralSvg, meta: metaSvg,
  codex: codexSvg,
}

// accent used for the rounded tile behind the mark
export const BRAND_META: Record<Brand, { name: string; color: string }> = {
  claude:     { name: 'Anthropic',   color: '#D97757' },
  openai:     { name: 'OpenAI',      color: '#10A37F' },
  zhipu:      { name: 'GLM · Z.ai',  color: '#3859FF' },
  grok:       { name: 'xAI Grok',    color: '#9CA3AF' },
  gemini:     { name: 'Google Gemini', color: '#4285F4' },
  openrouter: { name: 'OpenRouter',  color: '#8B7CF6' },
  ollama:     { name: 'Ollama',      color: '#9CA3AF' },
  deepseek:   { name: 'DeepSeek',    color: '#4D6BFE' },
  qwen:       { name: 'Qwen',        color: '#615CED' },
  mistral:    { name: 'Mistral',     color: '#FA520F' },
  meta:       { name: 'Meta Llama',  color: '#0668E1' },
  codex:      { name: 'Codex',       color: '#10A37F' },
  custom:     { name: 'Custom',      color: '#8B949E' },
}

/** Provider id (model_router catalog) → brand. */
export function brandForProvider(pid?: string | null): Brand {
  switch ((pid || '').toLowerCase()) {
    case 'anthropic': return 'claude'
    case 'openai': return 'openai'
    case 'codex': return 'codex'
    case 'glm': case 'zai': case 'zhipu': return 'zhipu'
    case 'gemini': case 'google': return 'gemini'
    case 'grok': case 'xai': return 'grok'
    case 'openrouter': return 'openrouter'
    case 'deepseek': return 'deepseek'
    case 'ollama': return 'ollama'
    default: return 'custom'
  }
}

/** Model id (e.g. "openrouter:deepseek/deepseek-r1") → the model's own brand. */
export function brandForModel(id?: string | null): Brand {
  const s = (id || '').toLowerCase()
  if (s.startsWith('codex:')) return 'codex'
  if (/codex/.test(s)) return 'codex'
  if (/claude/.test(s)) return 'claude'
  if (/gpt|chatgpt|o[134](-|$|\b)|davinci|openai\//.test(s)) return 'openai'
  if (/glm|zhipu|z-ai|zai\//.test(s)) return 'zhipu'
  if (/gemini|gemma/.test(s)) return 'gemini'
  if (/grok/.test(s)) return 'grok'
  if (/deepseek/.test(s)) return 'deepseek'
  if (/qwen|qwq/.test(s)) return 'qwen'
  if (/mistral|mixtral|pixtral|codestral/.test(s)) return 'mistral'
  if (/llama|meta\//.test(s)) return 'meta'
  if (/ollama/.test(s)) return 'ollama'
  // fall back to the provider prefix ("provider:model")
  return brandForProvider(s.split(':')[0])
}

/** The raw mark, sized by font-size; mono marks inherit the surrounding text color. */
export function BrandMark({ brand, size = 15, className = '' }: { brand: Brand; size?: number; className?: string }) {
  const svg = brand !== 'custom' ? SVGS[brand] : null
  if (!svg) {
    return <span className={`font-bold ${className}`} style={{ fontSize: size * 0.8, color: BRAND_META.custom.color }}>◆</span>
  }
  return (
    <span aria-hidden className={`inline-flex items-center justify-center leading-none ${className}`}
      style={{ fontSize: size }} dangerouslySetInnerHTML={{ __html: svg }} />
  )
}

/** Brand mark in a rounded, brand-tinted tile — the standard logo chip.
 *  Tile uses color-mix so the brand tint stays legible on both dark and light themes
 *  (a flat 12.5% tint vanishes in light mode). */
export default function LlmLogo({ model, provider, size = 15, className = '' }: {
  model?: string | null; provider?: string | null; size?: number; className?: string
}) {
  const brand = model ? brandForModel(model) : brandForProvider(provider)
  const m = BRAND_META[brand]
  return (
    <span title={m.name} className={`flex shrink-0 items-center justify-center rounded-md text-heading ${className}`}
      style={{
        width: size + 9, height: size + 9,
        background: `color-mix(in srgb, ${m.color} 16%, rgb(var(--surface)))`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${m.color} 30%, transparent)`,
      }}>
      <BrandMark brand={brand} size={size} />
    </span>
  )
}
