import json
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.core.archetype import ArchetypeClassifier, ProductArchetype, DeliveryArchitecture

logger = logging.getLogger(__name__)

_ARCHITECT_SYSTEM_DEFAULT = """You are a senior software architect. You plan what to build — the Coder builds it, the UI Designer styles it.

YOUR ONLY JOB: Given a user requirement, output a JSON spec with:
- archetype (single_page_app | multi_page_site | dashboard | game | tool | admin_panel | landing_page)
- stack (html5 | react | vue | nodejs | python | fastapi)
- file_plan: list of files with path, type, description
- spec_summary: 2-3 sentences describing what to build
- risks: any technical concerns

ARCHETYPE FILE RULES (hard limits):
- single_page_app: 1 HTML, 1 CSS, 1-2 JS
- dashboard: 1 HTML, 1 CSS, 1-3 JS  
- game: 1 HTML with canvas, 1 CSS, 1-3 JS
- tool: 1 HTML, 1 CSS, 1-2 JS
- landing_page: 1 HTML, 1 CSS, 1 JS
- multi_page_site: 2-5 HTML, 1 CSS, 1-2 JS
- admin_panel: 1-5 HTML, 1 CSS, 1-3 JS

SPEC QUALITY RULES:
- File descriptions must be SPECIFIC: list exact UI elements, not "page with content"
- Every app needs at least one interactive element
- Describe the visual style intent in spec_summary so UI Designer knows the vibe
- If user mentions colors/theme, include that in spec_summary

OUTPUT: Valid JSON only. No explanations."""


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

        # Validate required keys
        required = ["spec_summary", "components", "tech_stack", "file_plan", "risks"]
        missing = [k for k in required if k not in data]
        if missing:
            logger.error("Architect JSON missing required keys: %s", missing)
            return ArchitectOutput(
                success=False,
                error=f"Architect output missing required keys: {missing}"
            )

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
            spec_summary=data.get("spec_summary", ""),
            components=data.get("components", []),
            tech_stack=data.get("tech_stack", {}),
            file_plan=data.get("file_plan", []),
            risks=data.get("risks", []),
            archetype=archetype,  # Set the archetype for sharing with other agents
            structured_spec_path=str(spec_path),
            file_plan_path=str(plan_path),
        )
