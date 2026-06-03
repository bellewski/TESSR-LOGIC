# Brand Kits — test fixtures

Self-contained, **offline** brand kits to choose from when testing TESSR-LOGIC builds.
Each kit has a `brand.json` (colors, typography, voice, taglines, aesthetic, constraints)
and a sized `logo.svg`. Point a build prompt at one to get a consistent, distinct look —
useful for testing the pipeline across very different design languages.

| Kit | Industry | Vibe | Palette |
|-----|----------|------|---------|
| `tessr-logic`        | AI build pipeline (us) | dark, security-forward | indigo / violet / cyan |
| `nebula-fintech`     | Fintech / payments     | clean, trust, data-forward | navy / teal |
| `terra-organic`      | Organic food / eco     | warm, wholesome, serif | cream / green |
| `pulse-health`       | Healthcare / telemed   | calm, clinical, accessible | white / blue |
| `forge-devtools`     | Dev tools / CLI        | dark terminal, monospace | black / neon-green |
| `lumen-creative`     | Creative agency        | maximalist, bold, gradients | pink / purple / yellow |
| `atlas-logistics`    | Logistics / B2B        | industrial, operational | slate / safety-orange |
| `bloom-beauty`       | Beauty / skincare      | luxe minimal, elegant serif | blush / cream |
| `quantum-ai`         | AI / ML SaaS           | futuristic, glassmorphism | deep-space purple / cyan |
| `summit-realestate`  | Luxury real estate     | premium, refined serif | charcoal / gold |
| `cobalt-gov`         | Government / civic     | official, accessible (508/AA) | gov blue / red |

## Use in a build
Either paste the kit's tokens into your prompt, or tell the pipeline which kit to use, e.g.:

> Use the `forge-devtools` brand kit: dark terminal theme, JetBrains Mono, bg #0d1117,
> neon-green #39d353 accent, code-block hero, monospace everywhere. Inline SVG icons only.

Each `brand.json` maps 1:1 to the UI Designer's `:root` variables (colors, type scale,
spacing, radius). All assets are inline SVG / JSON / text — no external assets, no CDN —
so they drop straight into an offline build. Every SVG is sized (no giant-blob bug).

> Future: a `--brand-kit <name>` build option can auto-inject the chosen kit's tokens +
> logo so every build is on-brand without re-describing it.
