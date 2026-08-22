from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    objective: str = Field(min_length=12, max_length=2000)


class FollowUpCreate(BaseModel):
    message: str = Field(min_length=3, max_length=1000)
