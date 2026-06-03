# Knowledge Library — cross-domain grounding for the agents

Vetted, reusable **recipes** the agents retrieve *before* they generate, so they build with
knowledge of what good looks like instead of inventing from a cold base model. Fully offline.
Spans every kind of build — not just UI.

```
library/
  ui/          hero/bento/glass, responsive navbar, …      (look & layout)
  frontend/    state, routing, forms (add as needed)
  backend/     fastapi-crud, …                              (APIs/services)
  database/    relational-schema, …                         (data layer)
  auth/        session-jwt, …                               (authn/authz/security)
  ai-agents/   tool-loop, …                                 (agent & swarm patterns)
  data/        sensor-diagnostics, …                        (telemetry/diagnostics/monitoring)
  mobile/      responsive-pwa, …                            (mobile/offline/installable)
  cli/         argparse-tool, …                             (command-line tools)
```

## Entry schema (one JSON file per recipe)
```jsonc
{
  "id": "unique-id",
  "domain": "ui|frontend|backend|database|auth|ai-agents|data|mobile|cli|…",
  "title": "Short human title",
  "tags": ["keywords", "the", "retriever", "matches", "on"],
  "stack": ["html","css"],                  // technologies it applies to
  "when": "One line: when to use this",
  "principle": "What to do and why (the transferable lesson)",
  "exemplar": ["line 1", "line 2", "…"],    // string OR array of lines — code to ADAPT, not copy
  "pitfalls": "Common mistakes to avoid"
}
```

## How it's used
`backend/core/library.py` loads every entry and exposes:
- `search(query, domains, k)` — deterministic tag/keyword retrieval (offline, no embed model).
- `exemplars_block(query, domains, k)` — formatted REFERENCE EXEMPLARS block injected into agent prompts.

The Architect/Coder/UI-Designer call this per build, scoped to the build's domains
(`STACK_DOMAINS` maps stack_family → domains). Recipes are references to **adapt**, never fixed
templates — the model still writes everything.

## Extending
Drop a new `library/<domain>/<id>.json` file in. It's picked up automatically (call
`library.reload()` or restart). The Connectors tab can also auto-generate recipes by extracting
patterns from GitHub repos.
