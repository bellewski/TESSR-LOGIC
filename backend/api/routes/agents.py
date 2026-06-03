import logging
from typing import Sequence
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.agent_config import AgentConfig
from backend.repositories.agent_config_repo import AgentConfigRepository
from backend.agents.hiring_manager import HiringManagerAgent, HiringManagerInput
from backend.providers.ollama_provider import OllamaProvider
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


class AgentConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    agent_type: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    position: int = 0
    enabled: bool = True
    can_edit: bool = False
    input_schema: str | None = None
    output_schema: str | None = None


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    position: int | None = None
    enabled: bool | None = None
    can_edit: bool | None = None
    input_schema: str | None = None
    output_schema: str | None = None


class AgentConfigRead(BaseModel):
    id: str
    name: str
    agent_type: str
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    position: int
    enabled: bool
    is_builtin: bool
    can_edit: bool = False
    input_schema: str | None = None
    output_schema: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


def get_repo(db: Session = Depends(get_db)) -> AgentConfigRepository:
    return AgentConfigRepository(db)


@router.get("", response_model=list[AgentConfigRead])
def list_agents(repo: AgentConfigRepository = Depends(get_repo)):
    agents: Sequence[AgentConfig] = repo.list_all()
    return [AgentConfigRead(**a.to_dict()) for a in agents]


@router.get("/pipeline", response_model=list[AgentConfigRead])
def get_pipeline(repo: AgentConfigRepository = Depends(get_repo)):
    agents: Sequence[AgentConfig] = repo.get_enabled_pipeline()
    return [AgentConfigRead(**a.to_dict()) for a in agents]


@router.get("/{agent_id}", response_model=AgentConfigRead)
def get_agent(agent_id: str, repo: AgentConfigRepository = Depends(get_repo)):
    agent = repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentConfigRead(**agent.to_dict())


@router.post("", response_model=AgentConfigRead)
def create_agent(payload: AgentConfigCreate, repo: AgentConfigRepository = Depends(get_repo)):
    data = payload.model_dump()
    data["is_builtin"] = False
    agent = repo.create(data)
    return AgentConfigRead(**agent.to_dict())


@router.patch("/{agent_id}", response_model=AgentConfigRead)
def update_agent(agent_id: str, payload: AgentConfigUpdate, repo: AgentConfigRepository = Depends(get_repo)):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    agent = repo.update(agent_id, data)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentConfigRead(**agent.to_dict())


@router.delete("/{agent_id}")
def delete_agent(agent_id: str, repo: AgentConfigRepository = Depends(get_repo)):
    ok = repo.delete(agent_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot delete builtin agent or agent not found")
    return {"deleted": True}


class HireRequest(BaseModel):
    new_agent_name: str = Field(..., min_length=1, max_length=255)
    new_agent_type: str = Field(..., min_length=1, max_length=50)
    new_agent_description: str = Field(..., min_length=1)


class HireResponse(BaseModel):
    success: bool
    error: str = ""
    recommended_position: int = 0
    rationale: str = ""
    placement: str = ""
    confidence: str = "low"


@router.post("/hire", response_model=HireResponse)
async def hire_agent(req: HireRequest, repo: AgentConfigRepository = Depends(get_repo)):
    """Consult the Hiring Manager to determine where a new agent belongs in the pipeline."""
    all_agents = repo.list_all()
    pipeline = [
        {
            "name": a.name,
            "agent_type": a.agent_type,
            "position": a.position,
            "description": a.description,
        }
        for a in all_agents
    ]

    hm = HiringManagerAgent(OllamaProvider())
    result = await hm.run(
        HiringManagerInput(
            new_agent_name=req.new_agent_name,
            new_agent_description=req.new_agent_description,
            new_agent_type=req.new_agent_type,
            current_pipeline=pipeline,
        )
    )

    return HireResponse(
        success=result.success,
        error=result.error,
        recommended_position=result.recommended_position,
        rationale=result.rationale,
        placement=result.placement,
        confidence=result.confidence,
    )


# ── Conversational Agent Designer ─────────────────────────────────────────────
class DesignMsg(BaseModel):
    role: str
    content: str


class DesignRequest(BaseModel):
    messages: list[DesignMsg]


_DESIGNER_SYSTEM = """You are an Agent Architect helping a NON-technical user design a NEW agent for a
multi-agent software BUILD pipeline (the existing pipeline: Architect -> Coder -> UI Designer ->
Hardener -> Fixer -> Validator -> Builder -> Smoke Tester -> Runtime QA -> Design Critic).

Chat naturally. Understand what the user wants the new agent to DO — its single clear responsibility,
what input it reads, what it outputs, and where it likely fits. Ask at most one or two short
clarifying questions only if genuinely needed; otherwise propose.

When you have enough to propose the agent, END your message with a fenced JSON block exactly like:
```json
{"name":"Title Case Name","agent_type":"snake_case_type","description":"one or two sentences on its job and where it fits","system_prompt":"the full system prompt that tells this agent how to do its job, its role boundary (what it must NOT do), and its output format"}
```
Only include the JSON block once you're confident. Keep prose before it short and friendly."""


class DesignResponse(BaseModel):
    reply: str
    proposal: dict | None = None


@router.post("/design", response_model=DesignResponse)
async def design_agent(req: DesignRequest):
    """Conversational helper that co-designs a new agent and proposes its name/type/description/prompt."""
    from backend.providers.base import ModelRequest
    import json as _json
    import re as _re

    convo = "\n".join(f"{m.role.upper()}: {m.content}" for m in req.messages[-12:])
    resp = await OllamaProvider(agent_type="architect").complete(ModelRequest(
        prompt=convo + "\n\nRespond as the Agent Architect.",
        system_prompt=_DESIGNER_SYSTEM, temperature=0.4, max_tokens=1400, num_ctx=8192,
    ))
    if not resp.success:
        raise HTTPException(status_code=502, detail=f"Designer failed: {resp.error}")

    content = resp.content or ""
    proposal = None
    m = _re.search(r"```json\s*(\{.*?\})\s*```", content, _re.DOTALL)
    if not m:
        m = _re.search(r"(\{[^{}]*\"system_prompt\"[^{}]*\})", content, _re.DOTALL)
    if m:
        try:
            data = _json.loads(m.group(1))
            proposal = {
                "name": str(data.get("name", ""))[:120],
                "agent_type": _re.sub(r"[^a-z0-9_]", "_", str(data.get("agent_type", "")).lower())[:50],
                "description": str(data.get("description", ""))[:600],
                "system_prompt": str(data.get("system_prompt", ""))[:4000],
            }
            content = content[: m.start()].strip() or "Here's a proposed agent — review and adjust below."
        except Exception:
            proposal = None
    return DesignResponse(reply=content.strip(), proposal=proposal)
