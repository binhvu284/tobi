# Theme v2 System Upgrade Plan

> Queue status: In progress — v1 implemented per this plan (see QUEUE.md #13 for the build/verification notes).
> Scope: Planning only. This document is for a worker agent to implement later.
> Do not implement Supabase or Vercel changes for this task.

## 1. Summary

Upgrade the existing MC Theme system from simple color-variable swaps into a centralized Theme v2 token system that controls visual identity across core UI: shell, settings, chat, cards, forms, buttons, nav, shared dashboard components, and common data display surfaces.

Owner decisions already collected:

- Product feel: premium SaaS.
- First implementation scope: core UI, not every page.
- Priority: maintainable system first.
- Primary baseline: Dark Default.
- Main current weakness: themes feel like recolors.
- Must preserve: instant theme switching.
- Customization: every theme, guided controls, remembered per theme.
- Initial active themes: Dark Default, Light Default, Gaming, High Tech, Japanese, Chinese, Jarvis OS.
- Removed active themes: Midnight Neon, High Contrast, Warm, Scientific.
- Migration: map removed themes to closest surviving theme.
- Brand-inspired proposals only: subtle Productivity + Dev set.
- Icons: existing `lucide-react` icons only, selector-only.
- Import placeholder: quiet disabled Theme v3 UI in Theme Settings.
- Persistence: frontend-first unless current code proves backend storage already exists.
- Dependencies: small dependency allowed only if clearly useful, but avoid by default.
- Fonts: system font stacks only.
- Verification: build plus focused manual UI checks.
- Docs: update related docs only if required.
- Queue status: Queued.

## 2. Current System Findings

Current implementation:

- Theme state lives in `dashboard/src/context/ThemeProvider.tsx`.
- Current theme IDs: `dark`, `light`, `midnight`, `contrast`, `warm`, `gaming`, `hightech`, `scientific`.
- Current persistence key: `localStorage["tobi.prefs"]`.
- Current preference shape: `{ theme, fontScale, density, sound }`.
- Current `ThemeProvider` writes:
  - `<html data-theme="...">`
  - `<html data-density="...">`
  - `--font-scale`
  - temporary `data-theme-anim` for crossfade.
- Theme CSS variables currently live in `dashboard/src/index.css`.
- Settings theme selector lives in `dashboard/src/pages/Settings.tsx`.
- Quick theme switch exists in `dashboard/src/components/AppShell.tsx`.
- Command palette exposes theme switching in `dashboard/src/components/CommandPalette.tsx`.
- Backend `owner_settings` currently stores timezone and vault-related values; theme appears frontend-only.
- Office intentionally pins some wrappers to `data-theme="dark"` and must not be forced into full Theme v2 in this pass.

## 3. Theme v2 Architecture Plan

Build a centralized frontend token architecture:

1. Create a Theme v2 model in `dashboard/src/context/ThemeProvider.tsx` or a nearby module such as `dashboard/src/context/themeTokens.ts`.
2. Keep stable theme IDs separate from display labels.
3. Replace flat `THEMES` plus `THEME_META` with richer theme definitions:
   - `id`
   - `label`
   - `description`
   - `icon`
   - `mode`
   - `tokens`
   - `defaults`
   - `customizable`
   - `migrationFrom`
4. Keep instant switching by continuing to write CSS custom properties to `<html>`.
5. Do not hardcode theme conditionals across random components.
6. Use CSS variables for full theme identity, not component-specific one-off styles.
7. Keep Tailwind compatibility by preserving existing color triplet tokens used by classes like `bg-accent/10`.
8. Keep Theme v2 frontend-first. Do not introduce backend persistence unless another current file proves it is already required.

## 4. Theme Token Schema Proposal

Use Theme v2 token groups like this:

```ts
type ThemeId =
  | 'dark'
  | 'light'
  | 'gaming'
  | 'hightech'
  | 'japanese'
  | 'chinese'
  | 'jarvis'

type ThemeV2Tokens = {
  color: {
    scheme: 'dark' | 'light'
    bg: string
    surface: string
    panel: string
    border: string
    muted: string
    text: string
    heading: string
    accent: string
    success: string
    warning: string
    danger: string
    purple: string
    accent2?: string
    glow?: string
  }
  typography: {
    ui: string
    mono: string
    scale: number
    tracking: 'normal' | 'wide' | 'tight'
    weight: 'regular' | 'medium' | 'bold'
  }
  shape: {
    radius: 'sharp' | 'soft' | 'rounded'
    cardRadius: string
    buttonRadius: string
    inputRadius: string
  }
  density: {
    default: 'compact' | 'comfortable' | 'spacious'
    spacingScale: number
  }
  elevation: {
    shadowDepth: 'flat' | 'soft' | 'deep' | 'glow'
    cardShadow: string
    popoverShadow: string
  }
  component: {
    buttonStyle: 'solid' | 'ghost' | 'outline' | 'glass'
    cardStyle: 'flat' | 'outlined' | 'glass' | 'layered'
    inputStyle: 'outlined' | 'filled' | 'underlined'
    navStyle: 'rail' | 'panel' | 'floating'
  }
  background: {
    style: 'plain' | 'grid' | 'gradient' | 'paper' | 'hud'
    overlayOpacity: number
  }
  dataViz: {
    palette: string[]
    gridOpacity: number
    glowCharts: boolean
  }
  motion: {
    intensity: 'quiet' | 'standard' | 'expressive'
  }
}
```

Expose these as CSS vars:

- Existing required vars: `--bg`, `--surface`, `--panel`, `--border`, `--muted`, `--text`, `--heading`, `--accent`, `--success`, `--warning`, `--danger`, `--purple`, `--font-scale`.
- New vars: `--radius-card`, `--radius-button`, `--radius-input`, `--shadow-card`, `--shadow-popover`, `--spacing-scale`, `--tracking-ui`, `--bg-overlay-opacity`, `--chart-1` through `--chart-6`, `--theme-glow`, `--theme-accent-2`.

## 5. Migration Plan

Implement safe migration inside the `ThemeProvider` load path.

Required migration behavior:

- Read `localStorage["tobi.prefs"]`.
- If missing or invalid, use Theme v2 defaults.
- If `theme` is removed, map to closest surviving theme:
  - `midnight` -> `gaming`
  - `contrast` -> `dark`
  - `warm` -> `dark`
  - `scientific` -> `light`
- Preserve `fontScale`, `density`, and `sound`.
- Add new `customByTheme` object while keeping old preferences compatible.
- Write upgraded shape back to `tobi.prefs`.
- Never crash if localStorage contains malformed JSON.
- If unknown theme ID is found, fallback to `dark`.

Suggested new preference shape:

```ts
type ThemePrefsV2 = {
  version: 2
  theme: ThemeId
  fontScale: number
  density: 'compact' | 'comfortable' | 'spacious'
  sound: boolean
  customByTheme: Record<ThemeId, Partial<ThemeCustomization>>
}
```

## 6. Themes To Keep, Remove, Upgrade, And Add

Keep and rename:

- `dark` -> Dark Default
- `light` -> Light Default

Upgrade:

- `gaming` -> Gaming
  - Esports neon.
  - Dark surface, sharper HUD accents, lime success, purple/pink secondary.
  - More energetic button/card treatment through tokens.
- `hightech` -> High Tech
  - Clean engineering dashboard.
  - Cool blues, teal accents, precise borders, restrained glow, technical spacing.

Remove from active availability:

- `midnight` / Midnight Neon
- `contrast` / High Contrast
- `warm` / Warm
- `scientific` / Scientific

Add:

- `japanese` / Japanese
  - Light white base, soft pink/sakura accent, calm minimal cards, soft radius.
- `chinese` / Chinese
  - Red and gold premium SaaS feel, festive but professional, stronger accent hierarchy.
- `jarvis` / Jarvis OS
  - High-tech blue AI OS, dark dashboard, glowing but controlled, analytics-focused.

Do not add the two extra ideas yet. Propose only.

## 7. Brand-Inspired Theme Proposals

These are proposals only. Do not implement them until the owner confirms.

1. Notion Calm
   - Inspired by Notion.
   - Off-white, black text, minimal borders, low-shadow cards.
   - System sans, clean typography.
   - Simple square-ish components.
   - Icon strategy: document/page symbolic icon, not Notion logo.
   - Fit: good for founder productivity and planning views.

2. Linear Flow
   - Inspired by Linear.
   - Dark refined surfaces, violet/blue accent, crisp cards, smooth issue-tracker feel.
   - Slightly denser typography and sharper actions.
   - Icon strategy: diagonal/command symbolic icon, not Linear logo.
   - Fit: strong match for project/task/product-management workflows.

3. GitHub Dev
   - Inspired by GitHub.
   - Dark and light dev-friendly palettes, clear borders, code-friendly contrast.
   - System UI plus mono emphasis.
   - Icon strategy: code branch/git symbolic icon, not GitHub logo.
   - Fit: good for technical agent workflows, MCP, logs, and code-adjacent pages.

4. VS Code Terminal
   - Inspired by VS Code.
   - Dark editor-like surfaces, blue activity accents, compact panels.
   - Mono-friendly data zones.
   - Icon strategy: terminal/code symbolic icon, not VS Code logo.
   - Fit: future TOBI CLI and developer modes.

5. Vercel Mono
   - Inspired by Vercel.
   - Black/white, high whitespace, sharp components, minimal shadows.
   - Typography: clean system sans, tighter heading hierarchy.
   - Icon strategy: triangle/launch symbolic icon, not Vercel logo.
   - Fit: clean SaaS control room with strong premium feel.

## 8. Two Extra Theme Ideas

Suggest only. Do not implement yet.

1. Aurora Studio
   - Creative dark theme with teal, violet, and soft aurora gradients.
   - Best for users who want expressive but still polished AI workspace energy.

2. Solar Forge
   - Warm creative theme with ember, copper, and deep charcoal.
   - Best for users who want a powerful creative-builder vibe without using the removed old Warm theme.

## 9. UI/UX Plan For Theme Selector And Customization

Theme selector:

- Upgrade Settings Theme section into a clear Theme v2 panel.
- Keep quick switch in AppShell but make it simpler than Settings.
- Show each theme as a card with:
  - icon
  - display name
  - short description
  - real swatch using `data-theme`
  - active check state
- Use existing `lucide-react` icons:
  - Dark Default: `Moon`
  - Light Default: `Sun`
  - Gaming: `Gamepad2`
  - High Tech: `Cpu`
  - Japanese: `Flower2` or closest available flower icon.
  - Chinese: `Landmark`, `Sparkles`, or symbolic fallback if no lantern/fan exists.
  - Jarvis OS: `Bot`, `Cpu`, or `LayoutDashboard`.

Customization UI:

- Add guided controls under the theme grid.
- Controls should be presets, not freeform chaos:
  - Accent color
  - Radius: sharp / soft / rounded
  - Density: compact / comfortable / spacious
  - Typography preset: default / technical / calm
  - Card style: flat / outlined / glass / layered
  - Button style: solid / ghost / outline / glass
  - Background style: plain / grid / gradient / paper / HUD
  - Animation intensity: quiet / standard / expressive
  - Shadow depth: flat / soft / deep / glow
  - Contrast: standard / boosted
- Store customization per theme.
- Add reset controls:
  - Reset current theme customization.
  - Reset all appearance preferences.

## 10. Placeholder Plan For Theme v3 Import Function

Add a quiet disabled control in Theme Settings.

Copy:

`Import custom theme from file - Coming in Theme v3`

Rules:

- No file input.
- No parser.
- No upload.
- No hidden side effects.
- Do not mention specific file types yet.

## 11. Implementation Task Breakdown

Phase 1: Theme model and migration

- Refactor `ThemeProvider` to support Theme v2 definitions and migration.
- Preserve `useTheme()` compatibility where possible.
- Add removed-theme fallback logic.
- Keep localStorage key as `tobi.prefs`.
- Preserve instant `<html>` CSS-var updates.

Phase 2: Token expansion

- Move theme definitions into a centralized TS module or keep cleanly in `ThemeProvider`.
- Add new active themes.
- Remove removed themes from active selector arrays.
- Preserve CSS fallback in `index.css`.
- Add new CSS vars for shape, shadow, density, background, data visualization, and component feel.
- Add utility classes only where needed for shared patterns.

Phase 3: Settings UI

- Upgrade `Settings.tsx` theme section.
- Add selector icons and richer cards.
- Add guided customization controls.
- Add Theme v3 import placeholder.
- Preserve existing Density, Motion, Text size, Sound, Timezone behavior.
- Avoid overloading Settings with too much text.

Phase 4: Quick switch and command palette

- Update `AppShell.tsx` quick theme switch to use active Theme v2 list and clean names.
- Update `CommandPalette.tsx` theme commands so removed themes no longer appear.
- Ensure unknown/removed stored values do not break command palette rendering.

Phase 5: Core UI token adoption

- Apply new vars to shared surfaces:
  - shell/header/sidebar
  - buttons
  - cards/panels
  - inputs/selects
  - popovers/dropdowns
  - charts/data surfaces where already theme-aware
- Do not rewrite every page.
- Do not touch Office's pinned dark scene except ensuring root accent still works.

Phase 6: Docs and queue

- Use this plan file as the implementation source of truth.
- Keep `QUEUE.md` status as `Queued` until implementation starts.
- Mention conflict risk with AppShell/Settings/ThemeProvider work in the queue notes.

## 12. Testing Plan

Worker must run:

- `npm.cmd run build` from `tobi/dashboard`.
- If PowerShell blocks `npm`, use `npm.cmd`, not `npm.ps1`.

Manual checks:

1. Start local dashboard.
2. Open Settings.
3. Switch every active theme.
4. Confirm removed themes do not appear.
5. Temporarily set localStorage `tobi.prefs` to each removed theme and reload:
   - `midnight` migrates to Gaming.
   - `contrast` migrates to Dark Default.
   - `warm` migrates to Dark Default.
   - `scientific` migrates to Light Default.
6. Confirm malformed `tobi.prefs` does not crash app.
7. Confirm quick theme switch still works.
8. Confirm command palette theme commands show only active themes.
9. Confirm density, text size, motion, sound still work.
10. Confirm Theme v3 import UI is disabled and does not open file picker.
11. Confirm core UI changes are visible in shell, settings, chat, common cards/forms/buttons.
12. Confirm Office still renders its intended dark cyberpunk scene.

Suggested unit/static checks if easy:

- Add small pure functions for migration and test them if frontend test infrastructure exists.
- If no frontend tests exist, keep migration logic simple and manually verifiable.

## 13. Rollback Plan

If Theme v2 causes visual or runtime problems:

1. Restore previous `ThemeProvider.tsx`.
2. Restore old theme CSS blocks in `index.css`.
3. Restore old Settings theme selector.
4. Keep localStorage migration defensive so old/new preference shapes do not crash.
5. Since persistence remains frontend localStorage-only, rollback does not require backend/database migration.
6. If needed, users can clear `localStorage["tobi.prefs"]` to return to Dark Default.

## 14. Files Likely To Be Changed

High-confidence files:

- `dashboard/src/context/ThemeProvider.tsx`
- `dashboard/src/index.css`
- `dashboard/src/pages/Settings.tsx`
- `dashboard/src/components/AppShell.tsx`
- `dashboard/src/components/CommandPalette.tsx`

Possible files:

- `dashboard/src/pages/Storage.tsx` if chart palette extraction needs new vars.
- `dashboard/src/components/PageLoader.tsx` if loader should respect new theme personality.
- `dashboard/src/components/motion/AmbientField.tsx` if background style tokens need better support.
- `dashboard/src/office/theme.ts` only if root accent bridging breaks.

Do not touch:

- Supabase or Vercel.
- Backend schema unless repo inspection proves theme is already backend-persisted.
- Office Phaser scene internals unless required for root accent compatibility.

## 15. Risks And Assumptions

Risks:

- Parallel work on AppShell, Settings, Chat UI, or theme provider may conflict.
- Existing generated `dist` assets may be stale after implementation; worker should rebuild only when asked or if project convention requires checking build output.
- Strong theme personality can become messy if workers hardcode per-theme component branches.
- Cultural themes must stay tasteful and SaaS-appropriate.
- Brand-inspired themes must avoid copied logos, proprietary assets, or exact UI cloning.
- Existing Office dark pinning is intentional; forcing it into all themes may regress the game-like office.

Assumptions:

- Theme v2 remains frontend-first.
- `tobi.prefs` remains the browser persistence key.
- No new font files or external font loading.
- Existing `lucide-react` icons are enough.
- Small dependencies are allowed, but none are required for the initial plan.
- Related docs are updated only if directly required during implementation.

## 16. Final Queued Task Plan

Queue row added to `QUEUE.md`:

```md
| 13 | **Theme v2 System Upgrade** - expressive token-based MC theme architecture | 🟡 Queued | [THEME_V2_SYSTEM_UPGRADE_PLAN.md](THEME_V2_SYSTEM_UPGRADE_PLAN.md) | Upgrade MC Theme from simple recolors into a centralized Theme v2 system controlling color, typography, radius, shadows, density, component shape, background, chart palette, motion intensity, icons, and product vibe across core UI. Keeps Dark/Light defaults, upgrades Gaming and High Tech, adds Japanese, Chinese, and Jarvis OS, removes Midnight Neon/High Contrast/Warm/Scientific from active availability with safe localStorage migration. Adds per-theme guided customization, selector icons via existing `lucide-react`, and a quiet disabled Theme v3 import placeholder. Frontend-first, no Supabase/Vercel, no implementation until this queued plan is picked up. High conflict risk with AppShell/Settings/ThemeProvider/UI-shell work; avoid implementing in parallel with other theme/header/settings tasks. |
```

Placement:

- The row should remain in the queued section near Project v2 and TOBI CLI.
- Do not mark it in progress until a worker agent starts implementation.
