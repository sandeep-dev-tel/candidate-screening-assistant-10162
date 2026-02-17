from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ResumeOut(BaseModel):
    id: UUID = Field(..., description="Resume UUID.")
    filename: str = Field(..., description="Original uploaded filename.")
    content_type: Optional[str] = Field(None, description="MIME type provided on upload.")
    extracted: Dict[str, Any] = Field(..., description="Extracted structured fields (JSON).")
    created_at: datetime = Field(..., description="Upload timestamp.")


class CriteriaIn(BaseModel):
    title: str = Field(..., min_length=1, description="Criteria title/name.")
    description: Optional[str] = Field(None, description="Free-form description.")
    criteria: Dict[str, Any] = Field(..., description="Criteria JSON payload (skills, weights, etc.).")


class CriteriaOut(BaseModel):
    id: UUID = Field(..., description="Criteria UUID.")
    title: str = Field(..., description="Criteria title/name.")
    description: Optional[str] = Field(None, description="Free-form description.")
    criteria: Dict[str, Any] = Field(..., description="Criteria JSON payload.")
    created_at: datetime = Field(..., description="Creation timestamp.")


class RankRequest(BaseModel):
    criteria_id: UUID = Field(..., description="Criteria UUID to use for ranking.")


class RankingOut(BaseModel):
    id: UUID = Field(..., description="Ranking UUID.")
    criteria_id: UUID = Field(..., description="Criteria UUID.")
    resume_id: UUID = Field(..., description="Resume UUID.")
    score: float = Field(..., description="Match score (higher is better).")
    breakdown: Dict[str, Any] = Field(..., description="Details about how the score was computed.")
    created_at: datetime = Field(..., description="Ranking timestamp.")


class CandidateRankedOut(BaseModel):
    resume: ResumeOut = Field(..., description="Resume info.")
    ranking: RankingOut = Field(..., description="Ranking info.")
