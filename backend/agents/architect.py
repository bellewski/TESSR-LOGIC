import json
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.core.archetype import ArchetypeClassifier, ProductArchetype, DeliveryArchitecture

logger = logging.getLogger(__name__)

_ARCHITECT_SYSTEM_DEFAULT = """You are a senior software architect. Analyse the user requirement and produce a complete technical specification that drives every downstream agent.

The spec_summary and contract fields are the most critical — every other agent reads them to know what to build.

spec_summary MUST END with a section titled exactly "SUCCESS CRITERIA:" — a numbered list of 3-8 concrete, user-visible capabilities that define done. Each criterion must be verifiable by looking at the finished product (e.g. "1. Clicking the cat increases the coin counter", "2. At least two upgrades can be purchased and increase coins per click", "3. A reset button returns coins and upgrades to zero"). Derive them ONLY from the user requirement — never invent features that were not asked for.

spec_summary must be a complete technical brief:
- Exactly what the product does and all its features
- For games: every mechanic, all characters/units with their stats, progression system, UI layout
- For web apps: every page, form, interactive element, color scheme
- For APIs: every endpoint, request/response format, data models, auth method
- For CLIs: every command, argument, and expected output
- Visual design: colors, theme, mood, layout style

contract must define what "done" means:
- entry_points: the main files to run/open
- required_artifacts: every file that must exist with its kind (source/config/schema/doc)
- interface_contracts: HTTP endpoints, CLI commands, game mechanics, UI interactions
- validation_rules: what the QA agents should check
- ui_layer: "html_css" | "react" | "cli" | "none"

file_plan descriptions must name the actual functions, classes, game objects, API routes in each file.

OUTPUT: Valid JSON only. No markdown. No prose.
{
  "archetype": "single_page_app|multi_page_site|dashboard|game|tool|api_server|cli_tool|database_app|fullstack_app|other",
  "product_type": "web_app|game_web|api_server|cli_tool|desktop_app|database_schema|mobile_backend|automation_script|other",
  "stack": "html5|react|vue|nodejs|python|fastapi|flask|express|other",
  "components": ["major feature or module names"],
  "tech_stack": {"frontend": "...", "backend": "...", "database": "...", "runtime": "..."},
  "contract": {
    "ui_layer": "html_css|react|cli|none",
    "entry_points": ["index.html", "main.py", "app.js"],
    "required_artifacts": [{"path": "file.ext", "kind": "source|config|schema|doc"}],
    "interface_contracts": [{"type": "ui_interaction|http_endpoint|cli_command|game_mechanic", "name": "...", "description": "..."}],
    "validation_rules": ["what must be true for this build to be complete"]
  },
  "file_plan": [{"path": "filename.ext", "type": "source", "description": "specific functions/classes/routes/objects in this file"}],
  "spec_summary": "Complete technical brief: all features, mechanics, visual design, data, interactions",
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
        
        # Add archetype-specific guidance to the prompt
        archetype_guidance = (
            f"\n\nDETECTED ARCHITECTURE: {archetype.value}\n"
            f"DELIVERY ARCHITECTURE: {delivery_arch.value}\n"
            f"ARCHETYPE DESCRIPTION: {contract.description}\n"
            f"FILE REQUIREMENTS: "
            f"{contract.min_html_files}-{contract.max_html_files or 'unlimited'} HTML files, "
            f"{contract.min_css_files}-{contract.max_css_files} CSS files, "
            f"{contract.min_js_files}-{contract.max_js_files or 'unlimited'} JS files.\n"
            f"REQUIRES NAVIGATION: {contract.requires_navigation}\n"
            f"REQUIRES FORMS: {contract.requires_forms}\n"
            f"REQUIRES CANVAS: {contract.requires_canvas}\n"
            f"REQUIRES INTERACTIVITY: {contract.requires_interactivity}\n"
            f"\nCRITICAL: Design the file plan to match these exact requirements. "
            f"Do NOT exceed the maximum file counts for this archetype."
        )
        
        prompt = (
            f"Project Name: {input_data.project_name}\n"
            f"{stack_line}"
            f"Requirement:\n{req}\n"
            f"{context_section}"
            f"{archetype_guidance}\n"
            "Produce the structured specification JSON now."
        )

        max_retries = 3
        for attempt in range(max_retries):
            extra = ""
            if attempt == 0:
                extra = f"\n\nCRITICAL: Follow the {archetype.value} archetype requirements exactly. Plan the correct number of files for this archetype. Use EXACTLY ONE shared styles.css and appropriate JS files."
            else:
                extra = f"\n\nCRITICAL CORRECTION: Your previous attempt did not match the {archetype.value} archetype requirements. Follow the file count requirements exactly: {contract.min_html_files}-{contract.max_html_files or 'unlimited'} HTML, {contract.min_css_files}-{contract.max_css_files} CSS, {contract.min_js_files}-{contract.max_js_files or 'unlimited'} JS files."
            response = await self.provider.complete(
                ModelRequest(
                    prompt=prompt + extra,
                    system_prompt=load_system_prompt("architect", _ARCHITECT_SYSTEM_DEFAULT),
                    temperature=0.3 - (attempt * 0.05),  # lower temp = more deterministic
                    max_tokens=4096 if attempt > 0 else 2048,
                    response_format="json",  # Ollama constrains generation to valid JSON
                )
            )
            if not response.success:
                return ArchitectOutput(success=False, error=response.error)

            try:
                content = response.content.strip()
                if content.startswith("```"):
                    lines = content.split("\n")
                    content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                data = json.loads(content)
            except Exception as e:
                logger.error("Architect JSON parse failed (attempt %d): %s", attempt + 1, e)
                if attempt == max_retries - 1:
                    return ArchitectOutput(
                        success=False,
                        error=f"Architect output was not valid JSON after {max_retries} attempts: {str(e)[:200]}. Raw output: {response.content[:500]}"
                    )
                continue

            # Validate file plan size early to retry
            file_plan = data.get("file_plan", [])
            if isinstance(file_plan, list):
                tech_stack = data.get("tech_stack", {})
                is_web = (
                    isinstance(tech_stack, dict) and
                    ("html" in str(tech_stack.get("frontend", "")).lower() or
                     "vanilla" in str(tech_stack.get("frontend", "")).lower() or
                     "web" in str(tech_stack.get("frontend", "")).lower())
                )
                valid_files = [f for f in file_plan if isinstance(f, dict) and f.get("path") and f.get("path") != "relative/path/to/file.ext"]
                if is_web and len(valid_files) >= 4:
                    break  # success
                elif is_web:
                    logger.warning("Architect attempt %d planned only %d files (need >=4), retrying...", attempt + 1, len(valid_files))
                    if attempt == max_retries - 1:
                        # Fallback: use whatever the model produced as-is
                        logger.warning("Architect reached max retries with %d files. Using as-is.", len(valid_files))
                        break  # proceed with what we have
                    continue
                else:
                    break  # non-web app, any file count ok
            else:
                if attempt == max_retries - 1:
                    return ArchitectOutput(success=False, error="file_plan must be a list")
                continue

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

        # Guarantee a SUCCESS CRITERIA section exists in spec_summary so the
        # Coder implements against it and the Validator verifies against it.
        _spec = data.get("spec_summary", "") or ""
        if "SUCCESS CRITERIA" not in _spec.upper():
            _req = (input_data.requirement or "").strip()
            data["spec_summary"] = _spec.rstrip() + (
                "\n\nSUCCESS CRITERIA:\n"
                "1. Every capability stated in the requirement below is present and working:\n"
                + _req + "\n"
                "2. All interactive elements respond to user input.\n"
                "3. No placeholder text, empty sections, or dead controls."
            )
            logger.warning("Architect: spec_summary lacked SUCCESS CRITERIA — appended requirement-derived fallback")

        # -- Deterministic plan completion ---------------------------------
        # Small models sometimes plan a lone HTML file. For web builds,
        # guarantee the plan includes at least one CSS and one JS file so
        # downstream agents (UI Designer, Coder) and QA minimums line up.
        _plan = data.get("file_plan", [])
        _stack_str = str(data.get("tech_stack", {})).lower()
        _is_web_plan = (
            any(str(f.get("path", "")).endswith(".html") for f in _plan if isinstance(f, dict))
            or "html" in _stack_str or "vanilla" in _stack_str or "web" in _stack_str
        )
        if _is_web_plan:
            _has_css = any(str(f.get("path", "")).endswith(".css") for f in _plan if isinstance(f, dict))
            _has_js = any(str(f.get("path", "")).endswith(".js") for f in _plan if isinstance(f, dict))
            if not _has_css:
                _plan.append({"path": "styles.css", "type": "style",
                              "description": "Shared stylesheet for all pages (theme applied by UI Designer)"})
                logger.warning("Architect plan completion: added missing styles.css to file plan")
            if not _has_js:
                _plan.append({"path": "app.js", "type": "source",
                              "description": "Interactive behavior: DOM event listeners and state updates implementing the requirement's core interactions (button clicks, counters, dynamic content). Must be linked from every HTML page via <script src=\'app.js\'></script>."})
                logger.warning("Architect plan completion: added missing app.js to file plan")
            data["file_plan"] = _plan
        if "contract" not in data:
            data["contract"] = {
                "ui_layer": "html_css" if data.get("stack","").startswith("html") else "none",
                "entry_points": [f.get("path","") for f in data.get("file_plan",[])[:1]],
                "required_artifacts": [{"path": f.get("path",""), "kind": "source"} for f in data.get("file_plan",[])],
                "interface_contracts": [],
                "validation_rules": ["All planned files exist", "Core features from spec_summary are implemented"]
            }
        if "product_type" not in data:
            arch = data.get("archetype","")
            if "game" in arch: data["product_type"] = "game_web"
            elif "api" in arch: data["product_type"] = "api_server"
            elif "cli" in arch: data["product_type"] = "cli_tool"
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
