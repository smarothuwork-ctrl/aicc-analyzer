from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentReference(BaseModel):
    doc_id: str
    document_type: str
    presigned_url: str
    expires_at: str


class ContractData(BaseModel):
    dealer_id: str | None = None
    retail_type: str | None = None
    contract_date: str | None = None
    financed_amount: float | None = None
    stated_apr: float | None = None


class AnalyzerJobEvent(BaseModel):
    schema_version: int = Field(default=2)
    eval_id: str
    account_number: str
    contract_data: ContractData | None = None
    document_references: list[DocumentReference] = Field(default_factory=list)


class RuleEvaluation(BaseModel):
    rule_id: str
    rule_description: str
    status: str
    expected_value: str | None = None
    actual_value: str | None = None
    explanation: str | None = None


class AnalyzerResult(BaseModel):
    event_type: str = "EVALUATION_COMPLETED"
    eval_id: str
    account_number: str
    overall_status: str = "FLAGGED"
    overall_score: float = 0.0
    metrics: dict[str, int] = Field(default_factory=lambda: {"total_rules": 0, "passed_rules": 0, "failed_rules": 0})
    summary_results: list[RuleEvaluation] = Field(default_factory=list)
