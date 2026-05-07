from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentInput(BaseModel):
    build_id: str
    mode: str = "fast"


class AgentOutput(BaseModel):
    success: bool
    error: str = ""


class BaseAgent(ABC, Generic[InputT, OutputT]):
    @abstractmethod
    async def run(self, input_data: InputT) -> OutputT:
        pass
