from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    goal: str = Field(default="", description="Natural language job goal.")
    config_only: bool = Field(default=False, description="Use config defaults only.")
    dry_run: bool = Field(default=True, description="If true, do not submit final applications.")
    easy_apply_only: bool = Field(default=True, description="Restrict scraping to Easy Apply jobs.")
    max_scraped_jobs: int = Field(default=10, ge=1, le=100)
    max_scoring_jobs: int = Field(default=10, ge=1, le=50)
    max_applications: int = Field(default=10, ge=1, le=20)
    submission_target_successes: int = Field(default=1, ge=1, le=20, description="Stop submission once this many applications succeed.")
    max_approved_candidates: int = Field(default=10, ge=1, le=20)
    work_mode_preference: str = Field(default="any", description="Preferred work mode: any/remote/onsite/hybrid.")
    linkedin_email: str = Field(default="", description="LinkedIn login email for this run.")
    linkedin_password: str = Field(default="", description="LinkedIn login password for this run.")
    resume_file_name: str = Field(default="", description="Uploaded resume filename.")
    resume_file_b64: str = Field(default="", description="Uploaded resume file content as base64.")


class RunResponse(BaseModel):
    run_id: str
    status: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AsyncRunResponse(BaseModel):
    run_id: str
    status: str


class FirebaseLoginRequest(BaseModel):
    id_token: str


class FirebaseUserResponse(BaseModel):
    uid: str
    email: str = ""
    name: str = ""
    picture: str = ""


class TelegramTestRequest(BaseModel):
    message: str = Field(default="Job Agent backend Telegram test message.")


class TrackerStatusUpdateRequest(BaseModel):
    job_id: str
    new_status: str
    notes: str = ""


class FeatureResponse(BaseModel):
    service: str
    features: dict[str, Any] = Field(default_factory=dict)


class DocsSummaryResponse(BaseModel):
    service: str
    version: str
    sections: dict[str, Any] = Field(default_factory=dict)
