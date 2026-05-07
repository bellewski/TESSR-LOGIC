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
    input_schema: str | None = None
    output_schema: str | None = None


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    position: int | None = None
    enabled: bool | None = None
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
