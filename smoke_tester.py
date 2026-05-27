import json, logging, re
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.core.archetype import ArchetypeClassifier, ProductArchetype

logger = logging.getLogger(__name__)

class SmokeTesterInput(BaseModel):
    build_id: str; build_dir: str; project_name: str
    stack_target: str; project_type: str; requirement: str = ""
    archetype: ProductArchetype = ProductArchetype.SINGLE_PAGE_APP  # From Architect, not re-classified

class SmokeTesterOutput(BaseModel):
    success: bool; error: str = ""; tests_passed: int = 0
    tests_failed: int = 0; results: list[dict] = []; fix_feedback: str = ""
    categories_failed: list[str] = []  # e.g. ["html", "js_jsx", "placeholder"] for orchestrator routing

class SmokeTesterAgent(BaseAgent[SmokeTesterInput, SmokeTesterOutput]):
    """
    Runtime / content acceptance tester.
    ONLY validates file contents and structure — NOT security (Hardener) or spec compliance (Validator).
    Checks: HTML structure, CSS rules, JS functions, JSX ban, placeholder text, package.json validity.
    """
    def __init__(self, build_dir: Path): 
        self.build_dir = build_dir
        self.archetype_classifier = ArchetypeClassifier()

    async def run(self, inp: SmokeTesterInput) -> SmokeTesterOutput:
        src = self.build_dir / "src"
        if not src.exists(): src = self.build_dir
        r, p, f, fixes = [], 0, 0, []
        cats = set()

        files = [x for x in src.rglob("*") if x.is_file() and x.stat().st_size > 0]
        if not files: r.append({"t":"files","s":"fail","d":"src/ empty"}); f+=1; fixes.append("Generate actual source files in src/."); cats.add("files")
        else: r.append({"t":"files","s":"pass","d":f"{len(files)} files"}); p+=1

        # File-count heuristic for web apps: reject single-page stubs
        html_files = list(src.rglob("*.html"))
        css_files = list(src.rglob("*.css"))
        js_files = list(src.rglob("*.js"))
        is_web = (
            inp.project_type.lower() in ("web", "website", "pwa", "spa", "static")
            or "html" in inp.stack_target.lower()
            or len(html_files) > 0
        )
        # Mandatory: must have at least some source files
        source_files = list(src.rglob("*"))
        has_source = any(f.is_file() for f in source_files)
        if not has_source:
            r.append({"t":"source_files","s":"fail","d":"No source files in src/"}); f+=1
            fixes.append("No source files found in the build output. The coder did not generate any files. This build cannot succeed.")
            cats.add("source_files")
        else:
            r.append({"t":"source_files","s":"pass","d":f"{len([f for f in source_files if f.is_file()])} source files"}); p+=1

        if is_web:
            # Step 1: Use archetype from Architect (not re-classified)
            archetype = inp.archetype
            contract = self.archetype_classifier.get_contract(archetype)
            
            # Step 2: Apply archetype-specific validation
            # HTML file count validation
            if len(html_files) < contract.min_html_files:
                r.append({"t":"html_count","s":"fail","d":f"Only {len(html_files)} HTML page(s) (need {contract.min_html_files}+ for {archetype.value})"}); f+=1
                fixes.append(f"This {contract.description} requires at least {contract.min_html_files} HTML file(s). Current structure doesn't match the {archetype.value} archetype.")
                cats.add("html_count")
            elif contract.max_html_files and len(html_files) > contract.max_html_files:
                r.append({"t":"html_count","s":"fail","d":f"Too many HTML files: {len(html_files)} (max {contract.max_html_files} for {archetype.value})"}); f+=1
                fixes.append(f"This {contract.description} should have at most {contract.max_html_files} HTML file(s). Current structure has too many for the {archetype.value} archetype.")
                cats.add("html_count")
            else:
                r.append({"t":"html_count","s":"pass","d":f"{len(html_files)} HTML pages (matches {archetype.value})"}); p+=1
            
            # CSS file count validation
            if len(css_files) < contract.min_css_files:
                r.append({"t":"css_count","s":"fail","d":f"Only {len(css_files)} CSS file(s) (need {contract.min_css_files}+)"}); f+=1
                fixes.append(f"Generate at least {contract.min_css_files} CSS file(s) for the {archetype.value}.")
                cats.add("css_count")
            elif len(css_files) > contract.max_css_files:
                r.append({"t":"css_count","s":"fail","d":f"Too many CSS files: {len(css_files)} (max {contract.max_css_files})"}); f+=1
                extra = [c.name for c in css_files if c.name != "styles.css"]
                fixes.append(f"This {archetype.value} requires exactly {contract.max_css_files} CSS file(s). Remove extra files: {', '.join(extra)}.")
                cats.add("css_count")
            else:
                r.append({"t":"css_count","s":"pass","d":f"{len(css_files)} CSS file(s) (matches {archetype.value})"}); p+=1
            
            # JavaScript file count validation
            if len(js_files) < contract.min_js_files:
                r.append({"t":"js_count","s":"fail","d":f"Only {len(js_files)} JS file(s) (need {contract.min_js_files}+)"}); f+=1
                fixes.append(f"Generate at least {contract.min_js_files} JavaScript file(s) for the {archetype.value}.")
                cats.add("js_count")
            elif contract.max_js_files and len(js_files) > contract.max_js_files:
                r.append({"t":"js_count","s":"fail","d":f"Too many JS files: {len(js_files)} (max {contract.max_js_files} for {archetype.value})"}); f+=1
                fixes.append(f"This {archetype.value} should have at most {contract.max_js_files} JavaScript file(s).")
                cats.add("js_count")
            else:
                r.append({"t":"js_count","s":"pass","d":f"{len(js_files)} JS file(s) (matches {archetype.value})"}); p+=1
            # Step 3: Apply archetype-specific feature validation
            # Navigation validation (only for archetypes that require it)
            if contract.requires_navigation and len(html_files) > 1:
                idx = src / "index.html"
                if idx.exists():
                    idx_text = idx.read_text(errors="replace").lower()
                    nav_links = len([h for h in html_files if h.name != "index.html" and h.stem in idx_text])
                    if nav_links < len(html_files) - 1:
                        missing = [h.name for h in html_files if h.name != "index.html" and h.stem not in idx_text]
                        r.append({"t":"nav_links","s":"fail","d":f"Missing nav to {missing} (required for {archetype.value})"}); f+=1
                        fixes.append(f"This {archetype.value} requires navigation between pages. Add links to: {', '.join(missing)}.")
                        cats.add("nav_links")
                    else:
                        r.append({"t":"nav_links","s":"pass","d":"All pages linked from index"}); p+=1
            elif not contract.requires_navigation and len(html_files) > 1:
                # For archetypes that don't require navigation, just warn
                idx = src / "index.html"
                if idx.exists():
                    idx_text = idx.read_text(errors="replace").lower()
                    nav_links = len([h for h in html_files if h.name != "index.html" and h.stem in idx_text])
                    if nav_links < len(html_files) - 1:
                        missing = [h.name for h in html_files if h.name != "index.html" and h.stem not in idx_text]
                        r.append({"t":"nav_links","s":"warn","d":f"Missing nav to {missing} (optional for {archetype.value})"}); p+=1
                        fixes.append(f"Consider adding navigation links to: {', '.join(missing)} for better user experience.")
                    else:
                        r.append({"t":"nav_links","s":"pass","d":"All pages linked from index"}); p+=1

            # CSS quality: only check styles.css, ignore extra per-page CSS
            for css in css_files:
                if css.name != "styles.css":
                    continue  # skip per-page CSS files — only styles.css matters
                css_text = css.read_text(errors="replace")
                rule_count = css_text.count("}")
                has_vars = "--" in css_text
                has_dark = "[data-theme=\"dark\"]" in css_text or "dark" in css_text.lower()
                if rule_count < 3:
                    r.append({"t":"css_rules_styles","s":"fail","d":f"Only ~{rule_count} CSS rules"}); f+=1
                    fixes.append("styles.css: CSS file is nearly empty. Add at least a few selectors with real properties.")
                    cats.add("css_rules")
                else:
                    r.append({"t":"css_rules_styles","s":"pass","d":f"{rule_count} CSS rules"}); p+=1
                # CSS custom properties are nice but not mandatory for a passing build
                if not has_vars:
                    r.append({"t":"css_vars_styles","s":"warn","d":"No CSS custom properties"}); p+=1
                else:
                    r.append({"t":"css_vars_styles","s":"pass","d":"Has CSS vars"}); p+=1

            # JS quality: must have event listeners in app.js only, data.js can be pure data
            for js in js_files:
                js_text = js.read_text(errors="replace")
                is_data_file = "data" in js.name.lower() or "model" in js.name.lower() or "config" in js.name.lower() or "sounds" in js.name.lower() or "audio" in js.name.lower() or "assets" in js.name.lower()
                has_listener = "addeventlistener" in js_text.lower() or "onclick" in js_text.lower() or "onchange" in js_text.lower()
                has_function = "function" in js_text or "=>" in js_text or "const " in js_text or "let " in js_text or "var " in js_text
                # Only require event listeners in app.js / main logic files, NOT data/model files
                if not has_listener and not is_data_file:
                    r.append({"t":f"js_events_{js.name}","s":"fail","d":"No event listeners"}); f+=1
                    fixes.append(f"{js.name}: JavaScript file has no event listeners. Add addEventListener('click', ...) or onclick handlers for all interactive elements.")
                    cats.add("js_events")
                else:
                    r.append({"t":f"js_events_{js.name}","s":"pass","d":"Has event listeners"}); p+=1
                if not has_function:
                    r.append({"t":f"js_logic_{js.name}","s":"fail","d":"No functions"}); f+=1
                    fixes.append(f"{js.name}: JavaScript has no function definitions. Write real logic with functions, not just comments.")
                    cats.add("js_logic")
                else:
                    r.append({"t":f"js_logic_{js.name}","s":"pass","d":"Has functions"}); p+=1

        for html in src.rglob("*.html"):
            c = html.read_text(errors="replace")
            cl = c.lower()
            ok = "<html" in cl and "<body" in cl
            if not ok: r.append({"t":f"html_{html.name}","s":"fail","d":"No html/body"}); f+=1; fixes.append(f"{html.name} needs <!DOCTYPE html> + <html> + <body>."); cats.add("html")
            else: r.append({"t":f"html_{html.name}","s":"pass","d":"Structure OK"}); p+=1
            # Detect empty sections that only contain comments
            if ok and re.search(r'<(section|div|main)[^>]*>\s*<!--', c, re.IGNORECASE):
                r.append({"t":f"html_empty_{html.name}","s":"fail","d":"Empty sections with only comments"}); f+=1
                fixes.append(f"{html.name}: HTML sections contain only <!-- comments --> instead of actual DOM elements. Replace comments with real <div>, <button>, <input>, <select> elements with IDs so JavaScript can manipulate them.")
                cats.add("html_empty")
            else: p+=1; r.append({"t":f"html_empty_{html.name}","s":"pass","d":"Has real elements"})
            # Detect absolute paths that break subdirectory serving
            if re.search(r'(?:href|src)="/[^"]*"', c):
                r.append({"t":f"html_paths_{html.name}","s":"fail","d":"Absolute paths used"}); f+=1
                fixes.append(f"{html.name}: Uses absolute paths like href='/client/src/style.css' or src='/client/src/app.js'. Change to RELATIVE paths: href='style.css' or src='app.js' so the app works when served from any URL path.")
                cats.add("html_paths")
            else: p+=1; r.append({"t":f"html_paths_{html.name}","s":"pass","d":"Relative paths OK"})

        # Step 4: Archetype-specific feature validation (runs at top-level, not inside html loop)
        if is_web:
            all_html_content = ""
            for html in src.rglob("*.html"):
                all_html_content += html.read_text(errors="replace").lower()

            all_js_content = ""
            for js in src.rglob("*.js"):
                all_js_content += js.read_text(errors="replace").lower()

            # Canvas validation (for games)
            if contract.requires_canvas:
                if "canvas" not in all_html_content:
                    r.append({"t":"canvas_present","s":"fail","d":"No canvas element (required for game)"}); f+=1
                    fixes.append(f"This {archetype.value} requires a <canvas> element. Add canvas to your HTML.")
                    cats.add("canvas")
                else:
                    r.append({"t":"canvas_present","s":"pass","d":"Canvas element found"}); p+=1

            # Forms validation (for tools, admin panels, landing pages)
            if contract.requires_forms:
                if not any(tag in all_html_content for tag in ["<form", "<input", "<select", "<textarea"]):
                    r.append({"t":"forms_present","s":"fail","d":"No form elements (required for this archetype)"}); f+=1
                    fixes.append(f"This {archetype.value} requires form elements. Add <form>, <input>, <select>, or <textarea> elements.")
                    cats.add("forms")
                else:
                    r.append({"t":"forms_present","s":"pass","d":"Form elements found"}); p+=1

            # Interactivity validation (for archetypes that require it)
            if contract.requires_interactivity:
                has_interactivity = (
                    "addeventlistener" in all_js_content or
                    "onclick" in all_js_content or
                    "onchange" in all_js_content or
                    "onsubmit" in all_js_content or
                    "queryselector" in all_js_content or
                    "getelementbyid" in all_js_content
                )
                if not has_interactivity:
                    r.append({"t":"interactivity_present","s":"fail","d":"No interactivity (required for this archetype)"}); f+=1
                    fixes.append(f"This {archetype.value} requires interactive elements. Add event listeners or DOM manipulation.")
                    cats.add("interactivity")
                else:
                    r.append({"t":"interactivity_present","s":"pass","d":"Interactive elements found"}); p+=1

        for css in src.rglob("*.css"):
            c = css.read_text(errors="replace")
            if "{" not in c: r.append({"t":f"css_{css.name}","s":"fail","d":"No rules"}); f+=1; fixes.append(f"{css.name} needs CSS rules."); cats.add("css")
            else: r.append({"t":f"css_{css.name}","s":"pass","d":"Has rules"}); p+=1

        for js in src.rglob("*.js"):
            c = js.read_text(errors="replace")
            has_func = "function" in c or "=>" in c or "document." in c or "console." in c or "module.exports" in c or "require(" in c or "export " in c or "class " in c
            rel = str(js.relative_to(src))
            if not has_func:
                r.append({"t":f"js_{js.name}","s":"fail","d":"No JS logic"})
                f += 1
                fixes.append(f"File {rel}: MUST contain actual JavaScript code. Include at least ONE of: a function declaration (function x(){{...}}), an arrow function (const x = ()=>{{...}}), a class (class X{{...}}), DOM manipulation (document.querySelector), module.exports, or require(). Do NOT write empty files, placeholder comments, or TODOs.")
                cats.add("js")
            else: r.append({"t":f"js_{js.name}","s":"pass","d":"Has logic"}); p+=1
            # Detect JSX/framework syntax that browsers cannot execute directly
            has_jsx = re.search(r'<[A-Z][A-Za-z0-9]*\s*/?>|<[A-Z][A-Za-z0-9]*\s+[^>]*>', c) or 'React' in c or 'react' in c
            if has_jsx:
                r.append({"t":f"js_jsx_{js.name}","s":"fail","d":"Contains JSX/framework code"}); f+=1
                fixes.append(f"File {rel}: Contains React/JSX syntax (e.g. <Component />, React.createElement, import React). Browsers CANNOT execute JSX directly. Rewrite as plain vanilla JavaScript using document.createElement and addEventListener.")
                cats.add("js_jsx")
            else: p+=1; r.append({"t":f"js_jsx_{js.name}","s":"pass","d":"Vanilla JS"})
            # Detect placeholder text
            if re.search(r'This is a\s+\w+\s+(component|section|page|placeholder)', c, re.IGNORECASE):
                r.append({"t":f"js_placeholder_{js.name}","s":"fail","d":"Placeholder text detected"}); f+=1
                fixes.append(f"File {rel}: Contains placeholder text like 'This is a ... component'. Replace with REAL functionality: actual event handlers, data rendering, API calls, form validation, etc.")
                cats.add("js_placeholder")
            else: p+=1; r.append({"t":f"js_placeholder_{js.name}","s":"pass","d":"Real content"})

        pkg = src / "package.json"
        if pkg.exists():
            c = pkg.read_text(errors="replace")
            try:
                data = json.loads(c)
                deps = bool(data.get("dependencies") or data.get("devDependencies"))
                scripts = bool(data.get("scripts"))
                if not deps: r.append({"t":"pkg_deps","s":"fail","d":"No dependencies"}); f+=1; fixes.append("package.json must list dependencies."); cats.add("pkg")
                else: r.append({"t":"pkg_deps","s":"pass","d":"Has deps"}); p+=1
                if not scripts: r.append({"t":"pkg_scripts","s":"fail","d":"No scripts"}); f+=1; fixes.append("package.json must have scripts (start/build)."); cats.add("pkg")
                else: r.append({"t":"pkg_scripts","s":"pass","d":"Has scripts"}); p+=1
            except: r.append({"t":"pkg_json","s":"fail","d":"Invalid JSON"}); f+=1; fixes.append("package.json must be valid JSON."); cats.add("pkg")

        for py in src.rglob("*.py"):
            c = py.read_text(errors="replace")
            if "def " not in c and "class " not in c and "import " not in c:
                r.append({"t":f"py_{py.name}","s":"fail","d":"No Python logic"}); f+=1; fixes.append(f"{py.name} needs functions/classes/imports.")
                cats.add("py")
            else: r.append({"t":f"py_{py.name}","s":"pass","d":"Has logic"}); p+=1

        success = f == 0
        feedback = "\n".join(f"- {fix}" for fix in fixes) if fixes else "All smoke tests passed."
        return SmokeTesterOutput(success=success, tests_passed=p, tests_failed=f, results=r, fix_feedback=feedback, categories_failed=sorted(cats))
