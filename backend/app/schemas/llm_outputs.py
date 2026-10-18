from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, create_model


class EvidenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None = None
    evidence: str | None = None
    confidence: Literal["high", "medium", "low"] = "low"


SCALAR_FIELDS = "title company_name company_website location_text work_mode employment_type experience_required_text stipend_or_salary_text duration_text start_date_text application_deadline_text posted_date_text apply_url apply_email contact_name contact_email contact_phone source_platform description_summary_verbatim selection_process_text other_notes openings_count_text".split()
LIST_FIELDS = "responsibilities required_skills preferred_skills qualifications perks_benefits".split()
JobExtraction = create_model("JobExtraction", __config__=ConfigDict(extra="forbid"), **{key: (EvidenceValue, Field(default_factory=EvidenceValue)) for key in SCALAR_FIELDS}, **{key: (list[EvidenceValue], Field(default_factory=list)) for key in LIST_FIELDS}, multiple_jobs_detected=(bool, False), titles=(list[str], Field(default_factory=list)))


class Keyword(BaseModel):
    term: str
    synonyms: list[str] = Field(default_factory=list)
    category: str = "skill"
    jd_evidence: str


class JDAnalysis(BaseModel):
    must_have_keywords: list[Keyword] = Field(default_factory=list)
    nice_to_have_keywords: list[Keyword] = Field(default_factory=list)
    responsibilities_themes: list[str] = Field(default_factory=list)
    seniority_signal: str = "unspecified"
    domain: str = "unspecified"
    ats_exact_phrases: list[str] = Field(default_factory=list)


class EvidenceJudgement(BaseModel):
    fact_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class BulletResult(BaseModel):
    bullet: str | None
    fact_ids: list[str] = Field(default_factory=list)


class SummaryResult(BaseModel):
    text: str | None
    fact_ids: list[str] = Field(default_factory=list)
