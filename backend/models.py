"""
Pydantic request / response models for the Cognivue AI API.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class RetrieveRequest(BaseModel):
    query: str = Field(default="", description="Search query or question")
    topic: Optional[str] = Field(default=None, description="Topic name")
    top_k: int = Field(default=6, description="Number of context chunks to retrieve")


class GenerateQuizRequest(BaseModel):
    topic: str = Field(..., description="Target topic name")
    mastery_score: float = Field(default=50.0, description="Current mastery score (0-100)")
    quiz_perf_pct: Optional[float] = Field(default=50.0)
    time_on_section_pct: Optional[float] = Field(default=50.0)
    revisit_frequency_pct: Optional[float] = Field(default=50.0)
    recent_errors: Optional[List[str]] = Field(default_factory=list)
    question_count: int = Field(default=3)


class EvaluateQuizRequest(BaseModel):
    topic: str
    questions: List[Dict[str, Any]]
    given_answers: List[str]
    current_mastery: float = 50.0


class StreamTranscriptRequest(BaseModel):
    video_title: str
    timestamp: str
    transcript_segment: str
    current_topic: str
    dwell_seconds: int = 15


class AIConfigRequest(BaseModel):
    provider: str = Field(..., description="'gemini', 'openai', or 'local'")
    api_key: Optional[str] = Field(default="")
