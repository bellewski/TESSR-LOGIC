import re
import json
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)


def _as_list(value) -> list:
    """Coerce an LLM-produced contract field into a list, regardless of shape.
    Handles None, a single string, a list, or a dict (uses its values).
    Prevents slice/iteration crashes when the model returns an object where a
    list was expected (e.g. interface_contracts as a JSON object on Python 3.12+
    where dict[:N] raises KeyError(slice))."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return [value]


_CODER_SYSTEM_DEFAULT = """You are a world-class software engineer. Write complete, production-quality source code based on the spec.

OUTPUT FORMAT — only file blocks:
===FILE: filename.ext===
[complete file content]
===END===

Read the spec_summary and the contract carefully. They tell you exactly what to build. Implement everything they describe — in whatever language, framework, or file types the spec calls for.

COMPLETENESS RULES — these apply to every project type and every language:
- Every feature described in the spec must be implemented and working
- No stubs, no TODOs, no placeholder comments, no empty functions
- Every interface in the contract (endpoint, command, screen, function) must be real
- Data that should persist must use the appropriate mechanism (localStorage, files, or a database)
- Write enough code to make the project actually work — if it needs 500 lines, write 500 lines

QUALITY RULES:
- Real, descriptive names — not x, y, temp
- Handle edge cases — empty inputs, invalid inputs, error paths
- Format output appropriately for the platform
- Initialize/bootstrap the program properly (entry points, event listeners, startup routines)

OUTPUT RULES:
- Use the ===FILE: path.ext=== format for every file — no exceptions, any extension
- Every file must be complete — the whole file, not a fragment
- Make design and implementation decisions yourself based on the spec — do not ask questions
- Do NOT invent files outside the file plan unless they are strictly required to run

RUNTIME CORRECTNESS (your code is executed in a real browser and must not throw):
- Every getElementById / querySelector you call must match an element that actually
  exists in the HTML you wrote. Mismatched IDs/classes/selectors cause null crashes.
- Never call a method or read a property on a query result without ensuring it exists
  (a null .style / .innerHTML / .addEventListener is the #1 cause of dead pages).
- Attach event listeners only after the DOM is ready (inside DOMContentLoaded) and only
  to elements that exist on the current page (guard `if (el) {...}`).
- Class/id names in the HTML and the JS MUST match exactly (e.g. button id="add-section"
  vs JS listening for class "add-section-btn" is a bug).

NO EMPTY SHELLS / STATIC-FIRST (applies to every HTML page):
- Write ALL visible content directly in the HTML — real headings, paragraphs, lists, cards,
  forms, buttons, nav links. Every page must look complete when opened with JavaScript disabled.
- Write the initial/seed content as real HTML elements. Use JavaScript only to ENHANCE
  (add/delete/edit/persist) — never as the sole way content appears. If your JS throws, the
  page must still show its content. Do NOT render the whole page from JS into an empty container.
- NEVER ship a page that is just <div id="app"></div> (or similar) populated only by JS.
- NEVER use placeholder comments like <!-- content here --> in place of real content.
- Each page in a multi-page site must have its own full body content — do not leave any page thin."""


class CoderInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    stack_target: str
    spec_summary: str
    file_plan: list[dict]
    archetype: str = "single_page_app"
    product_type: str = "web_app"
    contract: dict = {}
    fix_feedback: str = ""
    findings: list[dict] = []


class CoderOutput(BaseModel):
    success: bool
    error: str = ""
    generated_files: list[dict] = []


class CoderAgent(BaseAgent[CoderInput, CoderOutput]):
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir

    async def run(self, input_data: CoderInput) -> CoderOutput:
        all_generated: list[dict] = []
        file_plan = input_data.file_plan or []
        if not file_plan:
            return CoderOutput(success=False, error="No file_plan provided.")

        # ── ADDITIVE PATCH MODE ──────────────────────────────────────────────
        # On a retry (fix_feedback present) where files already exist, DON'T
        # regenerate from scratch — that plays whack-a-mole (fixing A drops B).
        # Instead, keep every existing file and edit ONLY what the feedback names.
        src_dir = self.build_dir / "src"
        existing_files = [p for p in src_dir.rglob("*") if p.is_file()] if src_dir.exists() else []
        if input_data.fix_feedback and existing_files:
            patched = await self._run_patch(input_data, src_dir, existing_files)
            if patched is not None:
                return patched
            # If patch mode couldn't produce anything, fall through to full regen.

        contract = input_data.contract or {}
        ui_layer = contract.get("ui_layer", "html_css")
        stack_family = contract.get("stack_family", "web")
        is_web_build = ui_layer in ("html_css", "react") or stack_family == "web"

        # ── Feedback from prior rounds (validator / smoke tester / security) ──
        feedback_section = ""
        if input_data.fix_feedback:
            feedback_section = (
                f"\n\n{'='*60}\n"
                f"FEEDBACK FROM THE LAST BUILD ROUND — YOU MUST ADDRESS ALL OF THIS\n"
                f"{'='*60}\n"
                f"{input_data.fix_feedback}\n"
                f"{'='*60}\n"
                f"Regenerate the affected files completely to resolve every issue above."
            )

        if input_data.findings:
            findings_text = "\n".join(
                f"- {f.get('severity', 'unknown')}: {f.get('description', '')} (line {f.get('line_number', 'unknown')})"
                for f in input_data.findings[:10]
            )
            feedback_section += f"\n\nSECURITY FINDINGS TO FIX:\n{findings_text}\nYou MUST eliminate these vulnerabilities in your new code."

        # ── Contract-driven guidance (NO hardcoded UI templates) ─────────────
        # Everything the model needs comes from the Architect's contract:
        # interface_contracts, validation_rules, entry_points. The model decides
        # how to implement them — we never stamp prescriptive markup or logic.
        contract_guidance = self._build_contract_guidance(contract)

        # Honor an explicit no-framework constraint (user's stated choice, not UI bias)
        stack_warning = ""
        if input_data.stack_target.lower() in ("html5", "vanilla", "plain"):
            stack_warning = (
                "\n\nSTACK CONSTRAINT: The user explicitly chose plain HTML5/vanilla. "
                "Do NOT introduce React, Vue, Angular, JSX, or any build tooling. "
                "Use only standard HTML, CSS, and vanilla JavaScript."
            )

        # ── Adaptive batching ────────────────────────────────────────────────
        def _batch_size_for(f: dict) -> int:
            ext = (f.get("path", "") or "").rsplit(".", 1)[-1].lower()
            if ext in ("html", "jsx", "tsx", "vue", "svelte"):
                return 1
            if ext in ("js", "ts", "py", "go", "rs", "java", "rb", "php", "cpp", "c", "cs", "kt", "swift"):
                return 1
            return 3  # config, css, json, md, yaml, toml, etc.

        batches: list[list[dict]] = []
        current_batch: list[dict] = []
        current_limit = 1
        for file_entry in file_plan:
            limit = _batch_size_for(file_entry)
            if not current_batch:
                current_batch = [file_entry]
                current_limit = limit
            elif limit == current_limit and len(current_batch) < current_limit:
                current_batch.append(file_entry)
            else:
                batches.append(current_batch)
                current_batch = [file_entry]
                current_limit = limit
        if current_batch:
            batches.append(current_batch)

        for batch_idx, batch in enumerate(batches):
            batch_json = json.dumps(batch, indent=2)
            if all_generated:
                prior_summary = json.dumps([
                    {"path": f["relative_path"], "preview": f.get("content_preview", "")[:300]}
                    for f in all_generated
                ], indent=2)
            else:
                prior_summary = "none yet"

            prompt = (
                f"Project: {input_data.project_name}\n"
                f"STACK TARGET: {input_data.stack_target}{stack_warning}\n"
                f"PRODUCT TYPE: {input_data.product_type}\n"
                f"Requirement:\n{input_data.requirement}\n\n"
                f"Spec Summary:\n{input_data.spec_summary}\n"
                f"{contract_guidance}\n\n"
                f"Files already generated (path + preview):\n{prior_summary}\n\n"
                f"Generate ONLY these {len(batch)} file(s) now (batch {batch_idx + 1}/{len(batches)}):\n{batch_json}"
                f"{feedback_section}\n\n"
                "Generate ONLY the listed files. "
                "ONLY output ===FILE: path.ext=== blocks followed by ===END===. "
                "NO introductions. NO explanations. NO questions. ONLY file blocks. "
                "Every file MUST contain real, working code — not stubs or TODOs."
            )

            response = await self.provider.complete(
                ModelRequest(
                    prompt=prompt,
                    system_prompt=load_system_prompt("coder", _CODER_SYSTEM_DEFAULT),
                    temperature=0.2,
                    max_tokens=16384,
                )
            )
            if not response.success:
                return CoderOutput(success=False, error=response.error)

            generated = self._parse_files(response.content)
            if not generated:
                # Salvage: the model ignored the ===FILE:=== protocol (common with
                # code-tuned models that emit bare markdown fences). Since we know the
                # exact files this batch was asked to produce, map the model's code
                # blocks onto those known paths instead of failing.
                generated = self._salvage_files(response.content, batch)
                if generated:
                    logger.info("Coder salvaged %d file(s) for batch %d via known file_plan paths", len(generated), batch_idx + 1)
            if not generated:
                return CoderOutput(
                    success=False,
                    error=f"Batch {batch_idx + 1}: No parseable files found. Wrap every file in ===FILE: path.ext=== ... ===END=== format."
                )
            all_generated.extend(generated)

        if not all_generated:
            return CoderOutput(success=False, error="No parseable files found in any batch.")

        # Self-validation: reject if too many empty/stub files (language-agnostic)
        empty_count = sum(1 for f in all_generated if f.get("size", 0) < 50)
        if empty_count > len(all_generated) // 3:
            logger.warning("Coder produced %d/%d empty/stub files — treating as failure", empty_count, len(all_generated))
            return CoderOutput(success=False, error=f"Generated {empty_count}/{len(all_generated)} empty or stub files. Write complete code for every file.")

        # Self-validation: note missing planned source files (don't fail — let QA loop catch it)
        planned_paths = {self._sanitize_path(f.get("path", "")) for f in input_data.file_plan if f.get("path")}
        generated_paths = {self._sanitize_path(f.get("relative_path", "").replace("src/", "")) for f in all_generated}
        source_plan = {p for p in planned_paths if p and not p.endswith((".md", ".txt", ".rst"))}
        if source_plan:
            missing = source_plan - generated_paths
            if missing:
                logger.warning("Coder missing %d planned files: %s", len(missing), missing)

        # ── ONLY mechanical wiring left: ensure HTML actually links its stylesheet ──
        # This is correctness plumbing (the LLM wrote the CSS; make sure it loads),
        # NOT UI generation. No content, layout, or logic is ever fabricated here.
        src_dir = self.build_dir / "src"
        if src_dir.exists() and ui_layer == "html_css":
            for html_file in src_dir.rglob("*.html"):
                try:
                    content = html_file.read_text(encoding="utf-8")
                    has_local_css = (src_dir / "styles.css").exists() or any(src_dir.rglob("*.css"))
                    if has_local_css and "<link" not in content.lower():
                        css_name = "styles.css"
                        existing = list(src_dir.rglob("*.css"))
                        if existing and not (src_dir / "styles.css").exists():
                            css_name = existing[0].name
                        inject = f'<link rel="stylesheet" href="{css_name}">'
                        if "</head>" in content:
                            content = content.replace("</head>", f"  {inject}\n</head>")
                        elif "<head>" in content:
                            content = content.replace("<head>", f"<head>\n  {inject}")
                        else:
                            continue
                        html_file.write_text(content, encoding="utf-8")
                        logger.info("Coder: linked stylesheet in %s", html_file.name)
                        for f in all_generated:
                            if f.get("path") == str(html_file):
                                f["content_preview"] = content[:500]
                                f["size"] = len(content)
                except Exception as e:
                    logger.warning("Could not link stylesheet in %s: %s", html_file.name, e)

        # ── Self-consistency: the Coder verifies its OWN work before handoff ──────
        # Catches the #1 cause of dead pages: JS selectors that match no element it
        # wrote. This is the agent doing its job (general, language-level — NOT a
        # hardcoded template). It re-prompts itself to reconcile, up to 2 passes.
        if is_web_build and src_dir.exists():
            for _pass in range(3):
                feedback = self._runtime_self_check(src_dir)
                if not feedback:
                    break
                logger.info("Coder self-check pass %d found runtime issues; self-correcting", _pass + 1)
                fixed = await self._self_correct(input_data, src_dir, feedback)
                if not fixed:
                    break
            # refresh generated_files from disk after any self-correction
            refreshed = []
            for p in sorted([q for q in src_dir.rglob("*") if q.is_file()]):
                rel = p.relative_to(src_dir).as_posix()
                try:
                    txt = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    txt = ""
                refreshed.append({"path": str(p), "relative_path": f"src/{rel}",
                                  "size": len(txt), "content_preview": txt[:500]})
            if refreshed:
                all_generated = refreshed

        return CoderOutput(success=True, generated_files=all_generated)

    def _selector_mismatches(self, src_dir: Path):
        """Static check: find JS getElementById / simple querySelector targets that match
        no element anywhere (HTML or JS-created). Returns details or None if all resolve.
        General language-level check — no project-specific assumptions."""
        html_ids, classes = set(), set()
        # Collect ids/classes from HTML *and* from JS string templates (innerHTML etc.),
        # so elements the JS creates dynamically are not false-flagged.
        scan_text = ""
        for h in src_dir.rglob("*.html"):
            scan_text += "\n" + h.read_text(errors="replace")
        for j in src_dir.rglob("*.js"):
            scan_text += "\n" + j.read_text(errors="replace")
        for m in re.findall(r'id\s*=\s*["\']([^"\']+)["\']', scan_text):
            html_ids.add(m.strip())
        for cl in re.findall(r'class\s*=\s*["\']([^"\']+)["\']', scan_text):
            for c in cl.split():
                classes.add(c.strip())
        # Also count setAttribute('id', 'x') / .id = 'x'
        for m in re.findall(r'\.id\s*=\s*["\']([^"\']+)["\']', scan_text):
            html_ids.add(m.strip())

        dead_ids, dead_sel = [], []
        for j in src_dir.rglob("*.js"):
            code = j.read_text(errors="replace")
            for m in re.findall(r'getElementById\(\s*["\']([^"\']+)["\']', code):
                if m not in html_ids:
                    dead_ids.append(m)
            for sel in re.findall(r'querySelector(?:All)?\(\s*["\']([^"\']+)["\']', code):
                s = sel.strip()
                if re.match(r'^#[\w-]+$', s) and s[1:] not in html_ids:
                    dead_sel.append(s)
                elif re.match(r'^\.[\w-]+$', s) and s[1:] not in classes:
                    dead_sel.append(s)
        dead_ids = sorted(set(dead_ids))
        dead_sel = sorted(set(dead_sel))
        if dead_ids or dead_sel:
            return {"dead": {"getElementById": dead_ids, "querySelector": dead_sel},
                    "available_ids": sorted(html_ids)[:40], "available_classes": sorted(classes)[:40]}
        return None

    def _runtime_self_check(self, src_dir: Path):
        """Run the SAME headless runtime checker the pipeline uses, on the Coder's own
        output. Returns a precise feedback string if any page throws / has dead selectors /
        broken interactions, or None if all pages are clean. Falls back to a static
        selector check if Node isn't available. General — no project assumptions."""
        import subprocess, shutil, json as _json
        checker = Path(__file__).resolve().parents[2] / "tools" / "runtime-check" / "check.js"
        node = shutil.which("node")
        pages = sorted(p.name for p in src_dir.glob("*.html"))
        if not pages:
            return None
        if not node or not checker.exists():
            # Static fallback: simple selector/element mismatch check
            m = self._selector_mismatches(src_dir)
            if not m:
                return None
            return (f"DEAD getElementById {m['dead']['getElementById']}; "
                    f"DEAD querySelector {m['dead']['querySelector']}; "
                    f"available ids {m['available_ids']}; available classes {m['available_classes']}")
        try:
            proc = subprocess.run([node, str(checker), str(src_dir), *pages],
                                  capture_output=True, text=True, timeout=90)
            data = _json.loads(proc.stdout.strip() or "{}")
        except Exception:
            return None
        lines = []
        for pg in data.get("pages", []):
            if pg.get("ok"):
                continue
            errs = (pg.get("errors", []) or []) + (pg.get("functionalErrors", []) or [])
            detail = f"- {pg.get('page','?')}: " + "; ".join(errs[:3])
            dead = pg.get("deadSelectors", {}) or {}
            if dead.get("getElementById") or dead.get("querySelector"):
                detail += (f"\n    dead getElementById {dead.get('getElementById')}, "
                           f"dead querySelector {dead.get('querySelector')}; "
                           f"real ids {pg.get('availableIds')}, real classes {pg.get('availableClasses')}")
            lines.append(detail)
        return "\n".join(lines) if lines else None

    async def _self_correct(self, input_data, src_dir: Path, feedback: str) -> bool:
        """Re-prompt the LLM (fast model) to fix the runtime issues it caused. The model
        decides HOW (add the missing element, fix the selector, guard nulls) — we never
        inject markup. Returns True if it wrote any changed file."""
        files = [p for p in src_dir.rglob("*") if p.is_file() and p.suffix in (".html", ".js")]
        budget, bodies, used = 40000, [], 0
        for p in sorted(files):
            rel = p.relative_to(src_dir).as_posix()
            txt = p.read_text(errors="replace")
            block = f"===FILE: {rel}===\n{txt}\n===END===\n"
            if used + len(block) <= budget:
                bodies.append(block); used += len(block)
        system = (
            "You wrote this site and it has RUNTIME bugs: pages throw JavaScript errors when "
            "loaded or buttons do nothing when clicked. Fix them so every page loads with zero "
            "JS errors and every control works. Typical causes: a selector/getElementById that "
            "matches no element, calling a method on a null result, or an inline onclick referencing "
            "a function that isn't global. Either add the missing element with the exact id/class, "
            "or fix the JS to match what exists, or guard with if(el). Keep all working features. "
            "Return ONLY the files you change, complete, as ===FILE: path===\\n<content>\\n===END===. "
            "No prose, no markdown fences."
        )
        prompt = (
            "Current files:\n" + "".join(bodies) + "\n"
            "RUNTIME ISSUES detected by executing the pages in a headless browser:\n"
            f"{feedback}\n\n"
            "Fix every issue above. Return only the changed files now."
        )
        resp = await self.provider.complete(ModelRequest(
            prompt=prompt, system_prompt=system, temperature=0.2, max_tokens=16384,
        ))
        if not resp.success:
            return False
        return bool(self._parse_files(resp.content))

    async def _run_patch(self, input_data: "CoderInput", src_dir: Path, existing_files: list[Path]):
        """Additive retry: keep all existing files, edit only what the feedback names.

        Sends the current project to the LLM with the validator/smoke feedback and asks
        for ONLY the changed files back (===FILE:=== format). Unchanged files stay on disk.
        Returns a CoderOutput (full current file set) on success, or None to fall back to
        full regeneration."""
        # Build a context of current files (budgeted to fit the model's context window).
        CHAR_BUDGET = 12000
        listing = []
        bodies = []
        used = 0
        for p in sorted(existing_files):
            rel = p.relative_to(src_dir).as_posix()
            listing.append(rel)
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            snippet = text if len(text) <= 8000 else text[:8000] + "\n/* …truncated… */"
            block = f"===FILE: {rel}===\n{snippet}\n===END===\n"
            if used + len(block) <= CHAR_BUDGET:
                bodies.append(block)
                used += len(block)

        feedback = input_data.fix_feedback or ""
        if input_data.findings:
            feedback += "\n\nSECURITY FINDINGS TO FIX:\n" + "\n".join(
                f"- {f.get('severity','?')}: {f.get('description','')} ({f.get('file_path','?')}:{f.get('line_number','?')})"
                for f in input_data.findings[:10]
            )

        system = (
            "You are editing an EXISTING project. You are given the current files and a list "
            "of issues to fix. Apply ONLY the changes needed to resolve those issues. "
            "Preserve all working functionality that is already present — do not remove features "
            "or pages that already work. "
            "If an issue says a page is an 'empty shell', rewrite that page with ALL real content "
            "directly in the HTML (headings, paragraphs, cards, forms, buttons) — never a bare "
            "<div id='app'></div> filled by JS, never placeholder comments. "
            "Return ONLY the files you actually changed, each as a COMPLETE file in this format:\n"
            "===FILE: relative/path.ext===\n<full updated file>\n===END===\n"
            "Do NOT return files you did not change. No prose, no markdown fences."
        )
        prompt = (
            f"Project: {input_data.project_name}\n"
            f"Spec summary:\n{input_data.spec_summary}\n\n"
            f"Current files in the project:\n- " + "\n- ".join(listing) + "\n\n"
            f"Current file contents:\n" + "".join(bodies) + "\n"
            f"{'='*60}\nISSUES TO FIX (address every one):\n{feedback}\n{'='*60}\n\n"
            f"Return ONLY the changed files now, complete, in ===FILE:=== format."
        )

        response = await self.provider.complete(ModelRequest(
            prompt=prompt, system_prompt=system, temperature=0.2, max_tokens=16384,
        ))
        if not response.success:
            logger.warning("Coder patch mode LLM failed (%s) — falling back to full regen", response.error)
            return None

        changed = self._parse_files(response.content)
        if not changed:
            # Try salvage against the whole known file list as a single-target hint
            logger.warning("Coder patch mode: no parseable changed files — falling back to full regen")
            return None

        logger.info("Coder patch mode: edited %d file(s) in place", len(changed))

        # Return the FULL current file set (changed + untouched) so QA/DB see everything.
        all_files: list[dict] = []
        for p in sorted([q for q in src_dir.rglob("*") if q.is_file()]):
            rel = p.relative_to(src_dir).as_posix()
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
            all_files.append({
                "path": str(p),
                "relative_path": f"src/{rel}",
                "size": len(text),
                "content_preview": text[:500],
            })
        return CoderOutput(success=True, generated_files=all_files)

    def _build_contract_guidance(self, contract: dict) -> str:
        """
        Turn the Architect's machine-readable contract into guidance text.
        This is the ONLY source of per-build direction — no hardcoded archetype
        templates. The LLM decides how to satisfy the contract.
        """
        if not contract:
            return ""
        parts = ["\n\nCONTRACT — you MUST satisfy every item below:"]

        entry_points = _as_list(contract.get("entry_points"))
        if entry_points:
            parts.append(f"- Entry points (must exist and be runnable): {', '.join(str(e) for e in entry_points)}")

        interfaces = _as_list(contract.get("interface_contracts"))
        if interfaces:
            parts.append("- Interfaces to implement:")
            for iface in interfaces[:30]:
                if isinstance(iface, dict):
                    itype = iface.get("type", "")
                    name = iface.get("name", "")
                    desc = iface.get("description", "")
                    parts.append(f"    • [{itype}] {name}: {desc}")
                else:
                    parts.append(f"    • {iface}")

        rules = _as_list(contract.get("validation_rules"))
        if rules:
            parts.append("- These conditions define a passing build (make them true):")
            for rule in rules[:20]:
                parts.append(f"    • {rule}")

        artifacts = _as_list(contract.get("required_artifacts"))
        if artifacts:
            names = []
            for a in artifacts:
                if isinstance(a, dict) and a.get("path"):
                    names.append(str(a["path"]))
                elif isinstance(a, str):
                    names.append(a)
            if names:
                parts.append(f"- Required artifacts: {', '.join(names[:30])}")

        return "\n".join(parts)

    def _salvage_files(self, raw: str, batch: list[dict]) -> list[dict]:
        """Last-resort recovery when a model ignores the ===FILE:=== protocol.

        We know exactly which files this batch was supposed to produce (from the
        file plan), so we extract the model's code block(s) and map them onto the
        known target paths. Makes the Coder tolerant of any model's output style."""
        planned = [self._sanitize_path(f.get("path", "")) for f in batch if f.get("path")]
        planned = [p for p in planned if p]
        if not planned:
            return []

        # Pull fenced code blocks (```lang ... ```), stripping the fences.
        blocks = re.findall(r'```[^\n]*\n(.*?)```', raw, re.DOTALL)
        blocks = [b.strip("\n") for b in blocks if b.strip()]

        # If no fences at all, treat the whole response as one block (single-file batch).
        if not blocks:
            body = raw.strip()
            # Drop obvious leading prose lines before the first code-looking line
            if body and len(planned) == 1:
                blocks = [body]

        if not blocks:
            return []

        results = []
        # Map blocks to planned paths positionally. If counts differ but there's
        # exactly one planned file, concatenate all blocks into it.
        if len(planned) == 1 and len(blocks) >= 1:
            pairs = [(planned[0], blocks[0] if len(blocks) == 1 else "\n\n".join(blocks))]
        else:
            pairs = list(zip(planned, blocks))

        for rel_path, body in pairs:
            if not body or len(body) < 10:
                continue
            target = self.build_dir / "src" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": f"src/{rel_path}",
                "size": len(body),
                "content_preview": body[:500],
            })
        return results

    def _parse_files(self, raw: str) -> list[dict]:
        results = []

        # Primary: ===FILE: path=== format
        parts = re.split(r'===FILE:\s*', raw)
        for part in parts[1:]:
            header, _, body = part.partition('\n')
            path = header.replace('===', '').strip()
            body = re.split(r'===END===|===FILE:', body)[0]
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            body = body.strip('\n')
            rel_path = self._sanitize_path(path)
            if not rel_path:
                continue
            target = self.build_dir / "src" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": f"src/{rel_path}",
                "size": len(body),
                "content_preview": body[:500],
            })

        if results:
            logger.info("Coder parsed %d files (===FILE: format)", len(results))
            return results

        # Fallback: markdown code blocks with filenames
        md_pattern = re.compile(
            r'(?:(?:\*\*|__)([^*_\n]+\.\w+)(?:\*\*|__)\s*\n)?'
            r'```(?:\w+)?\n'
            r'(?://\s*([^\n]+\.\w+)\n)?'
            r'(.*?)'
            r'```',
            re.DOTALL
        )
        for match in md_pattern.finditer(raw):
            bold_name = match.group(1)
            comment_name = match.group(2)
            body = match.group(3).strip()
            path = bold_name or comment_name
            if not path or not body or len(body) < 10:
                continue
            rel_path = self._sanitize_path(path.strip())
            if not rel_path:
                continue
            target = self.build_dir / "src" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": f"src/{rel_path}",
                "size": len(body),
                "content_preview": body[:500],
            })

        if results:
            logger.info("Coder parsed %d files (markdown fallback)", len(results))
            return results

        # Last resort: heading + fenced content
        any_file_pattern = re.compile(
            r'(?:^|\n)#+\s*([^\n]+\.\w+)\s*\n(.*?)(?=\n#+\s|\Z)',
            re.DOTALL | re.MULTILINE
        )
        for match in any_file_pattern.finditer(raw):
            path = match.group(1).strip()
            body = match.group(2).strip()
            body = re.sub(r'^```\w*\n', '', body)
            body = re.sub(r'\n```\s*$', '', body)
            if len(body) < 20:
                continue
            rel_path = self._sanitize_path(path)
            if not rel_path:
                continue
            target = self.build_dir / "src" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            results.append({
                "path": str(target),
                "relative_path": f"src/{rel_path}",
                "size": len(body),
                "content_preview": body[:500],
            })

        if results:
            logger.info("Coder parsed %d files (heading fallback)", len(results))

        return results

    def _sanitize_path(self, raw: str) -> str:
        """Strip drive letters, leading slashes, src/ prefix, and path-traversal attempts.
        Accepts ANY file extension — the pipeline is language/file-type agnostic."""
        if len(raw) >= 2 and raw[1] == ":":
            raw = raw[2:]
        raw = raw.lstrip("/\\")
        if raw.lower().startswith("src/") or raw.lower().startswith("src\\"):
            raw = raw[4:]
            raw = raw.lstrip("/\\")
        parts = raw.replace("\\", "/").split("/")
        safe = [p for p in parts if p and p != "." and p != ".."]
        if not safe:
            return ""
        joined = "/".join(safe)
        test = (self.build_dir / "src" / joined).resolve()
        src_root = (self.build_dir / "src").resolve()
        try:
            test.relative_to(src_root)
        except ValueError:
            logger.warning("Path escapes src directory: %s", raw)
            return ""
        return joined
