from pydantic import BaseModel, Field


class AnalyzerSettings(BaseModel):
    app_name: str = Field(default="aicc-analyzer")
    environment: str = Field(default="dev")
    sqs_queue_url: str | None = Field(default=None)
    status_queue_url: str | None = Field(default=None)
    audit_queue_url: str | None = Field(default=None)
    max_documents_per_job: int = Field(default=10)


def get_settings() -> AnalyzerSettings:
    return AnalyzerSettings()
