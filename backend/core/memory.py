"""
Offline agent-memory / RAG layer for TESSR-LOGIC.

Fully local: embeddings via the local Ollama embed model, a SQLite vector store, and
cosine similarity in pure Python. No cloud, no third-party services, no AGPL code.

Two kinds of knowledge:
  - "lesson"  : durable, general engineering principles (hard-won QA lessons) the agents
                can retrieve per task. These are PRINCIPLES the LLM may apply — not output
                templates. The model still writes everything itself.
  - "project" : memory of past successful builds (spec summaries) so the system accumulates
                context over time.

Degrades gracefully: if the embed model isn't available, every call is a safe no-op
(returns [] / False) and the pipeline behaves exactly as before. So it can be added
without risk and "activated" later by pulling the embed model.
"""
import sqlite3
import json
import math
import time
import logging
from pathlib import Path

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

DEFAULT_EMBED_MODEL = "nomic-embed-text"


def _live():
    try:
        from backend.database import SessionLocal
        from backend.repositories.settings_repo import SettingsRepository
        db = SessionLocal()
        try:
            return SettingsRepository(db).get_all() or {}
        finally:
            db.close()
    except Exception:
        return {}


class MemoryStore:
    def __init__(self):
        live = _live()
        self.base_url = (live.get("ollama_base_url") or settings.ollama_base_url).rstrip("/")
        self.embed_model = live.get("ollama_embed_model") or DEFAULT_EMBED_MODEL
        self.enabled = str(live.get("memory_enabled", "true")).lower() != "false"
        try:
            base = Path(settings.workspace_path).parent
        except Exception:
            base = Path(".")
        self.db_path = str(base / "tessr_memory.db")
        self._init_db()

    def _init_db(self):
        try:
            con = sqlite3.connect(self.db_path)
            con.execute(
                """CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT, tags TEXT, text TEXT, embedding TEXT, created_at REAL)"""
            )
            con.commit()
            con.close()
        except Exception as e:
            logger.warning("MemoryStore init failed: %s", e)

    # --- embeddings (local Ollama) ---------------------------------------
    def _embed(self, text: str):
        if not self.enabled or not text:
            return None
        try:
            r = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text[:4000]},
                timeout=30,
            )
            r.raise_for_status()
            emb = r.json().get("embedding")
            return emb if emb else None
        except Exception as e:
            logger.debug("MemoryStore embed unavailable (%s) — memory is a no-op", e)
            return None

    @staticmethod
    def _cosine(a, b) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    # --- public API ------------------------------------------------------
    def add(self, kind: str, text: str, tags: str = "") -> bool:
        emb = self._embed(text)
        if not emb:
            return False
        try:
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO memory_entries(kind,tags,text,embedding,created_at) VALUES(?,?,?,?,?)",
                (kind, tags, text, json.dumps(emb), time.time()),
            )
            con.commit()
            con.close()
            return True
        except Exception as e:
            logger.warning("MemoryStore add failed: %s", e)
            return False

    def search(self, query: str, k: int = 4, kind: str | None = None) -> list[str]:
        """Return up to k most relevant stored texts for the query. [] if unavailable."""
        qemb = self._embed(query)
        if not qemb:
            return []
        try:
            con = sqlite3.connect(self.db_path)
            if kind:
                rows = con.execute("SELECT text, embedding FROM memory_entries WHERE kind=?", (kind,)).fetchall()
            else:
                rows = con.execute("SELECT text, embedding FROM memory_entries").fetchall()
            con.close()
        except Exception as e:
            logger.warning("MemoryStore search failed: %s", e)
            return []
        scored = []
        for text, emb_json in rows:
            try:
                score = self._cosine(qemb, json.loads(emb_json))
            except Exception:
                continue
            if score > 0.25:  # ignore weak matches
                scored.append((score, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:k]]

    def count(self) -> int:
        try:
            con = sqlite3.connect(self.db_path)
            n = con.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
            con.close()
            return n
        except Exception:
            return 0

    def seed_lessons(self) -> int:
        """Populate the durable engineering lessons once (idempotent-ish: only if empty)."""
        if self.count() > 0:
            return 0
        added = 0
        for tags, text in SEED_LESSONS:
            if self.add("lesson", text, tags):
                added += 1
        if added:
            logger.info("MemoryStore: seeded %d lessons", added)
        return added


# Durable, general engineering PRINCIPLES (not output templates). Retrieved per task and
# injected as reference the LLM may apply. These encode the hard-won QA lessons.
SEED_LESSONS = [
    ("web js selectors",
     "Every getElementById/querySelector in the JS must match an element that actually exists "
     "in the HTML you wrote. Guard results with if(el) before using them; attach listeners "
     "inside DOMContentLoaded. Mismatched ids/classes cause null crashes that make the page dead."),
    ("web onclick scope",
     "Inline onclick=\"fn()\" only works if fn is a GLOBAL (window) function. Functions defined "
     "inside DOMContentLoaded are local and won't resolve. Prefer addEventListener, or expose "
     "handlers on window. Keep id/class names identical between the HTML and the JS."),
    ("web static-first",
     "Write the initial/seed content as real HTML elements. Use JavaScript only to ENHANCE "
     "(add/delete/edit/persist). If the JS throws, the page must still show its content — never "
     "render the whole page from an empty <div id='app'></div>."),
    ("web multipage",
     "A multi-page site shares ONE navbar linking every page with the active page highlighted, "
     "ONE styles.css, and ONE app.js. Persist per-page state in localStorage keyed by page. "
     "Every page must have its own complete body content."),
    ("web shared-script page-safe",
     "A single shared app.js runs on EVERY page, but each page has a different DOM. Guard every "
     "element lookup before use: `const el = document.getElementById('x'); if (!el) return;`. "
     "Page-specific code (e.g. a contact form handler) must be wrapped in an existence check, or "
     "it throws null errors on pages that lack that element. The HTML <script src> and the actual "
     "JS file must share the exact same filename."),
    ("web modern 2026 design",
     "Modern sites (Linear/Vercel/Stripe-tier) are RICH, not just clean — and it all comes from "
     "inline SVG + CSS (no external assets, stays offline). Structure for it: a big bold display "
     "hero with a short value line and CTA; a bento/auto-fit GRID of feature cards each with an "
     "INLINE SVG icon; sections with visual variety (alternating backgrounds, asymmetry) instead of "
     "identical stacked text blocks; glassmorphism cards and an animated/gradient hero background; "
     "scroll-reveal fade-in animations; hover micro-interactions. Use inline <svg> for all icons "
     "(never icon fonts or image URLs). Oversized headings via clamp(). This is the difference "
     "between a 1998 template and a current SaaS landing page."),
    ("web design system",
     "Professional CSS: system font stack, a clear type and spacing scale, a gradient header, "
     "content on ELEVATED surfaces (cards lighter than the page background) with soft shadows and "
     "rounded corners, smooth hover transitions, a max-width centered container, a responsive grid, "
     "and a persisted light/dark theme. The page body and its sections must not be the same flat color."),
    ("web localstorage crud",
     "For add/edit/delete/reorder with persistence: keep an array in localStorage, render the list "
     "from it, and after every change save then re-render. Validate inputs (no empty title), and "
     "give visible feedback. Guard against an empty list with a friendly empty state."),
    ("python api",
     "For a FastAPI service: requirements.txt must list every third-party import; the entry point "
     "must be runnable (uvicorn app:app); route handlers return real data and proper status codes; "
     "use Pydantic models for request/response; guard inputs."),
    ("offline no-telemetry",
     "Generated sites must be fully self-contained: no CDN fonts/scripts, no analytics, no external "
     "calls. This keeps builds offline and avoids runtime failures when a CDN is unreachable."),
]


_INSTANCE = None


def get_memory() -> MemoryStore:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MemoryStore()
        try:
            _INSTANCE.seed_lessons()
        except Exception:
            pass
    return _INSTANCE
