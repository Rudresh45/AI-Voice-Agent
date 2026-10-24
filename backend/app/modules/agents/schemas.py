from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=8000)
    model_id: str = Field(min_length=1, max_length=120)


class AgentRead(BaseModel):
    id: str
    name: str
    model_id: str
    status: str
