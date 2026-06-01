import json
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.core.archetype import ArchetypeClassifier, ProductArchetype, DeliveryArchitecture

logger = logging.getLogger(__name__)


def _extract_json_object(raw: str):
    """Best-effort extraction of a JSON object from an LLM response.

    Handles models that wrap JSON in prose ("Here is the spec: {...}"), markdown
    fences, or trailing commentary. Returns the parsed dict, or None if no valid
    JSON object can be recovered."""
    if not raw:
        return None
    text = raw.strip()

    # Strip a leading ```json / ``` fence and its closing fence if present.
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()

    # Fast path: the whole thing is JSON.
    try:
        return json.loads(text)
    except Exception:
        pass

    # Recover the outermost {...} object by scanning brace depth (string-aware).
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    return None
    return None

_ARCHITECT_SYSTEM_DEFAULT = """You are a senior software architect. Analyse the user requirement and produce a complete technical specification that drives every downstream agent.

The spec_summary and contract fields are the most critical — every other agent reads them to know what to build.

spec_summary must be a complete technical brief covering ALL of:
- Exactly what the product does and all its features
- For web apps/games: every page, mechanic, character/unit, UI layout, color scheme
- For APIs: every endpoint, method, request/response schema, auth method, error handling
- For CLIs: every command, flag, argument, expected output, and exit codes
- For Python packages: public API surface, modules, classes, functions
- For services: startup, configuration, dependencies, health/readiness requirements
- Data models, persistence strategy, and any external integrations

contract is the machine-readable definition of "done" — downstream agents obey it exactly:
- ui_layer: "html_css" | "react" | "cli" | "none"  (controls whether UI Designer runs)
- entry_points: the actual files a user runs/opens to start the product
- required_artifacts: every file that must exist with path and kind
- interface_contracts: HTTP endpoints, CLI commands, game mechanics, UI interactions
- validation_rules: specific, checkable conditions that define a passing build
- stack_family: "web" | "python" | "node" | "fullstack" | "any"

file_plan descriptions MUST name the actual functions, classes, routes, and data models in each file.
For non-web builds: include setup.py/pyproject.toml/package.json, entry points, and test files.
For web builds: include index.html, styles.css, and all JS files.

OUTPUT: Valid JSON only. No markdown. No prose.
{
  "archetype": "single_page_app|multi_page_site|dashboard|game|tool|landing_page|admin_panel|docs_site|toy_app|api_server|cli_tool|python_package|node_service|fullstack_app|automation_script|database_schema",
  "product_type": "web_app|game_web|api_server|cli_tool|python_package|node_service|fullstack_app|automation_script|database_schema|other",
  "stack": "html5|react|vue|nodejs|python|fastapi|flask|express|other",
  "components": ["major feature or module names"],
  "tech_stack": {"frontend": "...", "backend": "...", "database": "...", "runtime": "..."},
  "contract": {
    "ui_layer": "html_css|react|cli|none",
    "stack_family": "web|python|node|fullstack|any",
    "entry_points": ["index.html", "main.py", "src/index.js"],
    "required_artifacts": [{"path": "file.ext", "kind": "source|config|schema|doc|test"}],
    "interface_contracts": [{"type": "ui_interaction|http_endpoint|cli_command|game_mechanic|python_api", "name": "...", "description": "..."}],
    "validation_rules": ["specific, checkable conditions — e.g. 'GET /health returns 200', 'python -m myapp --help exits 0'"]
  },
  "file_plan": [{"path": "filename.ext", "type": "source|config|schema|doc|test", "description": "specific functions/classes/routes/objects in this file"}],
  "spec_summary": "Complete technical brief: all features, mechanics, visual design, data models, interactions, interfaces",
  "risks": ["technical concerns"]
}"""


class ArchitectInput(BaseModel):
    build_id: str
    mode: str
    project_name: str
    requirement: str
    stack_target: str
    project_context_summary: str = ""   # injected from ProjectContext.context_summary
    source_dir: str = ""


class ArchitectOutput(BaseModel):
    success: bool
    error: str = ""
    spec_summary: str = ""
    components: list[str] = []
    tech_stack: dict = {}
    file_plan: list[dict] = []
    risks: list[str] = []
    archetype: ProductArchetype = ProductArchetype.SINGLE_PAGE_APP  # Added for sharing with other agents
    contract: dict = {}
    product_type: str = "web_app"
    structured_spec_path: str = ""
    file_plan_path: str = ""


class ArchitectAgent(BaseAgent[ArchitectInput, ArchitectOutput]):
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir
        self.archetype_classifier = ArchetypeClassifier()

    async def run(self, input_data: ArchitectInput) -> ArchitectOutput:
        # Step 1: Determine product archetype first with explicit constraints
        explicit_constraints = {
            "stack": input_data.stack_target
        }
        archetype, delivery_arch = self.archetype_classifier.classify_requirement(
            input_data.requirement, 
            explicit_constraints
        )
        contract = self.archetype_classifier.get_contract(archetype)
        
        context_section = ""
        if input_data.project_context_summary:
            context_section = (
                f"\nExisting Project Context (from folder scan):\n"
                f"{input_data.project_context_summary}\n"
                f"Source Directory: {input_data.source_dir or 'not set'}\n\n"
                "Use this context to tailor the file plan and avoid duplicating existing files.\n"
            )

        if input_data.stack_target and input_data.stack_target.lower() != "auto":
            stack_line = f"Stack Target (preferred): {input_data.stack_target}\n"
        else:
            stack_line = "Stack Target: Determine the best stack yourself based on the requirement.\n"

        req = input_data.requirement
        if len(req) > 2000:
            req = req[:2000] + "\n...[truncated for brevity]"
        
        # Add archetype-specific guidance to the prompt — contract-driven, stack-agnostic
        is_web = contract.stack_family == "web"
        if is_web:
            archetype_guidance = (
                f"\n\nDETECTED ARCHITECTURE: {archetype.value}\n"
                f"DELIVERY ARCHITECTURE: {delivery_arch.value}\n"
                f"STACK FAMILY: web\n"
                f"ARCHETYPE DESCRIPTION: {contract.description}\n"
                f"WEB FILE REQUIREMENTS: "
                f"{contract.min_html_files}-{contract.max_html_files or 'unlimited'} HTML files, "
                f"{contract.min_css_files}-{contract.max_css_files} CSS files, "
                f"{contract.min_js_files}-{contract.max_js_files or 'unlimited'} JS files.\n"
                f"REQUIRES NAVIGATION: {contract.requires_navigation}\n"
                f"REQUIRES FORMS: {contract.requires_forms}\n"
                f"REQUIRES CANVAS: {contract.requires_canvas}\n"
                f"REQUIRES INTERACTIVITY: {contract.requires_interactivity}\n"
                f"\nThese counts are TYPICAL for a {archetype.value} — treat them as guidance, not hard limits. "
                f"Use as many files as the product genuinely needs. "
                f"Set contract.ui_layer to 'html_css' or 'react' and contract.stack_family='web'. "
                f"Make sure contract.required_artifacts and contract.validation_rules fully describe what 'done' means — "
                f"those drive the QA agents."
            )
        else:
            # Non-web: stack-family guidance
            stack_family = contract.stack_family
            required_patterns = ", ".join(contract.required_file_patterns) if contract.required_file_patterns else "determined by stack"
            archetype_guidance = (
                f"\n\nDETECTED ARCHITECTURE: {archetype.value}\n"
                f"DELIVERY ARCHITECTURE: {delivery_arch.value}\n"
                f"STACK FAMILY: {stack_family}\n"
                f"ARCHETYPE DESCRIPTION: {contract.description}\n"
                f"REQUIRED FILE PATTERNS: {required_patterns}\n"
                f"MINIMUM SOURCE FILES: {contract.min_source_files}\n"
                f"\nCRITICAL CONTRACT RULES for {stack_family} builds:\n"
            )
            if stack_family == "python":
                archetype_guidance += (
                    "- Set contract.ui_layer='none' and contract.stack_family='python'\n"
                    "- entry_points must name the actual Python file to run (e.g. 'main.py', 'app.py')\n"
                    "- required_artifacts must include requirements.txt and all .py source files\n"
                    "- interface_contracts must list every function/class/endpoint in the public API\n"
                    "- validation_rules must include: 'python <entrypoint> --help exits 0' or 'uvicorn app:app starts'\n"
                    "- file_plan must include: entry point, models, routes/handlers, config, requirements.txt\n"
                )
            elif stack_family == "node":
                archetype_guidance += (
                    "- Set contract.ui_layer='none' and contract.stack_family='node'\n"
                    "- entry_points must name the main JS/TS file (e.g. 'index.js', 'server.js')\n"
                    "- required_artifacts must include package.json (with scripts.start) and all source files\n"
                    "- interface_contracts must list every route/endpoint/export\n"
                    "- validation_rules must include: 'npm start succeeds' and key endpoint checks\n"
                )
            elif stack_family == "fullstack":
                archetype_guidance += (
                    "- Set contract.ui_layer='react' or 'html_css' (whichever the frontend uses)\n"
                    "- Set contract.stack_family='fullstack'\n"
                    "- entry_points must list BOTH the frontend entry AND backend entry\n"
                    "- required_artifacts must cover both frontend and backend files\n"
                    "- file_plan must have a clear frontend/ and backend/ or server/ split\n"
                )
            elif stack_family == "any":
                archetype_guidance += (
                    "- Set contract.stack_family='any'\n"
                    "- Set contract.ui_layer='cli' if this is a terminal tool, else 'none'\n"
                    "- entry_points must name the file to run\n"
                    "- validation_rules must include how to run and verify the tool works\n"
                )
        
        # ── Offline memory: retrieve relevant lessons + past project context ──
        memory_section = ""
        try:
            from backend.core.memory import get_memory
            mem = get_memory()
            lessons = mem.search(input_data.requirement, k=3, kind="lesson")
            projects = mem.search(input_data.requirement, k=2, kind="project")
            if lessons:
                memory_section += "\n\nRELEVANT ENGINEERING LESSONS (apply where they fit):\n" + \
                    "\n".join(f"- {l}" for l in lessons)
            if projects:
                memory_section += "\n\nCONTEXT FROM PAST BUILDS:\n" + \
                    "\n".join(f"- {p}" for p in projects)
        except Exception:
            pass

        prompt = (
            f"Project Name: {input_data.project_name}\n"
            f"{stack_line}"
            f"Requirement:\n{req}\n"
            f"{context_section}"
            f"{archetype_guidance}"
            f"{memory_section}\n"
            "Produce the structured specification JSON now."
        )

        max_retries = 3
        for attempt in range(max_retries):
            extra = ""
            if attempt == 0:
                extra = f"\n\nCRITICAL: Follow the {archetype.value} archetype ({contract.description}) requirements exactly."
                if is_web:
                    extra += f" Plan {contract.min_html_files}-{contract.max_html_files or 'unlimited'} HTML, exactly {contract.min_css_files} CSS (styles.css), {contract.min_js_files}+ JS files."
                else:
                    extra += f" Stack family is '{contract.stack_family}'. Plan at least {contract.min_source_files} source files."
            else:
                extra = (
                    f"\n\nCRITICAL CORRECTION: Your previous attempt did not meet the {archetype.value} archetype requirements. "
                )
                if is_web:
                    extra += f"File counts required: {contract.min_html_files}-{contract.max_html_files or 'unlimited'} HTML, {contract.min_css_files}-{contract.max_css_files} CSS, {contract.min_js_files}-{contract.max_js_files or 'unlimited'} JS."
                else:
                    extra += f"Produce at least {contract.min_source_files} source files for stack_family='{contract.stack_family}'."

            response = await self.provider.complete(
                ModelRequest(
                    prompt=prompt + extra,
                    system_prompt=load_system_prompt("architect", _ARCHITECT_SYSTEM_DEFAULT),
                    temperature=0.3 - (attempt * 0.05),
                    max_tokens=4096 if attempt > 0 else 2048,
                )
            )
            if not response.success:
                return ArchitectOutput(success=False, error=response.error)

            data = _extract_json_object(response.content)
            if data is None:
                logger.error("Architect JSON parse failed (attempt %d). Raw head: %s", attempt + 1, response.content[:120])
                if attempt == max_retries - 1:
                    return ArchitectOutput(
                        success=False,
                        error=f"Architect output was not valid JSON after {max_retries} attempts. Raw output: {response.content[:500]}"
                    )
                continue

            # Validate file plan against contract
            file_plan = data.get("file_plan", [])
            if not isinstance(file_plan, list):
                if attempt == max_retries - 1:
                    return ArchitectOutput(success=False, error="file_plan must be a list")
                continue

            valid_files = [f for f in file_plan if isinstance(f, dict) and f.get("path") and f.get("path") != "relative/path/to/file.ext"]
            min_files = 4 if is_web else contract.min_source_files
            if len(valid_files) >= min_files:
                break  # good enough
            logger.warning("Architect attempt %d: only %d files (need %d), retrying...", attempt + 1, len(valid_files), min_files)
            if attempt == max_retries - 1:
                logger.warning("Architect reached max retries with %d files — using as-is.", len(valid_files))
                break

        # Ensure required keys exist with fallbacks
        if "spec_summary" not in data:
            data["spec_summary"] = input_data.requirement[:200]
        if "components" not in data:
            data["components"] = [f.get("path","") for f in data.get("file_plan", [])]
        if "tech_stack" not in data:
            stack = data.get("stack", input_data.stack_target or "html5")
            data["tech_stack"] = {"frontend": stack, "backend": None, "database": None}
        if "file_plan" not in data or not data["file_plan"]:
            logger.error("Architect JSON missing file_plan")
            return ArchitectOutput(success=False, error="Architect did not produce a file plan")
        if "risks" not in data:
            data["risks"] = []
        if "contract" not in data:
            stack = data.get("stack", "")
            detected_arch = data.get("archetype", "")
            if is_web:
                ui_layer = "html_css"
                stack_fam = "web"
            elif "react" in stack.lower() or "vue" in stack.lower():
                ui_layer = stack.lower().split()[0] if stack else "react"
                stack_fam = "web"
            elif "python" in stack.lower() or "fastapi" in stack.lower() or "flask" in stack.lower():
                ui_layer = "none"
                stack_fam = "python"
            elif "node" in stack.lower() or "express" in stack.lower():
                ui_layer = "none"
                stack_fam = "node"
            else:
                ui_layer = "none"
                stack_fam = "any"
            data["contract"] = {
                "ui_layer": ui_layer,
                "stack_family": stack_fam,
                "entry_points": [f.get("path", "") for f in data.get("file_plan", [])[:1]],
                "required_artifacts": [{"path": f.get("path", ""), "kind": "source"} for f in data.get("file_plan", [])],
                "interface_contracts": [],
                "validation_rules": ["All planned files exist", "Core features from spec_summary are implemented"]
            }
        # Ensure stack_family is in contract
        if "stack_family" not in data.get("contract", {}):
            data["contract"]["stack_family"] = contract.stack_family

        # Normalize contract list-fields — the LLM sometimes emits a JSON object
        # where an array is expected. Downstream agents slice/iterate these, and on
        # Python 3.12+ `dict[:N]` raises KeyError(slice). Coerce to lists here so every
        # consumer (Coder, SmokeTester, Validator) gets a clean shape.
        def _listify(v):
            if v is None:
                return []
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                return list(v.values())
            return [v]

        _c = data["contract"]
        for _field in ("entry_points", "required_artifacts", "interface_contracts", "validation_rules"):
            _c[_field] = _listify(_c.get(_field))
        # required_artifacts entries must be dicts with a path
        _norm_artifacts = []
        for _a in _c["required_artifacts"]:
            if isinstance(_a, dict):
                _norm_artifacts.append(_a)
            elif isinstance(_a, str):
                _norm_artifacts.append({"path": _a, "kind": "source"})
        _c["required_artifacts"] = _norm_artifacts
        # entry_points must be a list of strings
        _c["entry_points"] = [e if isinstance(e, str) else (e.get("path", "") if isinstance(e, dict) else str(e)) for e in _c["entry_points"]]

        if "product_type" not in data:
            arch = data.get("archetype", "")
            if "game" in arch: data["product_type"] = "game_web"
            elif "api_server" in arch: data["product_type"] = "api_server"
            elif "cli_tool" in arch: data["product_type"] = "cli_tool"
            elif "python_package" in arch: data["product_type"] = "python_package"
            elif "node_service" in arch: data["product_type"] = "node_service"
            elif "fullstack" in arch: data["product_type"] = "fullstack_app"
            elif "automation" in arch: data["product_type"] = "automation_script"
            elif "database" in arch: data["product_type"] = "database_schema"
            else: data["product_type"] = "web_app"

        self.build_dir.mkdir(parents=True, exist_ok=True)

        spec_path = self.build_dir / "structured_spec.md"
        spec_content = f"# {input_data.project_name} — Structured Spec\n\n"
        spec_content += f"## Summary\n{data.get('spec_summary', '')}\n\n"
        spec_content += f"## Stack\n{json.dumps(data.get('tech_stack', {}), indent=2)}\n\n"
        spec_content += f"## Components\n" + "\n".join(f"- {c}" for c in data.get("components", [])) + "\n\n"
        spec_content += f"## Risks\n" + "\n".join(f"- {r}" for r in data.get("risks", [])) + "\n"
        spec_path.write_text(spec_content, encoding="utf-8")

        plan_path = self.build_dir / "file_plan.json"
        plan_path.write_text(json.dumps(data.get("file_plan", []), indent=2), encoding="utf-8")

        return ArchitectOutput(
            success=True,
            contract=data.get("contract", {}),
            product_type=data.get("product_type", "web_app"),
            spec_summary=data.get("spec_summary", ""),
            components=data.get("components", []),
            tech_stack=data.get("tech_stack", {}),
            file_plan=data.get("file_plan", []),
            risks=data.get("risks", []),
            archetype=archetype,  # Set the archetype for sharing with other agents
            structured_spec_path=str(spec_path),
            file_plan_path=str(plan_path),
        )
