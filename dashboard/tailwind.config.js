/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'rgb(var(--bg) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        strip: 'rgb(var(--strip) / <alpha-value>)',
        panel: 'rgb(var(--panel) / <alpha-value>)',
        border: 'rgb(var(--border) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        text: 'rgb(var(--text) / <alpha-value>)',
        heading: 'rgb(var(--heading) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        success: 'rgb(var(--success) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        danger: 'rgb(var(--danger) / <alpha-value>)',
        purple: 'rgb(var(--purple) / <alpha-value>)',
        accent2: 'rgb(var(--theme-accent-2, var(--purple)) / <alpha-value>)',
        // Theme v2.1 (#13): scheme-aware wash tint (white on dark, ink on light)
        // so hover/chip overlays read correctly on every theme.
        overlay: 'rgb(var(--overlay, 255 255 255) / <alpha-value>)',
      },
      /* Theme v2 (#13): md/lg/xl/2xl track the theme's shape tokens so radius
         personality (sharp/soft/rounded) applies app-wide without page rewrites.
         Fallbacks equal Tailwind's defaults; rounded-full/sm stay untouched. */
      borderRadius: {
        md: 'var(--radius-input, 0.375rem)',
        lg: 'var(--radius-button, 0.5rem)',
        xl: 'var(--radius-card, 0.75rem)',
        '2xl': 'calc(var(--radius-card, 0.75rem) + 4px)',
        card: 'var(--radius-card, 0.75rem)',
        btn: 'var(--radius-button, 0.5rem)',
        input: 'var(--radius-input, 0.375rem)',
      },
      boxShadow: {
        card: 'var(--shadow-card, 0 1px 3px rgb(0 0 0 / 0.2))',
        popover: 'var(--shadow-popover, 0 16px 40px -12px rgb(0 0 0 / 0.4))',
        '2xl': 'var(--shadow-popover, 0 25px 50px -12px rgb(0 0 0 / 0.25))',
      },
      /* Theme v2.1 (#13): UI + display fonts follow the active theme's stack
         (self-hosted via @fontsource in src/theme/fonts.ts). Fallbacks = the
         system stack, so themes that opt out (dark/light/notion/chatgpt) are
         unchanged. `font-display` utility → headings/marquee type. */
      fontFamily: {
        sans: ['var(--font-ui, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif)'],
        display: ['var(--font-display, var(--font-ui, ui-sans-serif, system-ui, sans-serif))'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      animation: {
        'idle': 'idle 2.5s ease-in-out infinite',
        'working': 'working 0.6s ease-in-out infinite',
        'blink': 'blink 1.2s ease-in-out infinite',
        'flow': 'flow 2s linear infinite',
        'glow': 'glow 2s ease-in-out infinite',
      },
      keyframes: {
        idle: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-5px)' },
        },
        working: {
          '0%, 100%': { transform: 'translateY(0px) rotate(-3deg)' },
          '50%': { transform: 'translateY(-3px) rotate(3deg)' },
        },
        blink: {
          '0%, 90%, 100%': { opacity: '1' },
          '95%': { opacity: '0' },
        },
        flow: {
          '0%': { strokeDashoffset: '20' },
          '100%': { strokeDashoffset: '0' },
        },
        glow: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(88,166,255,0.3)' },
          '50%': { boxShadow: '0 0 20px rgba(88,166,255,0.7)' },
        },
      },
    },
  },
  plugins: [],
}
