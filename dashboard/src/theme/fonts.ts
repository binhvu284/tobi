/* ── Theme v2.1 self-hosted fonts (queue #13) ──────────────────────────────────
   Registers the branded @font-face families used by the theme system. These are
   just declarations — a browser only downloads a face when the ACTIVE theme's
   font stack (from themeTokens.ts → --font-ui / --font-display) actually uses it,
   and @fontsource splits each family by unicode-range so only the latin woff2 is
   fetched. Themes on the system stack (dark/light/notion/chatgpt) cost 0 bytes.
   Replaces Office's runtime Google-Fonts CDN <link> for Rajdhani (now bundled).
   Imported once from src/main.tsx. All faces use font-display: swap. */

// Static display faces — latin subset, only the weights the UI uses.
import '@fontsource/rajdhani/latin-500.css'        // gaming display + Office HUD
import '@fontsource/rajdhani/latin-600.css'
import '@fontsource/rajdhani/latin-700.css'
import '@fontsource/chakra-petch/latin-500.css'    // jarvis display
import '@fontsource/chakra-petch/latin-600.css'
import '@fontsource/zen-maru-gothic/latin-500.css' // japanese display
import '@fontsource/zen-maru-gothic/latin-700.css'
import '@fontsource/zcool-xiaowei/latin-400.css'   // chinese display (weight 400 only)

// Variable faces — the weight axis; each @font-face is unicode-range-gated,
// so only the latin woff2 downloads.
import '@fontsource-variable/geist/wght.css'        // vercel UI
import '@fontsource-variable/inter/wght.css'        // linear UI
import '@fontsource-variable/lora/wght.css'         // claude serif display
