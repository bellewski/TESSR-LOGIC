import json
import logging
from pydantic import BaseModel
from backend.agents.base import BaseAgent
from backend.agents.prompt_loader import load_system_prompt
from backend.providers.base import BaseModelProvider, ModelRequest

logger = logging.getLogger(__name__)

_HIRING_MANAGER_SYSTEM_DEFAULT = """You are the Hiring Manager for a multi-agent build pipeline. Your ONLY job is to recommend the optimal pipeline position for a new agent based on its role description.

ROLE BOUNDARY (CRITICAL):
- You ONLY analyze the new agent's purpose and recommend where it fits in the existing pipeline.
- You do NOT write code, evaluate code, or design systems — other agents handle that.
- You do NOT modify the descriptions or roles of existing agents.

PIPELINE CONTEXT:
The build pipeline runs agents in sequence. Each agent transforms the build state:

1. Architect — designs spec, success criteria, and file plan from user requirements
2. Project Manager — advisory review of the file plan (never removes files)
3. Coder — generates each source file (one model call per file)
4. File Consolidator — merges duplicate CSS/JS, repairs asset links and layout
5. UI Designer — selects a design-library theme and writes custom overrides
6. Hardener — regex + LLM security scan of generated code
7. Fixer — applies security remediations directly to affected files
8. Validator — verifies each success criterion against the generated files
9. Builder — installs dependencies, builds the project, produces artifacts
10. Smoke Tester — deterministic content, wiring, and structure checks

PLACEMENT RULES:
- If the new agent analyzes or improves CODE (e.g., linter, formatter, type checker, optimizer), place it between Coder and Hardener (position 3), or between Hardener and Validator (position 4).
- If the new agent tests or validates OUTPUT (e.g., performance tester, accessibility checker, screenshot comparator), place it after Smoke Tester (position 7+).
- If the new agent gathers or enriches REQUIREMENTS (e.g., research agent, spec expander, dependency analyzer), place it before Architect (position 0-1).
- If the new agent modifies or patches CODE (e.g., bug fixer, migration agent, polyfill injector), place it between Coder and Hardener (position 3).
- If the new agent is a general reviewer or auditor, place it between Validator and Builder (position 5).

OUTPUT FORMAT — ONLY return JSON, nothing else:
{
  "recommended_position": <integer>,
  "rationale": "<1-2 sentence explanation>",
  "placement": "<before|after> <existing_agent_name>",
  "confidence": "high|medium|low"
}
"""


class HiringManagerInput(BaseModel):
    new_agent_name: str
    new_agent_description: str
    new_agent_type: str
    current_pipeline: list[dict]  # Each dict: {name, agent_type, position, description}


class HiringManagerOutput(BaseModel):
    success: bool
    error: str = ""
    recommended_position: int = 0
    rationale: str = ""
    placement: str = ""
    confidence: str = "low"


class HiringManagerAgent(BaseAgent[HiringManagerInput, HiringManagerOutput]):
    def __init__(self, provider: BaseModelProvider):
        self.provider = provider

    async def run(self, input_data: HiringManagerInput) -> HiringManagerOutput:
        pipeline_json = json.dumps(input_data.current_pipeline, indent=2)

        prompt = (
            f"New Agent Name: {input_data.new_agent_name}\n"
            f"New Agent Type: {input_data.new_agent_type}\n"
            f"New Agent Description:\n{input_data.new_agent_description}\n\n"
            f"Current Pipeline:\n{pipeline_json}\n\n"
            "Recommend the optimal position for this new agent in the pipeline. "
            "ONLY output the JSON object specified in your instructions. "
            "NO introductions, NO explanations outside the JSON."
        )

        response = await self.provider.complete(
            ModelRequest(
                prompt=prompt,
                system_prompt=load_system_prompt("hiring_manager", _HIRING_MANAGER_SYSTEM_DEFAULT),
                temperature=0.2,
                max_tokens=1024,
                response_format="json",
            )
        )

        if not response.success:
            return HiringManagerOutput(success=False, error=response.error)

        try:
            content = response.content.strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
            data = json.loads(content)
            return HiringManagerOutput(
                success=True,
                recommended_position=data.get("recommended_position", 99),
                rationale=data.get("rationale", ""),
                placement=data.get("placement", ""),
                confidence=data.get("confidence", "low"),
            )
        except Exception as e:
            logger.warning("HiringManager JSON parse failed: %s", e)
            # Fallback: estimate based on agent_type keyword matching
            desc = input_data.new_agent_description.lower()
            pos = 99
            if any(k in desc for k in ("requirement", "research", "spec", "gather", "analyze request")):
                pos = 0
            elif any(k in desc for k in ("code", "lint", "format", "type check", "optimize", "refactor", "patch", "fix")):
                pos = 3
            elif any(k in desc for k in ("security", "harden", "vulnerability", "scan")):
                pos = 4
            elif any(k in desc for k in ("validate", "compliance", "spec check", "review")):
                pos = 5
            elif any(k in desc for k in ("test", "smoke", "runtime", "performance", "accessibility", "screenshot")):
                pos = 7
            else:
                pos = 5  # default: reviewer slot

            return HiringManagerOutput(
                success=True,
                recommended_position=pos,
                rationale=f"Fallback placement based on keyword matching in description. ({e})",
                placement="estimated from keywords",
                confidence="low",
            )
