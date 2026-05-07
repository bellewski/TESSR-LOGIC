import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # "architect", "coder", "hardener", "validator", "builder", "smoke_tester", "custom"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # JSON schema hints for custom agents
    input_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        String, default=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Mapped[datetime] = mapped_column(
        String, default=lambda: datetime.now(timezone.utc).isoformat(),
        onupdate=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "agent_type": self.agent_type,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "user_prompt_template": self.user_prompt_template,
            "position": self.position,
            "enabled": self.enabled,
            "is_builtin": self.is_builtin,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


BUILTIN_AGENTS = [
    {
        "name": "Hiring Manager",
        "agent_type": "hiring_manager",
        "description": "Meta-agent that recommends optimal pipeline placement for new custom agents based on their role.",
        "position": 0,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "Architect",
        "agent_type": "architect",
        "description": "Generates structured specifications and file plans from user requirements.",
        "position": 1,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "Coder",
        "agent_type": "coder",
        "description": "Generates source code files from the file plan and requirement.",
        "position": 2,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "UI Designer",
        "agent_type": "ui_designer",
        "description": "Generates production-quality CSS with dark mode, responsive design, and modern styling.",
        "position": 3,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "Hardener",
        "agent_type": "hardener",
        "description": "Reviews code for security vulnerabilities and adds hardening measures.",
        "position": 4,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "Validator",
        "agent_type": "validator",
        "description": "Validates spec compliance and functional completeness.",
        "position": 5,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "Builder",
        "agent_type": "builder",
        "description": "Installs dependencies, builds the project, and produces artifacts.",
        "position": 6,
        "enabled": True,
        "is_builtin": True,
    },
    {
        "name": "Smoke Tester",
        "agent_type": "smoke_tester",
        "description": "Performs runtime smoke tests on built artifacts.",
        "position": 7,
        "enabled": True,
        "is_builtin": True,
    },
]
