import re
from typing import Literal

from pydantic import BaseModel, field_validator

VOTER_ID_PATTERN = re.compile(r"^user-\d+$")


class VoteRequest(BaseModel):
    choice: Literal["jajang", "jjamppong"]
    voterId: str

    @field_validator("voterId")
    @classmethod
    def voter_id_format(cls, v: str) -> str:
        if not VOTER_ID_PATTERN.fullmatch(v):
            raise ValueError("voterId must match user-{int}")
        return v


class StateResponse(BaseModel):
    state: str


class ResultResponse(BaseModel):
    jajang: int
    jjamppong: int
    total: int


class HealthResponse(BaseModel):
    status: str
    db: str
