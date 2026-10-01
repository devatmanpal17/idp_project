"""
Pydantic request / response models for the ChaiGaram AI API.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Any, Optional, Literal


class RequestModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class RetrieveRequest(RequestModel):
    document_id: Optional[str] = Field(default=None, max_length=64)
    query: str = Field(default="", description="Search query or question")
    topic: Optional[str] = Field(default=None, description="Topic name")
    top_k: int = Field(default=6, ge=1, le=20, description="Number of context chunks to retrieve")


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class AskRequest(RequestModel):
    learner_key: Optional[str] = Field(default=None, max_length=100)
    video_key: Optional[str] = Field(default=None, max_length=200)
    document_id: Optional[str] = Field(default=None, max_length=64)
    question: str = Field(..., min_length=2, max_length=2000)
    topic: Optional[str] = Field(default=None, max_length=300)
    transcript_context: Optional[str] = Field(default=None, max_length=50000)
    top_k: int = Field(default=5, ge=1, le=10)
    history: List[ChatTurn] = Field(default_factory=list, max_length=12)
    source_type: Literal["document", "video"] = "document"
    observed_until_seconds: float = Field(default=0, ge=0)


class SummarizeRequest(RequestModel):
    learner_key: Optional[str] = Field(default=None, max_length=100)
    video_key: Optional[str] = Field(default=None, max_length=200)
    document_id: Optional[str] = Field(default=None, max_length=64)
    topic: str = Field(..., min_length=2, max_length=300)
    page_content: str = Field(default="", max_length=50000)
    page_url: Optional[str] = Field(default="", max_length=4000)
    source_type: Literal["document", "video"] = "document"
    observed_until_seconds: float = Field(default=0, ge=0)


class GenerateQuizRequest(RequestModel):
    learner_key: Optional[str] = Field(default=None, max_length=100)
    video_key: Optional[str] = Field(default=None, max_length=200)
    document_id: Optional[str] = Field(default=None, max_length=64)
    topic: str = Field(..., description="Target topic name")
    mastery_score: float = Field(default=0.0, ge=0, le=100, description="Persisted current mastery score (0-100)")
    quiz_perf_pct: Optional[float] = Field(default=0.0, ge=0, le=100)
    time_on_section_pct: Optional[float] = Field(default=0.0, ge=0, le=100)
    revisit_frequency_pct: Optional[float] = Field(default=0.0, ge=0, le=100)
    recent_errors: Optional[List[str]] = Field(default_factory=list)
    question_count: int = Field(default=3, ge=1, le=8)
    source_context: Optional[str] = Field(default=None, max_length=50000)
    page_url: Optional[str] = Field(default="", max_length=4000)
    language: str = Field(default="English", pattern="^English$")
    source_type: Literal["document", "video"] = "document"
    observed_until_seconds: float = Field(default=0, ge=0)


class AIJobRequest(BaseModel):
    request_id: Optional[str] = Field(default=None, pattern=r'^[a-zA-Z0-9-]{8,80}$')
    operation: Literal["ask", "summarize", "quiz", "seal"]
    payload: Dict[str, Any]


class EvaluateQuizRequest(RequestModel):
    topic: str
    quiz_id: str = Field(..., min_length=8)
    given_answers: List[str]
    current_mastery: float = Field(default=0.0, ge=0, le=100)


class IngestDocumentRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=300)
    topic: str = Field(..., min_length=2, max_length=300)
    content: str = Field(..., min_length=20, max_length=2_000_000)
    course: str = Field(default="", max_length=300)


class StreamTranscriptRequest(BaseModel):
    video_title: str
    timestamp: str
    transcript_segment: str = Field(..., min_length=2, max_length=12000)
    current_topic: str
    dwell_seconds: int = 15
    page_url: Optional[str] = Field(default="", max_length=4000)
    video_position_seconds: Optional[float] = Field(default=0, ge=0)
    video_duration_seconds: Optional[float] = Field(default=0, ge=0)


class AIConfigRequest(BaseModel):
    provider: str = Field(default="ollama", description="Local Ollama provider")
    api_key: Optional[str] = Field(default="")
    model: Optional[str] = Field(default="", max_length=200)
