"""Prompt Studio service — LLM chat refinement + template management."""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.models.prompt_template import PromptTemplate
from backend.providers.ollama_provider import OllamaProvider
from backend.providers.base import ModelRequest

logger = logging.getLogger(__name__)

REFINER_SYSTEM = """You are a helpful requirement analyst working inside a software build tool called TESSR-LOGIC.

Your job is to help users clarify and structure their software idea through conversation.

In each reply:
1. Ask ONE focused follow-up question OR confirm that you have enough information.
2. After your question/comment, output a JSON block wrapped in <FIELDS> tags with the updated structured fields you have extracted so far.

The fields you must extract:
- what_to_build: clear one-sentence description
- target_audience: who will use this
- platform_type: web / mobile / desktop / CLI / API / automation / other
- key_features: comma-separated list of main features
- constraints: technical or business constraints
- tech_stack: preferred technologies (e.g. "React, FastAPI, SQLite")
- security_sensitivity: low / medium / high
- output_format: files / deployed app / library / script / other

Format your JSON block exactly like:
<FIELDS>
{"what_to_build": "...", "target_audience": "...", "platform_type": "...", "key_features": "...", "constraints": "...", "tech_stack": "...", "security_sensitivity": "...", "output_format": "..."}
</FIELDS>

Only include fields you have confidence about. Use null for fields not yet known.
Keep your conversational text concise and friendly."""

PROMPT_GENERATOR_SYSTEM = """You are a technical product manager. Given the structured fields below, 
generate a clear, detailed, actionable software requirement prompt that can be sent to an AI coding pipeline.

The prompt should:
- State exactly what needs to be built
- List the key features clearly
- Specify the tech stack
- Call out any constraints or security requirements
- Be specific enough that a senior engineer could start work immediately

Output ONLY the final prompt text. No preamble, no meta-commentary."""


class PromptService:
    def __init__(self, db: Session):
        self.db = db

    def list_templates(self) -> list[PromptTemplate]:
        return self.db.query(PromptTemplate).order_by(PromptTemplate.updated_at.desc()).all()

    def get_template(self, template_id: str) -> PromptTemplate | None:
        return self.db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()

    def create_template(self, **kwargs) -> PromptTemplate:
        tpl = PromptTemplate(**{k: v for k, v in kwargs.items() if hasattr(PromptTemplate, k)})
        self.db.add(tpl)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    def update_template(self, template_id: str, **kwargs) -> PromptTemplate | None:
        tpl = self.get_template(template_id)
        if not tpl:
            return None
        for k, v in kwargs.items():
            if hasattr(tpl, k):
                setattr(tpl, k, v)
        tpl.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    def delete_template(self, template_id: str) -> bool:
        tpl = self.get_template(template_id)
        if not tpl:
            return False
        self.db.delete(tpl)
        self.db.commit()
        return True

    async def chat(self, messages: list[dict], current_fields: dict | None = None) -> dict:
        """Chat with the requirement-refining assistant."""
        try:
            provider = OllamaProvider(mode="fast")
        except Exception as e:
            logger.warning("Ollama is unreachable, falling back to local mode: %s", e)
            provider = None

        # Build the conversation prompt
        history_text = ""
        for msg in messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_text += f"{role}: {msg['content']}\n\n"

        if current_fields:
            fields_context = f"\nCurrent extracted fields:\n{json.dumps(current_fields, indent=2)}\n\n"
        else:
            fields_context = ""

        prompt = f"{fields_context}Conversation so far:\n{history_text}Assistant:"

        # Quick fallback to avoid timeouts
        if provider:
            try:
                response = await provider.complete(
                    ModelRequest(prompt=prompt, system_prompt=REFINER_SYSTEM, temperature=0.7, max_tokens=512)
                )
                if not response.success:
                    raise Exception("Ollama response failed")
            except Exception as e:
                logger.warning("Ollama call failed, using fallback: %s", e)
                return {
                    "reply": "I can help you refine your idea! Tell me more about what you want to build and I'll help structure the requirements.",
                    "updated_fields": current_fields or {},
                    "generated_prompt": None,
                }
        else:
            return {
                "reply": "I can help you refine your idea! Tell me more about what you want to build and I'll help structure the requirements.",
                "updated_fields": current_fields or {},
                "generated_prompt": None,
            }

        content = response.content
        updated_fields = current_fields.copy() if current_fields else {}

        # Parse <FIELDS> block
        import re
        match = re.search(r"<FIELDS>\s*(\{.*?\})\s*</FIELDS>", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                for k, v in parsed.items():
                    if v is not None and v != "null":
                        updated_fields[k] = v
            except Exception as e:
                logger.warning("Could not parse FIELDS block: %s", e)

        # Strip the FIELDS block from the reply
        reply = re.sub(r"<FIELDS>.*?</FIELDS>", "", content, flags=re.DOTALL).strip()

        return {
            "reply": reply,
            "updated_fields": updated_fields,
            "generated_prompt": None,
        }

    async def generate_final_prompt(self, fields: dict, context_summary: str | None = None) -> str:
        """Generate the final build prompt from structured fields."""
        provider = OllamaProvider(mode="fast")

        fields_text = json.dumps({k: v for k, v in fields.items() if v}, indent=2)
        context_section = f"\nProject Context:\n{context_summary}\n" if context_summary else ""

        prompt = f"Structured Fields:\n{fields_text}{context_section}\n\nGenerate the final build prompt:"

        response = await provider.complete(
            ModelRequest(prompt=prompt, system_prompt=PROMPT_GENERATOR_SYSTEM, temperature=0.3, max_tokens=2048)
        )

        if not response.success:
            # Fallback: compose manually from fields
            parts = []
            if fields.get("what_to_build"):
                parts.append(f"Build: {fields['what_to_build']}")
            if fields.get("target_audience"):
                parts.append(f"Target audience: {fields['target_audience']}")
            if fields.get("platform_type"):
                parts.append(f"Platform: {fields['platform_type']}")
            if fields.get("key_features"):
                parts.append(f"Key features: {fields['key_features']}")
            if fields.get("tech_stack"):
                parts.append(f"Tech stack: {fields['tech_stack']}")
            if fields.get("constraints"):
                parts.append(f"Constraints: {fields['constraints']}")
            if context_summary:
                parts.append(f"\nExisting project context:\n{context_summary}")
            return "\n".join(parts)

        return response.content.strip()

    def build_agent_handoff_previews(self, final_prompt: str, fields: dict) -> dict:
        """Build preview payloads for each agent phase."""
        stack = fields.get("tech_stack", "unspecified")
        project = fields.get("what_to_build", "project")
        return {
            "architect": {
                "agent": "ArchitectAgent",
                "input_summary": f"Produce structured_spec.md + file_plan.json for: {project}",
                "stack": stack,
                "prompt_preview": final_prompt[:300] + ("..." if len(final_prompt) > 300 else ""),
            },
            "coder": {
                "agent": "CoderAgent",
                "input_summary": "Generate source files based on architect output and file_plan.json",
                "stack": stack,
                "note": "Receives structured_spec + file_plan as context",
            },
            "hardener": {
                "agent": "HardenerAgent",
                "input_summary": "Heuristic security scan + LLM remediation notes",
                "checks": ["eval()", "shell=True", "hardcoded secrets", "permissive CORS", "pickle"],
            },
            "validator": {
                "agent": "ValidatorAgent",
                "input_summary": "Verify file completeness + quality, may trigger one retry",
                "retry_budget": 1,
            },
            "builder": {
                "agent": "BuilderAgent",
                "input_summary": "Detect project type, install dependencies, run build/test commands",
                "stack": stack,
                "note": "Runs npm install / pip install, then build/start/test scripts",
            },
            "smoke_tester": {
                "agent": "SmokeTesterAgent",
                "input_summary": "Deep inspection of built output — verify HTML structure, CSS rules, JS logic, package.json validity",
                "checks": ["HTML DOCTYPE + body tags", "CSS has actual rules", "JS has functions", "package.json deps + scripts", "Python imports + functions"],
            },
        }
