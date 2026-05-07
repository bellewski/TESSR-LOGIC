from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    what_to_build: Optional[str] = None
    target_audience: Optional[str] = None
    platform_type: Optional[str] = None
    key_features: Optional[str] = None
    constraints: Optional[str] = None
    tech_stack: Optional[str] = None
    security_sensitivity: Optional[str] = None
    output_format: Optional[str] = None
    final_prompt: Optional[str] = None
    conversation_history: Optional[str] = None


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    what_to_build: Optional[str] = None
    target_audience: Optional[str] = None
    platform_type: Optional[str] = None
    key_features: Optional[str] = None
    constraints: Optional[str] = None
    tech_stack: Optional[str] = None
    security_sensitivity: Optional[str] = None
    output_format: Optional[str] = None
    final_prompt: Optional[str] = None
    conversation_history: Optional[str] = None
    is_default: Optional[bool] = None


class PromptTemplateRead(BaseModel):
    id: str
    name: str
    description: Optional[str]
    what_to_build: Optional[str]
    target_audience: Optional[str]
    platform_type: Optional[str]
    key_features: Optional[str]
    constraints: Optional[str]
    tech_stack: Optional[str]
    security_sensitivity: Optional[str]
    output_format: Optional[str]
    final_prompt: Optional[str]
    conversation_history: Optional[str]
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class PromptChatRequest(BaseModel):
    template_id: Optional[str] = None
    messages: list[PromptChatMessage]
    current_fields: Optional[dict] = None


class PromptChatResponse(BaseModel):
    reply: str
    updated_fields: dict
    generated_prompt: Optional[str] = None
