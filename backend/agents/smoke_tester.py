import json
import logging
import re
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.core.archetype import ArchetypeClassifier, ProductArchetype

logger = logging.getLogger(__name__)


def _as_list(value) -> list:
    """Coerce an LLM-produced contract field into a list regardless of shape."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return [value]


def _entry_names(entry_points) -> list:
    """Normalize contract entry_points into a list of filename strings."""
    names = []
    for ep in _as_list(entry_points):
        if isinstance(ep, str):
            names.append(ep)
        elif isinstance(ep, dict) and ep.get("path"):
            names.append(str(ep["path"]))
    return names


class SmokeTesterInput(BaseModel):
    build_id: str
    build_dir: str
    project_name: str
    stack_target: str
    project_type: str
    requirement: str = ""
    archetype: ProductArchetype = ProductArchetype.SINGLE_PAGE_APP
    contract: dict = {}
    product_type: str = "web_app"


class SmokeTesterOutput(BaseModel):
    success: bool
    error: str = ""
    tests_passed: int = 0
    tests_failed: int = 0
    results: list[dict] = []
    fix_feedback: str = ""
    categories_failed: list[str] = []


class SmokeTesterAgent(BaseAgent[SmokeTesterInput, SmokeTesterOutput]):
    """
    Contract-driven acceptance tester.
    Routes to stack-appropriate checks based on contract.stack_family:
      "web"       → HTML structure, CSS rules, JS logic, archetype file counts
      "python"    → .py syntax, entry point, requirements.txt
      "node"      → package.json validity, .js/.ts logic
      "fullstack" → both web and backend checks
      "any"       → source file presence + contract required_artifacts
    Universal: always checks contract.required_artifacts if present.
    """

    def __init__(self, build_dir: Path):
        self.build_dir = build_dir
        self.archetype_classifier = ArchetypeClassifier()

    async def run(self, inp: SmokeTesterInput) -> SmokeTesterOutput:
        src = self.build_dir / "src"
        if not src.exists():
            src = self.build_dir

        r, p, f, fixes = [], 0, 0, []
        cats: set = set()

        contract = inp.contract or {}
        stack_family = contract.get("stack_family", "")
        ui_layer = contract.get("ui_layer", "")

        # Determine effective stack family
        if not stack_family:
            # Infer from archetype
            archetype_contract = self.archetype_classifier.get_contract(inp.archetype)
            stack_family = archetype_contract.stack_family

        is_web = (
            stack_family == "web"
            or ui_layer in ("html_css", "react")
            or inp.project_type.lower() in ("web", "website", "pwa", "spa", "static", "game_web", "web_app")
            or "html" in inp.stack_target.lower()
        )
        is_python = stack_family == "python" or "python" in inp.stack_target.lower() or "fastapi" in inp.stack_target.lower() or "flask" in inp.stack_target.lower()
        is_node = stack_family == "node" or "node" in inp.stack_target.lower() or "express" in inp.stack_target.lower()
        is_fullstack = stack_family == "fullstack"

        # ── Universal: source files exist ───────────────────────────────
        all_files = [x for x in src.rglob("*") if x.is_file() and x.stat().st_size > 0]
        if not all_files:
            r.append({"t": "files", "s": "fail", "d": "src/ is empty — no source files generated"})
            f += 1
            fixes.append("The coder generated no files. Regenerate with complete source code.")
            cats.add("files")
        else:
            r.append({"t": "files", "s": "pass", "d": f"{len(all_files)} files found"})
            p += 1

        # ── Universal: contract required_artifacts check ─────────────────
        required_artifacts = _as_list(contract.get("required_artifacts"))
        if required_artifacts:
            existing_exts = {p.suffix.lower() for p in all_files}
            missing_artifacts = []   # genuinely absent — no file of that type either
            drifted_artifacts = []   # exact name absent but a same-type file exists (naming drift)
            for artifact in required_artifacts:
                if isinstance(artifact, dict):
                    artifact_path = artifact.get("path", "")
                elif isinstance(artifact, str):
                    artifact_path = artifact
                else:
                    artifact_path = ""
                if not artifact_path:
                    continue
                # Try to find file — check under src/ directly and as relative path
                candidate1 = src / artifact_path
                candidate2 = src / Path(artifact_path).name
                if candidate1.exists() or candidate2.exists():
                    continue
                # Exact file missing. If a file of the SAME extension exists, treat it as
                # filename drift (e.g. contract said script.js, coder wrote app.js) — not a
                # hard failure. Only fail when no file of that type exists at all.
                ext = Path(artifact_path).suffix.lower()
                if ext and ext in existing_exts:
                    drifted_artifacts.append(artifact_path)
                else:
                    missing_artifacts.append(artifact_path)
            if missing_artifacts:
                missing_list = ", ".join(missing_artifacts[:10])
                r.append({"t": "required_artifacts", "s": "fail", "d": f"Missing contract artifacts: {missing_list}"})
                f += 1
                fixes.append(f"The Architect's contract requires these files which are missing: {missing_list}. Generate all required artifacts.")
                cats.add("required_artifacts")
            if drifted_artifacts:
                r.append({"t": "required_artifacts", "s": "warn",
                          "d": f"Filename drift (same-type file exists): {', '.join(drifted_artifacts[:10])}"})
            if not missing_artifacts and not drifted_artifacts:
                r.append({"t": "required_artifacts", "s": "pass", "d": f"All {len(required_artifacts)} required artifacts present"})
                p += 1

        # ── Web checks ───────────────────────────────────────────────────
        if is_web:
            self._check_web(src, inp, r, fixes, cats)
            p_new = sum(1 for x in r if x.get("s") == "pass")
            f_new = sum(1 for x in r if x.get("s") == "fail")
            p = p_new
            f = f_new

        # ── Python checks ────────────────────────────────────────────────
        if is_python and not is_web:
            py_p, py_f = self._check_python(src, inp, r, fixes, cats)
            p += py_p
            f += py_f

        # ── Node checks ──────────────────────────────────────────────────
        if is_node and not is_web:
            nd_p, nd_f = self._check_node(src, inp, r, fixes, cats)
            p += nd_p
            f += nd_f

        # ── Fullstack: web + backend ─────────────────────────────────────
        if is_fullstack:
            self._check_web(src, inp, r, fixes, cats)
            # Find backend dir
            backend_src = src
            for candidate in (src / "backend", src / "server", src / "api"):
                if candidate.exists():
                    backend_src = candidate
                    break
            if (backend_src / "requirements.txt").exists() or list(backend_src.rglob("*.py")):
                nd_p, nd_f = self._check_python(backend_src, inp, r, fixes, cats)
                p += nd_p
                f += nd_f
            elif (backend_src / "package.json").exists() or list(backend_src.rglob("*.js")):
                nd_p, nd_f = self._check_node(backend_src, inp, r, fixes, cats)
                p += nd_p
                f += nd_f
            p = sum(1 for x in r if x.get("s") == "pass")
            f = sum(1 for x in r if x.get("s") == "fail")

        # ── Generic "any" stack: just check source files have real content ─
        if not is_web and not is_python and not is_node and not is_fullstack:
            any_p, any_f = self._check_any(src, r, fixes, cats)
            p += any_p
            f += any_f

        # Recount from results for accuracy
        p = sum(1 for x in r if x.get("s") == "pass")
        f = sum(1 for x in r if x.get("s") == "fail")

        success = f == 0
        feedback = "\n".join(f"- {fix}" for fix in fixes) if fixes else "All smoke tests passed."
        return SmokeTesterOutput(
            success=success,
            tests_passed=p,
            tests_failed=f,
            results=r,
            fix_feedback=feedback,
            categories_failed=sorted(cats),
        )

    # ── Web validation ───────────────────────────────────────────────────

    def _check_web(self, src: Path, inp: SmokeTesterInput, r: list, fixes: list, cats: set):
        html_files = list(src.rglob("*.html"))
        css_files = list(src.rglob("*.css"))
        js_files = list(src.rglob("*.js"))
        contract = inp.contract or {}

        archetype = inp.archetype
        archetype_contract = self.archetype_classifier.get_contract(archetype)

        # File counts are ADVISORY ONLY — the LLM/contract decides structure.
        # We never fail a build for "too many" or "too few" files; the real gates
        # are: contract required_artifacts present, valid structure, real logic.
        # The only hard floor is "at least one HTML page exists" (checked below).
        if not html_files:
            r.append({"t": "html_present", "s": "fail", "d": "No HTML file in a web build"})
            fixes.append("A web build needs at least one HTML page. Generate index.html with real content.")
            cats.add("html_present")
        else:
            r.append({"t": "html_present", "s": "pass", "d": f"{len(html_files)} HTML, {len(css_files)} CSS, {len(js_files)} JS"})
            # Soft hint only — recorded as a warning, never fails the build
            if archetype_contract.max_html_files and len(html_files) > archetype_contract.max_html_files:
                r.append({"t": "html_count_hint", "s": "warn", "d": f"{len(html_files)} HTML (typical {archetype.value} uses ≤{archetype_contract.max_html_files})"})

        # Navigation (multi-page) — advisory unless the contract clearly needs it
        if archetype_contract.requires_navigation and len(html_files) > 1:
            idx = src / "index.html"
            if idx.exists():
                idx_text = idx.read_text(errors="replace").lower()
                missing = [h.name for h in html_files if h.name != "index.html" and h.stem not in idx_text]
                if missing:
                    # Advisory — surfaced to the LLM as feedback, but does not fail the build
                    r.append({"t": "nav_links", "s": "warn", "d": f"index.html may be missing nav to {missing}"})
                    fixes.append(f"Consider adding navigation links to: {', '.join(missing)}.")
                else:
                    r.append({"t": "nav_links", "s": "pass", "d": "All pages linked"})

        # HTML quality
        for html in src.rglob("*.html"):
            c = html.read_text(errors="replace")
            cl = c.lower()
            if "<html" not in cl or "<body" not in cl:
                r.append({"t": f"html_{html.name}", "s": "fail", "d": "Missing html/body"})
                fixes.append(f"{html.name} needs <!DOCTYPE html> + <html> + <body>.")
                cats.add("html")
            else:
                r.append({"t": f"html_{html.name}", "s": "pass", "d": "Structure OK"})

            real_elements = len(re.findall(r'<(input|button|select|textarea|table|form|ul|ol|canvas)[^/]', c, re.IGNORECASE))
            has_real_content = len(re.findall(r'<(p|h[1-6]|span|label|td|th|li)[^/]', c, re.IGNORECASE)) > 2
            is_empty_shell = (
                bool(re.search(r'<div\s+id=["\']app["\']>\s*<\/div>', c, re.IGNORECASE)) or
                bool(re.search(r'<body[^>]*>\s*<script', c, re.IGNORECASE)) or
                (bool(re.search(r'<(section|div|main)[^>]*>\s*<!--[^-]', c, re.IGNORECASE)) and real_elements < 3) or
                (real_elements == 0 and not has_real_content)
            )
            if is_empty_shell:
                r.append({"t": f"html_empty_{html.name}", "s": "fail", "d": "Empty shell"})
                fixes.append(f"{html.name}: HTML is an empty shell. Write ALL UI elements directly in HTML — no <div id='app'></div> placeholders.")
                cats.add("html_empty")
            else:
                r.append({"t": f"html_empty_{html.name}", "s": "pass", "d": "Has real elements"})

            if re.search(r'(?:href|src)="/[^"]*"', c):
                r.append({"t": f"html_paths_{html.name}", "s": "fail", "d": "Absolute paths"})
                fixes.append(f"{html.name}: Use relative paths (href='styles.css') not absolute (/src/styles.css).")
                cats.add("html_paths")
            else:
                r.append({"t": f"html_paths_{html.name}", "s": "pass", "d": "Relative paths OK"})

        # CSS quality
        for css in src.rglob("*.css"):
            c = css.read_text(errors="replace")
            if "{" not in c:
                r.append({"t": f"css_{css.name}", "s": "fail", "d": "No CSS rules"})
                fixes.append(f"{css.name} needs CSS rules with selectors.")
                cats.add("css")
            else:
                rule_count = c.count("}")
                r.append({"t": f"css_{css.name}", "s": "pass", "d": f"{rule_count} rules"})

        # JS quality
        for js in src.rglob("*.js"):
            c = js.read_text(errors="replace")
            is_data = any(w in js.name.lower() for w in ("data", "model", "config", "sounds", "audio", "assets"))
            has_listener = "addeventlistener" in c.lower() or "onclick" in c.lower()
            has_function = "function" in c or "=>" in c or "const " in c or "let " in c or "var " in c
            if not has_function:
                r.append({"t": f"js_{js.name}", "s": "fail", "d": "No JS logic"})
                fixes.append(f"{js.name}: no functions defined. Write real logic.")
                cats.add("js")
            else:
                r.append({"t": f"js_{js.name}", "s": "pass", "d": "Has logic"})
            if not has_listener and not is_data:
                r.append({"t": f"js_events_{js.name}", "s": "fail", "d": "No event listeners"})
                fixes.append(f"{js.name}: add addEventListener or onclick handlers.")
                cats.add("js_events")
            else:
                r.append({"t": f"js_events_{js.name}", "s": "pass", "d": "Has events"})
            has_jsx = re.search(r'<[A-Z][A-Za-z0-9]*\s*/?>|<[A-Z][A-Za-z0-9]*\s+[^>]*>', c) or "React" in c
            if has_jsx:
                r.append({"t": f"js_jsx_{js.name}", "s": "fail", "d": "JSX in plain JS file"})
                fixes.append(f"{js.name}: contains JSX/React syntax. Rewrite as vanilla JavaScript.")
                cats.add("js_jsx")
            else:
                r.append({"t": f"js_jsx_{js.name}", "s": "pass", "d": "Vanilla JS"})

        # Archetype feature checks
        all_html_content = "".join(h.read_text(errors="replace").lower() for h in src.rglob("*.html"))
        all_js_content = "".join(j.read_text(errors="replace").lower() for j in src.rglob("*.js"))

        if archetype_contract.requires_canvas and "canvas" not in all_html_content:
            r.append({"t": "canvas_present", "s": "fail", "d": "No <canvas> element"})
            fixes.append(f"{archetype.value} requires a <canvas> element.")
            cats.add("canvas")
        elif archetype_contract.requires_canvas:
            r.append({"t": "canvas_present", "s": "pass", "d": "Canvas found"})

        if archetype_contract.requires_forms and not any(t in all_html_content for t in ["<form", "<input", "<select", "<textarea"]):
            r.append({"t": "forms_present", "s": "fail", "d": "No form elements"})
            fixes.append(f"{archetype.value} requires form elements.")
            cats.add("forms")
        elif archetype_contract.requires_forms:
            r.append({"t": "forms_present", "s": "pass", "d": "Forms found"})

        if archetype_contract.requires_interactivity:
            has_interaction = any(kw in all_js_content for kw in ("addeventlistener", "onclick", "onchange", "queryselector", "getelementbyid"))
            if not has_interaction:
                r.append({"t": "interactivity", "s": "fail", "d": "No interactive elements"})
                fixes.append(f"{archetype.value} requires interactive JavaScript.")
                cats.add("interactivity")
            else:
                r.append({"t": "interactivity", "s": "pass", "d": "Interactive"})

    # ── Python validation ────────────────────────────────────────────────

    def _check_python(self, src: Path, inp: SmokeTesterInput, r: list, fixes: list, cats: set) -> tuple[int, int]:
        p, f = 0, 0
        py_files = list(src.rglob("*.py"))
        contract = inp.contract or {}

        if not py_files:
            r.append({"t": "py_files", "s": "fail", "d": "No .py files found"})
            fixes.append("No Python source files found. Generate .py files for the project.")
            cats.add("py_files")
            f += 1
            return p, f
        r.append({"t": "py_files", "s": "pass", "d": f"{len(py_files)} .py files"})
        p += 1

        # Entry point check
        entry_points = _entry_names(contract.get("entry_points"))
        entry_found = False
        if entry_points:
            for ep in entry_points:
                ep_path = src / Path(ep).name
                if ep_path.exists() or (src / ep).exists():
                    entry_found = True
                    break
        else:
            # Try common names
            for name in ("main.py", "app.py", "run.py", "server.py", "cli.py", "__main__.py"):
                if (src / name).exists():
                    entry_found = True
                    break

        if not entry_found:
            ep_list = ", ".join(entry_points) if entry_points else "main.py or app.py"
            r.append({"t": "py_entry", "s": "fail", "d": f"No entry point ({ep_list})"})
            fixes.append(f"Create an entry point file: {ep_list}")
            cats.add("py_entry")
            f += 1
        else:
            r.append({"t": "py_entry", "s": "pass", "d": "Entry point found"})
            p += 1

        # requirements.txt — only REQUIRED when third-party packages are actually imported.
        # A stdlib-only script (argparse, json, os, ...) legitimately needs no requirements.txt.
        _STDLIB = {
            "argparse", "os", "sys", "json", "re", "math", "random", "datetime", "time",
            "pathlib", "typing", "collections", "itertools", "functools", "logging",
            "subprocess", "shutil", "tempfile", "io", "csv", "sqlite3", "urllib", "http",
            "socket", "threading", "asyncio", "dataclasses", "enum", "abc", "unittest",
            "hashlib", "base64", "uuid", "decimal", "string", "textwrap", "glob", "copy",
        }
        third_party = set()
        for py in py_files:
            txt = py.read_text(errors="replace")
            for m in re.finditer(r'^\s*(?:from|import)\s+([a-zA-Z_][\w]*)', txt, re.MULTILINE):
                mod = m.group(1)
                if mod not in _STDLIB and not (src / f"{mod}.py").exists() and not (src / mod).is_dir():
                    third_party.add(mod)

        req = src / "requirements.txt"
        if req.exists() and req.read_text(errors="replace").strip():
            r.append({"t": "requirements_txt", "s": "pass", "d": f"{len(req.read_text().strip().splitlines())} packages"})
            p += 1
        elif third_party:
            r.append({"t": "requirements_txt", "s": "fail", "d": f"Imports third-party packages but no requirements.txt: {sorted(third_party)[:8]}"})
            fixes.append(f"Create requirements.txt listing the third-party packages used: {', '.join(sorted(third_party)[:8])}.")
            cats.add("requirements")
            f += 1
        else:
            r.append({"t": "requirements_txt", "s": "pass", "d": "Stdlib-only — no requirements.txt needed"})
            p += 1

        # Python file quality
        for py in py_files:
            c = py.read_text(errors="replace")
            has_logic = "def " in c or "class " in c or "import " in c
            if not has_logic:
                r.append({"t": f"py_{py.name}", "s": "fail", "d": "No Python logic"})
                fixes.append(f"{py.name}: no functions, classes, or imports. Write real Python code.")
                cats.add("py")
                f += 1
            else:
                r.append({"t": f"py_{py.name}", "s": "pass", "d": "Has logic"})
                p += 1

            # Detect stubs
            stub_count = len(re.findall(r'^\s*(pass|\.\.\.)\s*$', c, re.MULTILINE))
            real_lines = len([ln for ln in c.splitlines() if ln.strip() and not ln.strip().startswith("#")])
            if stub_count > 0 and real_lines < 10:
                r.append({"t": f"py_stub_{py.name}", "s": "fail", "d": f"{stub_count} stub(s) in thin file"})
                fixes.append(f"{py.name}: contains only stubs/pass statements. Implement all functions.")
                cats.add("py_stubs")
                f += 1
            elif stub_count > 0:
                r.append({"t": f"py_stub_{py.name}", "s": "pass", "d": f"{stub_count} stub(s) but substantial file"})
                p += 1

        return p, f

    # ── Node validation ──────────────────────────────────────────────────

    def _check_node(self, src: Path, inp: SmokeTesterInput, r: list, fixes: list, cats: set) -> tuple[int, int]:
        p, f = 0, 0
        contract = inp.contract or {}

        pkg = src / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(errors="replace"))
                has_deps = bool(data.get("dependencies") or data.get("devDependencies"))
                has_scripts = bool(data.get("scripts"))
                has_start = bool(data.get("scripts", {}).get("start") or data.get("scripts", {}).get("dev"))
                if not has_deps:
                    r.append({"t": "pkg_deps", "s": "fail", "d": "No dependencies in package.json"})
                    fixes.append("package.json must list dependencies.")
                    cats.add("pkg")
                    f += 1
                else:
                    r.append({"t": "pkg_deps", "s": "pass", "d": "Has deps"})
                    p += 1
                if not has_scripts:
                    r.append({"t": "pkg_scripts", "s": "fail", "d": "No scripts in package.json"})
                    fixes.append("package.json must have scripts.start.")
                    cats.add("pkg")
                    f += 1
                elif not has_start:
                    r.append({"t": "pkg_start", "s": "fail", "d": "No start/dev script"})
                    fixes.append("package.json must have scripts.start or scripts.dev.")
                    cats.add("pkg")
                    f += 1
                else:
                    r.append({"t": "pkg_scripts", "s": "pass", "d": "Has start script"})
                    p += 1
            except Exception:
                r.append({"t": "pkg_json", "s": "fail", "d": "Invalid package.json"})
                fixes.append("package.json must be valid JSON.")
                cats.add("pkg")
                f += 1
        else:
            r.append({"t": "pkg_json", "s": "fail", "d": "Missing package.json"})
            fixes.append("Create package.json with name, dependencies, and scripts.start.")
            cats.add("pkg")
            f += 1

        # Entry point
        entry_points = _entry_names(contract.get("entry_points"))
        entry_found = False
        if entry_points:
            for ep in entry_points:
                if (src / Path(ep).name).exists() or (src / ep).exists():
                    entry_found = True
                    break
        else:
            for name in ("index.js", "server.js", "app.js", "main.js", "index.ts", "server.ts"):
                if (src / name).exists():
                    entry_found = True
                    break

        if not entry_found:
            r.append({"t": "node_entry", "s": "fail", "d": "No entry point (index.js/server.js)"})
            fixes.append("Create an entry point: index.js or server.js with the main application logic.")
            cats.add("node_entry")
            f += 1
        else:
            r.append({"t": "node_entry", "s": "pass", "d": "Entry point found"})
            p += 1

        # JS/TS file quality
        source_files = list(src.rglob("*.js")) + list(src.rglob("*.ts"))
        source_files = [s for s in source_files if "node_modules" not in str(s)]
        if not source_files:
            r.append({"t": "node_source", "s": "fail", "d": "No .js/.ts source files"})
            fixes.append("Generate JavaScript/TypeScript source files.")
            cats.add("node_source")
            f += 1
        else:
            r.append({"t": "node_source", "s": "pass", "d": f"{len(source_files)} source files"})
            p += 1
            for js in source_files[:5]:  # spot-check first 5
                c = js.read_text(errors="replace")
                has_logic = "function" in c or "=>" in c or "module.exports" in c or "export " in c or "class " in c or "require(" in c or "import " in c
                if not has_logic:
                    r.append({"t": f"node_{js.name}", "s": "fail", "d": "No JS/TS logic"})
                    fixes.append(f"{js.name}: write real logic, not an empty file.")
                    cats.add("node_js")
                    f += 1
                else:
                    r.append({"t": f"node_{js.name}", "s": "pass", "d": "Has logic"})
                    p += 1

        return p, f

    # ── Generic "any" stack ───────────────────────────────────────────────

    def _check_any(self, src: Path, r: list, fixes: list, cats: set) -> tuple[int, int]:
        p, f = 0, 0
        all_files = [x for x in src.rglob("*") if x.is_file()]
        if not all_files:
            r.append({"t": "any_source", "s": "fail", "d": "No source files"})
            fixes.append("No source files were generated.")
            cats.add("source")
            f += 1
            return p, f

        # Check that files have real content (not empty/trivial)
        empty = [x for x in all_files if x.stat().st_size < 20]
        real = [x for x in all_files if x.stat().st_size >= 20]
        if real:
            r.append({"t": "any_source", "s": "pass", "d": f"{len(real)} substantive files"})
            p += 1
        if empty:
            r.append({"t": "any_empty", "s": "fail", "d": f"{len(empty)} empty/trivial files: {[x.name for x in empty[:5]]}"})
            fixes.append(f"Files are empty or trivially small: {[x.name for x in empty[:5]]}. Write complete content.")
            cats.add("empty_files")
            f += 1

        return p, f
