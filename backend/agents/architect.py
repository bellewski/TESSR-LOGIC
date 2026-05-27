import json
import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.orchestrator.event_bus import event_bus
from backend.core.archetype import ArchetypeClassifier, ProductArchetype, DeliveryArchitecture

logger = logging.getLogger(__name__)

_ARCHITECT_SYSTEM_DEFAULT = """You are a senior software architect. Your ONLY job is to design the project specification based on the user's requirement.

ARCHITECTURE-FIRST DESIGN (CRITICAL):
1. FIRST determine the product archetype (landing page, single-page app, multi-page site, dashboard, game, docs, admin panel, tool, or toy app).
2. THEN design the file structure to match that archetype's requirements.
3. NEVER use generic multi-page patterns for single-page requirements.

ARCHETYPE-SPECIFIC RULES:
- LANDING PAGE: 1 HTML file, 1 CSS, optional 1 JS. Focus on marketing content and forms.
- SINGLE-PAGE APP: 1 HTML file, 1 CSS, 1+ JS. Dynamic content within one page.
- MULTI-PAGE SITE: 2+ HTML files, 1 CSS, 1+ JS. Navigation between pages required.
- DASHBOARD: 1 HTML file, 1 CSS, 1-3 JS. Data visualization and controls.
- GAME: 1 HTML file with canvas, 1 CSS, 1-3 JS. Interactive gameplay.
- DOCS SITE: 3+ HTML files, 1 CSS, 1-2 JS. Documentation with navigation.
- ADMIN PANEL: 1-5 HTML files, 1 CSS, 1-3 JS. Forms and data management.
- TOOL: 1 HTML file, 1 CSS, 1-2 JS. Specific utility functionality.
- TOY APP: 1-3 HTML files, 1 CSS, 1-2 JS. Simple demo or experiment.

QUALITY STANDARDS (non-negotiable):
1. Every website MUST plan for visual stunningness: gradients, shadows, animations, card layouts, hero sections.
2. Every page MUST have real content descriptions — not generic "page content" but specific features.
3. Navigation ONLY when archetype requires it (multi-page, docs, admin).
4. Every website MUST be responsive (mobile + desktop) in the CSS plan.
5. Plan for at least ONE interactive visualization or animated element per page.
6. File descriptions must be DETAILED: list specific UI elements, not just "page with content".

ROLE BOUNDARY (CRITICAL):
- You ONLY design the spec: stack, components, file plan, and risks.
- You do NOT write code, choose colors, pick libraries beyond stack selection, or dictate implementation details beyond what files exist.
- You do NOT assess security, code quality, or functional correctness — other agents handle that.
- If the requirement is missing, empty, or nonsensical, return {"error": "Missing or invalid requirement"} and nothing else.

ARCHETYPE COMPLIANCE (ABSOLUTE - NO EXCEPTIONS):
- The detected archetype file count requirements are MANDATORY, not suggestions
- NEVER exceed max_html_files for the archetype - this is a hard constraint
- ALWAYS respect requires_navigation, requires_canvas, requires_forms flags
- If you violate archetype constraints, the build will fail
- Dashboard = MAX 1 HTML file, Landing Page = MAX 1 HTML file, Game = MAX 1 HTML file
- Multi-page = MIN 2 HTML files, Docs = MIN 3 HTML files
- ARCHITECTURE DECISIONS ARE FINAL - do not second-guess the archetype classification

STACK SELECTION RULES (CRITICAL):
- HONOR THE USER'S EXPLICIT STACK REQUEST FIRST AND FOREMOST
- If user requests React, Vue, Angular, Node.js, or any specific framework: USE THAT FRAMEWORK
- If user specifies "React/Node.js/MongoDB": Plan a React frontend with Node.js backend
- If user specifies "HTML5" or "vanilla": Use plain HTML + CSS + JavaScript
- If stack_target is "auto": Choose appropriate stack based on requirement complexity
- NEVER override an explicit user stack preference with your own opinion
- The user's request is FINAL - your job is to implement it, not second-guess it

FILE_PLAN RULES (CRITICAL):
- Follow the archetype file count requirements EXACTLY - this overrides any other file planning rules
- For dashboard, landing page, game, tool archetypes: Use 1 HTML file with sections for different features
- For multi-page, docs, admin archetypes: Use multiple HTML files as specified by archetype
- NEVER create more HTML files than the archetype max_html_files allows
- ARCHETYPE CONSTRAINTS OVERRIDE ALL OTHER FILE PLANNING RULES
- CSS MUST be in EXACTLY ONE shared styles.css file that ALL HTML pages link to. NEVER create per-page CSS files.
- JavaScript MUST be in EXACTLY ONE shared app.js plus ONE data.js module. NEVER create per-page JS files like projects.js or mouse-catcher.js.
- ARCHETYPE CONSTRAINTS ARE THE FINAL AUTHORITY - they override all complexity-based file counting rules
- For data-driven features, include a .json data file or .js data module ONLY if archetype allows extra JS files.

UI DESIGN REQUIREMENTS:
- Plan styles.css with at least 15 CSS selectors: layout (flex/grid), colors, spacing, borders, shadows, responsive breakpoints.
- Include a dark mode design: CSS custom properties (--primary, --bg, --text) + a dark-mode toggle function in app.js.
- Responsive design is MANDATORY: include @media queries for mobile layouts.
- Every interactive element MUST have CSS hover states and JavaScript event handlers.

BLOCKCHAIN IDENTITY REQUIREMENTS:
- For blockchain identity systems: Plan single dashboard with tabbed sections for Registration, Login, Verification, MFA Setup, Recovery
- Include blockchain verification UI elements, secure authentication forms, and recovery process interfaces
- Use professional security-focused design with trust indicators and status badges
- Plan proper form validation and error handling UI components

DONE_WHEN:
{
  "spec_summary": "Concise overview of the project purpose and features.",
  "components": ["list of major components or features"],
  "tech_stack": {"languages": [...], "frameworks": [...], "libraries": [...], "build_tools": [...]},
  "file_plan": [
    {"path": "file/path.ext", "description": "What this file does.", "type": "source|doc|config"}
  ],
  "risks": ["potential risk 1", "potential risk 2"]
}

Guidelines:
- CRITICAL: Keep file_plan descriptions UNDER 15 WORDS.
- CRITICAL: DO NOT WRITE ANY CODE IN THIS JSON. Only plan the files.
- All source files must have type "source".
- Prefer static site or vanilla JS where possible.
- Plan for EXACTLY ONE SHARED styles.css that all HTML pages link to.
- Plan for EXACTLY ONE SHARED app.js for all logic.
- Do NOT copy paths literally; generate REAL filenames.
Return ONLY the raw JSON object. Do not wrap in markdown or add conversational text."""


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
            f"Do NOT exceed the maximum file counts for this archetype.\n"
            f"WARNING: YOU ARE THE ARCHITECT. DO NOT WRITE CODE. ONLY OUTPUT THE JSON PLAN."
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

            full_content = ""
            try:
                # Generate the actual output with thinking integrated
                enhanced_prompt = f"""Think step by step about this requirement, then output the JSON:

Requirement: {input_data.requirement}

First, briefly think about:
1. What type of product is this?
2. What are the key features needed?
3. What's the best file structure?

Then output the JSON specification.

{prompt + extra}"""

                req = ModelRequest(
                    prompt=enhanced_prompt,
                    system_prompt=load_system_prompt("architect", _ARCHITECT_SYSTEM_DEFAULT),
                    temperature=0.3 - (attempt * 0.05),
                    max_tokens=4096,
                )
                await event_bus.publish(input_data.build_id, {
                    "event_type": "agent_typing",
                    "phase": "architecting",
                    "payload": f">>> NEW BUILD: {input_data.project_name}\n"
                               f">>> DETECTED ARCHETYPE: {archetype.value}\n"
                               f">>> TASK: Drafting JSON architecture plan...\n\n"
                })
                
                full_content = ""
                async for chunk in self.provider.stream_complete(req):
                    full_content += chunk
                    await event_bus.publish(input_data.build_id, {
                        "event_type": "agent_typing",
                        "phase": "architecting",
                        "payload": chunk
                    })
                
                await event_bus.publish(input_data.build_id, {
                    "event_type": "agent_typing",
                    "phase": "architecting",
                    "payload": "\n\n>>> ✅ PLAN COMPLETE. Ready for Coder handoff.\n"
                })
            except Exception as e:
                return ArchitectOutput(success=False, error=str(e))

            try:
                content = full_content.strip()
                import re
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1)
                elif content.find('{') != -1 and content.rfind('}') != -1:
                    content = content[content.find('{'):content.rfind('}')+1]
                data = json.loads(content)
            except Exception as e:
                logger.error("Architect JSON parse failed (attempt %d): %s", attempt + 1, e)
                if attempt == max_retries - 1:
                    return ArchitectOutput(
                        success=False,
                        error=f"Architect output was not valid JSON after {max_retries} attempts: {str(e)[:200]}. Raw output: {full_content[:500]}"
                    )
                continue

            # Successfully parsed JSON, exit retry loop
            break

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
