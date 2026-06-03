# TESSR-LOGIC Brand Kit (test fixture)

A self-contained, **fully offline** brand kit you can pull from when testing TESSR-LOGIC
builds — so generated sites get a real logo, a consistent color/UI scheme, inline-SVG icons,
a hero illustration, and on-brand copy, without any external assets.

Everything here is **inline SVG, JSON, and text** — no raster images, no CDN, no fonts to
download. It drops straight into an offline build.

## Contents
```
tessr-logic/
  brand.json            Design tokens: colors, typography, spacing, radius, shadows, voice, constraints
  logo/
    tessr-logo.svg      Full wordmark (gradient mark + "TESSR-LOGIC")
    tessr-mark.svg      Icon-only mark (square)
    favicon.svg         32x32 favicon
  icons/                24x24 inline icons, stroke=currentColor (style via CSS color)
    offline.svg  security.svg  pipeline.svg  speed.svg  agents.svg  lock.svg
  images/
    hero.svg            800x400 hero illustration (already size-constrained)
  content/
    copy.md             On-brand taglines, value props, agent blurbs, CTAs
```

## How to use it

### A) In a build prompt (manual, works today)
Tell the pipeline to use the kit and paste the key tokens. Example addition to your prompt:

> Use this exact brand: colors — bg #0b0e1a, surface #141a2e, primary #6366f1, accent #8b5cf6,
> accent2 #22d3ee, text #e5e7eb; font system-ui; gradient hero #6366f1→#8b5cf6→#22d3ee.
> Logo wordmark "TESSR-LOGIC" with a gradient square mark. Use inline SVG icons (offline, shield,
> pipeline, bolt, agents, lock). Tagline: "Describe it. TESSR builds it. Fully offline." Every
> inline svg must be sized (svg{max-width:100%;height:auto}; icons ~24px).

### B) Copy assets into the build (recommended for real brand fidelity)
After a build's `src/` exists, copy the kit's assets in and reference them:
```
cp assets/brand-kits/tessr-logic/logo/*.svg   <build>/src/
cp assets/brand-kits/tessr-logic/icons/*.svg  <build>/src/icons/
cp assets/brand-kits/tessr-logic/images/*.svg <build>/src/images/
```
Then in HTML: `<img src="logo/tessr-logo.svg" alt="TESSR-LOGIC" width="200">` (already sized).

### C) Future wiring (pipeline feature)
The Architect/Coder/UI-Designer can be given `brand.json` as context so every TESSR build is
on-brand automatically. The tokens map 1:1 to the UI Designer's variables (`:root` colors,
type scale, spacing, radius, shadows).

## Design rules baked into the kit
- **Offline & self-contained** — inline SVG only, no external assets, no CDN, no analytics.
- **Icons are inline SVG, never emoji.** Stroke uses `currentColor` so CSS `color:` styles them.
- **Every SVG is sized** (the hero has `max-width:100%;height:auto`; icons are 24x24) — prevents
  the "giant unsized SVG fills the page" failure.
- **Dark, indigo/violet, security-forward** aesthetic matching the TESSR-LOGIC identity.
