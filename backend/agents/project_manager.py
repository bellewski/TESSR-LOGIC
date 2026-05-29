"""
Project Manager agent that mediates between other agents and enforces architectural decisions.
Resolves conflicts and ensures agents follow the established architecture and constraints.
"""

import logging
from pathlib import Path
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest
from backend.core.archetype import ArchetypeClassifier, ProductArchetype

logger = logging.getLogger(__name__)

_PROJECT_MANAGER_SYSTEM_DEFAULT = """You are a technical project manager reviewing an architect's file plan before the build starts.

Check if the file plan violates archetype constraints:
1. Too many HTML files for archetypes that require only one (single_page_app, dashboard, game, tool)
2. A plain HTML/JS stack being asked to use a framework
3. Missing critical files for the project type

If the plan is correct, return has_conflicts: false.
If there are issues, return the corrected file plan.

Output ONLY valid JSON:
{"has_conflicts": true|false, "resolution": "brief explanation", "corrected_file_plan": [...] or null}"""

class ProjectManagerInput(BaseModel):
    build_id: str
    project_name: str
    requirement: str
    stack_target: str
    archetype: ProductArchetype
    file_plan: list[dict]
    conflict_type: str
    conflict_details: str
    agent_outputs: dict = {}

class ProjectManagerOutput(BaseModel):
    success: bool
    resolution: str = ""
    corrected_file_plan: list[dict] = []
    agent_guidance: dict = {}
    error: str = ""

class ProjectManagerAgent(BaseAgent[ProjectManagerInput, ProjectManagerOutput]):
    """Mediates between agents and enforces architectural compliance."""
    
    def __init__(self, provider: BaseModelProvider, build_dir: Path):
        self.provider = provider
        self.build_dir = build_dir
        self.archetype_classifier = ArchetypeClassifier()

    async def run(self, input_data: ProjectManagerInput) -> ProjectManagerOutput:
        """Resolve architectural conflicts and provide corrective guidance."""
        
        contract = self.archetype_classifier.get_contract(input_data.archetype)
        
        prompt = (
            f"PROJECT: {input_data.project_name}\n"
            f"REQUIREMENT: {input_data.requirement}\n"
            f"STACK TARGET: {input_data.stack_target}\n"
            f"ESTABLISHED ARCHITECTURE: {input_data.archetype.value}\n"
            f"ARCHETYPE CONTRACT: {contract.description}\n"
            f"FILE CONSTRAINTS: {contract.min_html_files}-{contract.max_html_files or 'unlimited'} HTML, "
            f"{contract.min_css_files}-{contract.max_css_files} CSS, "
            f"{contract.min_js_files}-{contract.max_js_files or 'unlimited'} JS\n"
            f"REQUIRES NAVIGATION: {contract.requires_navigation}\n"
            f"REQUIRES CANVAS: {contract.requires_canvas}\n"
            f"CURRENT FILE PLAN: {len(input_data.file_plan)} files\n"
            f"CONFLICT TYPE: {input_data.conflict_type}\n"
            f"CONFLICT DETAILS: {input_data.conflict_details}\n\n"
            f"CURRENT FILES:\n"
        )
        
        for i, file in enumerate(input_data.file_plan):
            prompt += f"{i+1}. {file.get('path', 'unknown')} - {file.get('description', 'no description')}\n"
        
        prompt += "\nResolve this conflict by enforcing the established architecture. Provide specific corrective actions."
        
        try:
            response = await self.provider.complete(
                ModelRequest(
                    prompt=prompt,
                    system_prompt=load_system_prompt("project_manager", _PROJECT_MANAGER_SYSTEM_DEFAULT),
                    temperature=0.1,  # Low temperature for consistent decisions
                    max_tokens=2048,
                )
            )
            
            if not response.success:
                return ProjectManagerOutput(
                    success=False,
                    error=f"Project Manager failed: {response.error}"
                )
            
            # Parse the resolution and generate corrected outputs
            resolution = response.content.strip()
            
            # Generate corrected file plan based on archetype constraints
            corrected_file_plan = self._generate_corrected_file_plan(
                input_data.file_plan, 
                contract, 
                input_data.archetype
            )
            
            # Generate specific guidance for each agent
            agent_guidance = self._generate_agent_guidance(
                input_data.conflict_type,
                contract,
                input_data.stack_target
            )
            
            return ProjectManagerOutput(
                success=True,
                resolution=resolution,
                corrected_file_plan=corrected_file_plan,
                agent_guidance=agent_guidance
            )
            
        except Exception as e:
            logger.error(f"Project Manager error: {e}")
            return ProjectManagerOutput(
                success=False,
                error=f"Project Manager error: {str(e)}"
            )
    
    def _generate_corrected_file_plan(self, original_plan: list[dict], contract, archetype: ProductArchetype) -> list[dict]:
        """Correct file plan to respect archetype constraints while preserving intent."""
        corrected = list(original_plan)  # start with full plan

        # Count HTML files
        html_files = [f for f in corrected if f.get("path", "").endswith(".html")]
        max_html = contract.max_html_files

        # Only trim if we exceed the max AND max is a hard limit (not None)
        if max_html and len(html_files) > max_html:
            # Keep only the first max_html HTML files
            keep_html = {f["path"] for f in html_files[:max_html]}
            corrected = [f for f in corrected if not f.get("path","").endswith(".html") or f["path"] in keep_html]
            logger.info("PM: trimmed HTML files from %d to %d for %s", len(html_files), max_html, archetype.value)

        # Ensure styles.css exists
        if not any(f.get("path","") == "styles.css" for f in corrected):
            corrected.append({"path": "styles.css", "description": "Shared styles", "type": "source"})

        # Ensure app.js exists
        if not any(f.get("path","") == "app.js" for f in corrected):
            corrected.append({"path": "app.js", "description": "Application logic", "type": "source"})

        return corrected
    
    def _generate_agent_guidance(self, conflict_type: str, contract, stack_target: str) -> dict:
        """Generate specific guidance for agents based on conflict type."""
        guidance = {}
        
        if "file_count" in conflict_type.lower():
            guidance["architect"] = (
                f"Reduce file plan to match {contract.archetype.value} constraints: "
                f"max {contract.max_html_files or 1} HTML files. "
                f"Consolidate multiple pages into single page with different sections."
            )
            guidance["coder"] = (
                f"Generate only the corrected file count. "
                f"Do not create extra HTML files beyond the architectural limit."
            )
        
        if "jsx" in conflict_type.lower() or "react" in conflict_type.lower():
            guidance["coder"] = (
                f"STACK VIOLATION: Target is {stack_target} - rewrite all JavaScript "
                f"to use vanilla DOM APIs only. No imports, no JSX, no frameworks."
            )
        
        if "navigation" in conflict_type.lower() and not contract.requires_navigation:
            guidance["architect"] = "Remove navigation requirements from file plan."
            guidance["coder"] = "Do not generate navigation elements or links between pages."
        
        return guidance
