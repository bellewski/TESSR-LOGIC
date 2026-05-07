from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas.prompt_template import (
    PromptTemplateCreate, PromptTemplateUpdate, PromptTemplateRead,
    PromptChatRequest, PromptChatResponse,
)
from backend.services.prompt_service import PromptService

router = APIRouter(prefix="/prompts", tags=["prompt-studio"])


@router.get("/templates", response_model=list[PromptTemplateRead])
def list_templates(db: Session = Depends(get_db)):
    return PromptService(db).list_templates()


@router.post("/templates", response_model=PromptTemplateRead, status_code=201)
def create_template(payload: PromptTemplateCreate, db: Session = Depends(get_db)):
    return PromptService(db).create_template(**payload.model_dump())


@router.get("/templates/{template_id}", response_model=PromptTemplateRead)
def get_template(template_id: str, db: Session = Depends(get_db)):
    tpl = PromptService(db).get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.patch("/templates/{template_id}", response_model=PromptTemplateRead)
def update_template(template_id: str, payload: PromptTemplateUpdate, db: Session = Depends(get_db)):
    tpl = PromptService(db).update_template(template_id, **payload.model_dump(exclude_none=True))
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str, db: Session = Depends(get_db)):
    ok = PromptService(db).delete_template(template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")


@router.post("/chat", response_model=PromptChatResponse)
async def chat(payload: PromptChatRequest, db: Session = Depends(get_db)):
    """Send a message to the requirement-refining chatbot."""
    svc = PromptService(db)
    messages = [m.model_dump() for m in payload.messages]
    result = await svc.chat(messages, current_fields=payload.current_fields)
    return PromptChatResponse(**result)


@router.post("/generate", response_model=dict)
async def generate_prompt(payload: dict, db: Session = Depends(get_db)):
    """Generate a final build prompt from structured fields + optional context summary."""
    svc = PromptService(db)
    fields = payload.get("fields", {})
    context_summary = payload.get("context_summary")
    final_prompt = await svc.generate_final_prompt(fields, context_summary)
    previews = svc.build_agent_handoff_previews(final_prompt, fields)
    return {"final_prompt": final_prompt, "agent_previews": previews}
