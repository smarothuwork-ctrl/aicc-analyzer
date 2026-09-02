
Credit Contract Compliance Evaluation Platform — Technical Reference
Purpose of this file: single source of truth for architecture, service boundaries, APIs, database schemas, and event contracts, meant to be dropped into a repo root (or opened in VS Code) so an AI coding assistant or a new engineer has full context before writing code. Reflects the Phase 1 design (TFS Retail only) plus target-state notes where relevant.

Table of Contents
Purpose & Scope
Design Principles
Phase 1 Scope Decisions
Services & Components
Overall Flow
Per-Service Flow & API Inventory
Database Schemas
Inter-Service Event Contracts
Redis Caching Strategy (Target State)
Security & Encryption
Hardening Backlog (Gap Analysis)
Open Decisions

1. Purpose & Scope
Automated platform that evaluates credit/finance contracts for compliance. It pulls a batch of accounts, retrieves the associated contract documents and metadata, runs LLM-based rule scoring against them, and surfaces pass/fail results to a compliance review UI.
Phase 1 scope: TFS Retail contracts only, ~100 accounts/day, contract selection via manual CSV/Excel upload (mirrors the existing Sage Advantage process).

2. Design Principles
Event-driven microservices. Services talk over SQS, not blocking HTTP calls, so long-running work (document retrieval, LLM scoring) never blocks a caller.
Deterministic orchestration vs. non-deterministic analysis. The Evaluation Service only tracks workflow state (PENDING → ... → COMPLETED). All LLM/AI logic lives in the Analyzer Service so it can evolve toward an agentic model later without touching the orchestrator's contract.
Database-per-service. Every service owns its own database/schema. No service reads or writes another service's tables directly — only via API or event.
Documents move as references, not payloads. Binary files live once in S3; services pass around object keys and short-lived pre-signed URLs, never file bytes.
CQRS split for evaluation state. DynamoDB absorbs high-concurrency status writes; PostgreSQL is the read model the UI actually queries. See Section 7.1.

3. Phase 1 Scope Decisions
Decision	Phase 1	Target State
Contract selection	Manual CSV/Excel upload via UI	Systematic/automated selection (logic TBD with business + BSA)
Compliance rules	One-time SQL seed into a table the Analyzer reads locally	Live REST API backed bycompliance_db, with versioning
Contract/credit data source	Contract/Account Service (external, via MuleSoft) — LOS has no exposed API	Same, pending confirmation this is the long-term system of record
Execution state store	DynamoDB (evaluation_execution_state)	Same
Rule/session caching	None	Redis / ElastiCache (evaluation-cache)

4. Services & Components
4.1 Ingestion Layer
Sub-component of the Evaluation Service that accepts the uploaded batch and fans it out into per-account work items.
S3 — landing-zone bucket (raw CSV/Excel uploads, short retention 7–30 days)
Lambda — csv-ingestion-lambda (triggered by s3:ObjectCreated:*, parses file, writes rows, emits SQS events)
SQS — ingestion-queue
DB — writes to evaluation_db (PostgreSQL)
4.2 Evaluation Service (Orchestrator)
Central, deterministic state machine. Coordinates but performs no heavy computation or LLM calls itself.
Compute — evaluation-orchestrator (Lambda or Fargate task)
DynamoDB — evaluation_execution_state (fast, high-concurrency workflow status)
PostgreSQL — evaluation_db (UI-facing read model)
S3 — contract-documents bucket (SSE-KMS)
SQS in — ingestion-queue, status-queue
SQS out — analyzer-queue, audit-queue
REST API exposed — consumed by UI and by the Analyzer (pre-signed URL issuance)
External calls — Contract/Account Service (MuleSoft), DMP/Document Lake
4.3 Analyzer Service
Owns all non-deterministic work: extraction, rule evaluation, LLM scoring. Decoupled from the orchestrator so it can become agentic later (LangGraph / Bedrock Agents with tool-calling sub-agents) without changing the orchestrator's contract.
Compute — analyzer-service (Lambda or Fargate task)
PostgreSQL — analyzer_db (deep trace store: extraction, prompts, token usage, rule scores)
SQS in — analyzer-queue
SQS out — status-queue, audit-queue
External calls — Amazon Textract, Amazon Bedrock, Prompt Management Service, Compliance Management Service, Evaluation Service (pre-signed URL API), S3 (GetObject via pre-signed URL)
4.4 Compliance Management Service
Owns business rules, thresholds, and versioning.
Compute — compliance-management-service
PostgreSQL — compliance_db
Phase 1 — rules seeded via one-time migration; no live API required yet
Target state — REST API + rule versioning + RuleUpdatedEvent publish (SNS/SQS) for cache invalidation
4.5 Audit System
Cross-cutting, append-only log fed by every other service.
SQS — audit-queue
Lambda — audit-consumer-lambda
PostgreSQL — audit_db

5. Overall Flow
flowchart TD
    UI["User / UI"] -->|"1 Upload CSV"| INGEST["Ingestion\n(S3 + Lambda + SQS)"]
    INGEST -->|"2 Account events (SQS)"| ORCH["Evaluation Orchestrator\nDynamoDB + evaluation_db"]
    ORCH -->|"3 Fetch data + docs"| EXT["External Systems\n(Contract Service, DMP)"]
    ORCH -->|"4 Execution event (SQS)"| ANALYZER["Analyzer Service\nanalyzer_db"]
    ANALYZER -->|"5 Extract + score"| AI["AWS AI Services\nTextract + Bedrock + Prompts"]
    ANALYZER -->|"6 Fetch rules"| COMPLIANCE["Compliance Service\ncompliance_db"]
    ANALYZER -.->|"7 Status event (SQS)"| ORCH
    UI <-->|"8 Query results (REST)"| ORCH
    ORCH -.->|"audit trace"| AUDIT["Audit System\naudit_db"]
    ANALYZER -.->|"audit trace"| AUDIT
    COMPLIANCE -.->|"audit trace"| AUDIT
 
Step	Actor	Action
1	User / UI	Upload CSV/Excel of account numbers
2	Ingestion Lambda	Parse CSV, write rows toevaluation_db, emit one SQS event per account
3	Evaluation Orchestrator	Consume event; call Contract/Account Service API for contract & credit data
4	Evaluation Orchestrator	Call DMP/Document Lake API; store D5 contract package docs in S3
5	Evaluation Orchestrator	Persist metadata + doc references toevaluation_db; write execution state to DynamoDB
6	Evaluation Orchestrator	Emit execution event (eval_id, account_number, data, doc_ids) to analyzer-queue
7	Analyzer Service	Request pre-signed URL from Evaluation Service API; download doc from S3
8	Analyzer Service	Run Textract extraction; fetch compliance rules; build LLM prompt
9	Analyzer Service	Invoke Bedrock; score rules; persist full trace toanalyzer_db
10	Analyzer Service	Publish status/result event tostatus-queue
11	Evaluation Orchestrator	Consume status event (idempotency check); updateevaluation_db
12	User / UI	Query REST APIs for batch progress and results
—	All services	Publish audit events toaudit-queue

6. Per-Service Flow & API Inventory
6.1 Ingestion Layer
flowchart TD
    UI["User / UI"] -->|"PutObject (pre-signed URL)"| S3["S3: landing-zone"]
    S3 -->|"ObjectCreated event"| LAMBDA["Lambda: csv-ingestion-lambda"]
    LAMBDA -->|"INSERT batch + account rows"| PG["PostgreSQL: evaluation_db"]
    LAMBDA -->|"SendMessage (1/account)"| SQS["SQS: ingestion-queue"]
    SQS -.->|"ReceiveMessage"| ORCH["Evaluation Orchestrator"]
 
Component	Type	API / Functional Call	Direction	Purpose
User / UI	Client	PutObject (S3 pre-signed URL)	Outbound (from UI)	Upload the CSV/Excel batch file
S3landing-zone	AWS S3	s3:ObjectCreated:* event	Trigger → Lambda	Notify Lambda the file has landed
csv-ingestion-lambda	AWS Lambda	INSERT into evaluation_batches, account_evaluations	Outbound → PostgreSQL	Persist batch + per-account rows
csv-ingestion-lambda	AWS Lambda	SendMessage	Outbound → SQSingestion-queue	Emit one event per account
ingestion-queue	AWS SQS	ReceiveMessage / DeleteMessage	Outbound → Orchestrator	Hand off account for processing
6.2 Evaluation Service (Orchestrator)
flowchart TD
    UI["User / UI"] <-->|"REST GET /batches, /evaluations/{id}"| ORCH["Evaluation Orchestrator"]
    ANALYZER_EXT["Analyzer Service"] -->|"REST GET presigned-url"| ORCH
    SQS_ING["SQS: ingestion-queue"] --> ORCH
    SQS_STATUS["SQS: status-queue"] --> ORCH
    ORCH -->|"GET data / docs"| EXT["Contract Service + DMP"]
    ORCH -->|"PutObject"| S3["S3: contract-documents"]
    ORCH -->|"PutItem / UpdateItem"| DDB["DynamoDB: evaluation_execution_state"]
    ORCH -->|"INSERT / UPDATE"| PG["PostgreSQL: evaluation_db"]
    ORCH -->|"SendMessage"| SQS_AN["SQS: analyzer-queue"]
    ORCH -->|"SendMessage"| SQS_AUD["SQS: audit-queue"]
 
Component	Type	API / Functional Call	Direction	Purpose
User / UI	Client	REST GET /batches, /batches/{id}, /evaluations/{id}	Inbound	Batch progress + results for dashboard
Analyzer Service	Internal REST	GET /evaluations/{id}/docs/{doc_id}/presigned-url	Inbound	Issue short-lived S3 GET URL
ingestion-queue	AWS SQS	ReceiveMessage / DeleteMessage	Inbound	Consume newly ingested accounts
status-queue	AWS SQS	ReceiveMessage / DeleteMessage	Inbound	Consume Analyzer status events
Contract/Account Service	External REST (MuleSoft)	GET /contracts/{account_number}	Outbound	Contract & credit metadata
DMP / Document Lake	External REST	GET /documents?account=...&source=D5	Outbound	Original contract package PDFs
S3contract-documents	AWS S3	PutObject	Outbound	Store retrieved PDFs (SSE-KMS)
DynamoDBevaluation_execution_state	AWS DynamoDB	PutItem / UpdateItem (conditional)	Outbound	High-concurrency status writes
PostgreSQLevaluation_db	RDS/Aurora	INSERT / UPDATE	Outbound	UI-facing aggregated state
analyzer-queue	AWS SQS	SendMessage	Outbound	Emit execution event to Analyzer
audit-queue	AWS SQS	SendMessage	Outbound	Emit audit trace event
6.3 Analyzer Service
flowchart TD
    SQS_AN["SQS: analyzer-queue"] --> ANALYZER["Analyzer Service"]
    ANALYZER -->|"GET presigned-url"| ORCH_API["Evaluation Service (REST)"]
    ANALYZER -->|"GetObject via URL"| S3["S3: contract-documents"]
    ANALYZER -->|"AnalyzeDocument"| TEXTRACT["Amazon Textract"]
    ANALYZER -->|"GET /prompts"| PROMPT["Prompt Mgmt Service"]
    ANALYZER -->|"GET /rules/export"| COMPLIANCE["Compliance Service"]
    ANALYZER -->|"InvokeModel"| BEDROCK["Amazon Bedrock"]
    ANALYZER -->|"INSERT"| PG["PostgreSQL: analyzer_db"]
    ANALYZER -->|"SendMessage"| SQS_STATUS["SQS: status-queue"]
    ANALYZER -->|"SendMessage"| SQS_AUD["SQS: audit-queue"]
 
Component	Type	API / Functional Call	Direction	Purpose
analyzer-queue	AWS SQS	ReceiveMessage / DeleteMessage	Inbound	Consume execution event from Orchestrator
Evaluation Service	Internal REST	GET /evaluations/{id}/docs/{doc_id}/presigned-url	Outbound	Request short-lived doc URL
S3contract-documents	AWS S3	GetObject (via pre-signed URL)	Outbound	Download document over HTTPS
Amazon Textract	AWS AI	AnalyzeDocument / StartDocumentAnalysis	Outbound	Extract text/structure from PDF
Prompt Management Service	External REST	GET /prompts/{template_id}	Outbound	Fetch prompt template
Compliance Management Service	Internal/External REST	GET /rules/export?account_type=...	Outbound	Fetch active rule set (Phase 1: local seeded table)
Amazon Bedrock	AWS AI	InvokeModel	Outbound	LLM reasoning + scoring
PostgreSQLanalyzer_db	RDS/Aurora	INSERT	Outbound	Persist extraction, prompts, token usage, rule scores
status-queue	AWS SQS	SendMessage	Outbound	Publish status/result to Orchestrator
audit-queue	AWS SQS	SendMessage	Outbound	Publish audit trace event
6.4 Compliance Management Service
flowchart TD
    ANALYZER_EXT["Analyzer Service"] -->|"REST GET /rules/export"| COMPLIANCE["Compliance Service"]
    COMPLIANCE_UI["Compliance UI (target state)"] -.->|"REST POST/PUT /rules"| COMPLIANCE
    COMPLIANCE -->|"SELECT/INSERT/UPDATE"| PG["PostgreSQL: compliance_db"]
    COMPLIANCE -->|"SendMessage"| SQS_AUD["SQS: audit-queue"]
    COMPLIANCE -.->|"publish RuleUpdatedEvent (target state)"| REDIS["Redis: evaluation-cache"]
 
Component	Type	API / Functional Call	Direction	Purpose
Analyzer Service	Internal REST	GET /rules/export	Inbound	Supply active rule set for scoring
Compliance UI*(target state)*	Client	POST / PUT /rules	Inbound	Create/update a rule
PostgreSQLcompliance_db	RDS/Aurora	SELECT / INSERT / UPDATE	Outbound	Read/write rule definitions
audit-queue	AWS SQS	SendMessage	Outbound	Publish audit trace event
Redisevaluation-cache (target state)	ElastiCache	PublishRuleUpdatedEvent	Outbound	Invalidate cached rule set on change
6.5 Audit System
flowchart TD
    ORCH["Evaluation Orchestrator"] -->|"SendMessage"| SQS["SQS: audit-queue"]
    ANALYZER["Analyzer Service"] -->|"SendMessage"| SQS
    COMPLIANCE["Compliance Service"] -->|"SendMessage"| SQS
    SQS -->|"ReceiveMessage"| LAMBDA["Lambda: audit-consumer-lambda"]
    LAMBDA -->|"INSERT system_audit_logs"| PG["PostgreSQL: audit_db"]
 
Component	Type	API / Functional Call	Direction	Purpose
Orchestrator / Analyzer / Compliance	Internal	SendMessage	Inbound	Publish trace events from every service
audit-queue	AWS SQS	ReceiveMessage / DeleteMessage	Inbound	Consume audit trace events
audit-consumer-lambda	AWS Lambda	INSERT (system_audit_logs)	Outbound	Persist immutable audit record

7. Database Schemas
7.1 DynamoDB — evaluation_execution_state
Single-table, key-only access pattern (point reads/writes by eval_id). No GSIs required unless the Orchestrator needs to query "all in-progress evals for batch X" directly (add a GSI on batch_id if so).
{
  "TableName": "evaluation_execution_state",
  "BillingMode": "PAY_PER_REQUEST",
  "KeySchema": [
    { "AttributeName": "eval_id", "KeyType": "HASH" }
  ],
  "AttributeDefinitions": [
    { "AttributeName": "eval_id", "AttributeType": "S" }
  ],
  "SSESpecification": { "Enabled": true, "SSEType": "KMS" }
}
 
Item shape:
{
  "eval_id": "eval-9876-xyz",
  "status": "ANALYZING",
  "current_step": "TEXTRACT_PARSING",
  "batch_id": "batch-001",
  "account_number": "ACC-123456",
  "attempt_count": 1,
  "last_event_id": "evt-abc123",
  "updated_at": "2026-08-30T13:20:00Z",
  "error_detail": null,
  "ttl": 1735689600
}
 
Writes use a ConditionExpression keyed on last_event_id so a redelivered SQS message is a no-op (idempotency).
7.2 PostgreSQL — evaluation_db
CREATE TABLE evaluation_batches (
    batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    uploaded_by VARCHAR(100) NOT NULL,
    total_accounts INT NOT NULL,
    completed_accounts INT DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'QUEUED', -- QUEUED, IN_PROGRESS, COMPLETED, FAILED
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE account_evaluations (
    eval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- matches DynamoDB partition key
    batch_id UUID REFERENCES evaluation_batches(batch_id) ON DELETE CASCADE,
    account_number VARCHAR(100) NOT NULL,
    dealer_id VARCHAR(100),
    retail_type VARCHAR(50), -- e.g., TFS_RETAIL
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING', -- PENDING, FETCHING_DOCS, ANALYZING, PASSED, FLAGGED, ERROR
    overall_score NUMERIC(5,2),
    total_rules_evaluated INT DEFAULT 0,
    rules_passed_count INT DEFAULT 0,
    rules_failed_count INT DEFAULT 0,
    external_contract_data JSONB, -- Contract/Account Service API response
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE evaluation_summary_results (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID REFERENCES account_evaluations(eval_id) ON DELETE CASCADE,
    rule_id VARCHAR(100) NOT NULL,
    rule_description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL, -- PASS, FAIL, WARNING
    expected_value TEXT,
    actual_value TEXT,
    explanation TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE evaluation_documents (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID REFERENCES account_evaluations(eval_id) ON DELETE CASCADE,
    document_type VARCHAR(100) NOT NULL, -- CREDIT_APPLICATION, RETAIL_CONTRACT
    s3_bucket VARCHAR(255) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_account_evaluations_batch_id ON account_evaluations(batch_id);
CREATE INDEX idx_account_evaluations_status ON account_evaluations(status);
CREATE INDEX idx_evaluation_summary_results_eval_id ON evaluation_summary_results(eval_id);
CREATE INDEX idx_evaluation_documents_eval_id ON evaluation_documents(eval_id);
 
7.3 PostgreSQL — analyzer_db
CREATE TABLE analyzer_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID NOT NULL, -- logical link to evaluation_db, no cross-DB FK
    account_number VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PROCESSING', -- PROCESSING, COMPLETED, FAILED
    start_time TIMESTAMPTZ DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    error_trace TEXT
);

CREATE TABLE document_extractions (
    extraction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES analyzer_jobs(job_id) ON DELETE CASCADE,
    doc_id UUID NOT NULL,
    raw_text TEXT,
    extracted_kv_pairs JSONB,
    extraction_latency_ms INT
);

CREATE TABLE prompt_logs (
    prompt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES analyzer_jobs(job_id) ON DELETE CASCADE,
    model_id VARCHAR(100) NOT NULL,
    system_prompt TEXT,
    user_prompt TEXT, -- includes the pipe-delimited compliance rule set
    input_tokens INT,
    output_tokens INT,
    latency_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE rule_evaluations (
    rule_eval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES analyzer_jobs(job_id) ON DELETE CASCADE,
    rule_id VARCHAR(100) NOT NULL,
    passed BOOLEAN NOT NULL,
    actual_value TEXT,
    expected_value TEXT,
    llm_reasoning TEXT,
    confidence_score NUMERIC(4,3)
);

CREATE INDEX idx_analyzer_jobs_eval_id ON analyzer_jobs(eval_id);
CREATE INDEX idx_document_extractions_job_id ON document_extractions(job_id);
CREATE INDEX idx_prompt_logs_job_id ON prompt_logs(job_id);
CREATE INDEX idx_rule_evaluations_job_id ON rule_evaluations(job_id);
 
7.4 PostgreSQL — compliance_db
CREATE TABLE compliance_rules (
    rule_id VARCHAR(100) PRIMARY KEY,
    account_type VARCHAR(50) NOT NULL, -- e.g., TFS_RETAIL
    field_target VARCHAR(100) NOT NULL, -- e.g., apr, finance_charge
    condition VARCHAR(50) NOT NULL, -- LESS_THAN_OR_EQUAL, EQUAL_TO
    expected_value TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL, -- CRITICAL, HIGH, MEDIUM
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, INACTIVE
    description TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_compliance_rules_account_type ON compliance_rules(account_type, status);
 
Rules export format (pipe-delimited, Accept: text/plain):
rule_id|account_type|field_target|condition|expected_value|severity|status|description
RULE-101|TFS_RETAIL|apr|LESS_THAN_OR_EQUAL|0.05|CRITICAL|ACTIVE|Ensure APR does not exceed max state limit
RULE-102|TFS_RETAIL|finance_charge|EQUAL_TO|calculated_finance_charge|HIGH|ACTIVE|Validate finance charge calculation
 
7.5 PostgreSQL — audit_db
CREATE TABLE system_audit_logs (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name VARCHAR(100) NOT NULL, -- EVALUATION_SERVICE, ANALYZER_SERVICE, COMPLIANCE_SERVICE
    event_type VARCHAR(100) NOT NULL, -- CONTRACT_FETCHED, ANALYSIS_COMPLETED, etc.
    account_number VARCHAR(100),
    payload JSONB NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_system_audit_logs_service_event ON system_audit_logs(service_name, event_type);
CREATE INDEX idx_system_audit_logs_timestamp ON system_audit_logs(timestamp);
 

8. Inter-Service Event Contracts
8.1 Orchestrator → Analyzer (analyzer-queue)
v2 (current, decided): the Orchestrator generates the pre-signed S3 URL at publish time (it already touches S3 to store the document) and embeds it directly in the event. This removes the callback API described in the old v1 design below — Analyzer never calls back to the Evaluation Service to request access, it just downloads. Set expires_at generously (30–60 min) to survive any SQS backlog/retry delay, since the URL is dead once it expires and there's no second chance to request a fresh one without re-publishing the event.
{
  "schema_version": 2,
  "eval_id": "eval-9876-xyz",
  "account_number": "ACC-123456",
  "contract_data": {
    "dealer_id": "DEALER-404",
    "retail_type": "TFS_RETAIL",
    "contract_date": "2026-08-15",
    "financed_amount": 35000.00,
    "stated_apr": 0.049
  },
  "document_references": [
    {
      "doc_id": "doc-001",
      "document_type": "CREDIT_APPLICATION",
      "presigned_url": "https://contract-documents.s3.amazonaws.com/...",
      "expires_at": "2026-08-30T14:30:00Z"
    },
    {
      "doc_id": "doc-002",
      "document_type": "RETAIL_CONTRACT",
      "presigned_url": "https://contract-documents.s3.amazonaws.com/...",
      "expires_at": "2026-08-30T14:30:00Z"
    }
  ]
}
 
Why not a standing IAM grant instead? Was raised and considered (Analyzer's role gets direct s3:GetObject on the Orchestrator's bucket, no pre-signed URL at all). Rejected for now — it's a permanent, un-time-boxed grant across a service boundary (same category of trade-off as the shared-DB debate), widening blast radius on regulated contract documents for the sake of removing one hop. The v2 contract above gets the same simplicity (no callback API) without that trade-off.
v1 (superseded) — request-based pre-signed URL 
Original design: the event carried only doc_id + s3_key, and Analyzer made a separate REST call to the Evaluation Service (GET /evaluations/{eval_id}/docs/{doc_id}/presigned-url) to obtain a short-lived (5 min) URL before downloading. Superseded by v2 above to remove the extra network hop; kept here for history since some diagrams/docs generated earlier in the project still show this flow and are due for a refresh.
8.2 Analyzer → Orchestrator (status-queue)
{
  "event_type": "EVALUATION_COMPLETED",
  "eval_id": "eval-9876-xyz",
  "account_number": "ACC-123456",
  "overall_status": "FLAGGED",
  "overall_score": 85.0,
  "metrics": { "total_rules": 10, "passed_rules": 8, "failed_rules": 2 },
  "summary_results": [
    {
      "rule_id": "RULE-101",
      "rule_description": "Ensure APR does not exceed max state limit",
      "status": "FAIL",
      "expected_value": "<= 5.0%",
      "actual_value": "6.2%",
      "explanation": "Extracted APR of 6.2% exceeds Texas legal max of 5.0%."
    }
  ]
}
 
8.3 Document access (pre-signed URL) — superseded, see 8.1 v2
The dedicated presigned-url endpoint is no longer needed under the v2 event contract (8.1) — the URL now travels inline in the SQS event. Analyzer still never gets standing S3 access, it just gets the URL a hop earlier.
8.4 DMP / Document Lake retrieval (confirmed via DMP team intake call)
APIs are synchronous only — no push/webhook notification for "new document available" exists yet for our use case (DMP has this on their roadmap, not present today). Confirms the Orchestrator's pull-based design is correct.
Search API: query by tagged metadata (account number) → returns matching doc_ids.
Get Content API: doc_id → raw PDF bytes.
Get Metadata API: doc_id → tags/metadata.
Contracts are confirmed to live in Doc Lake; exact site/store within Doc Lake is still being confirmed by their Doc Lake tech lead (Cervano).
Open risk, not yet resolved: an account can have more than one contract version (revisions/amendments after booking), and it's unconfirmed whether a contract can be amended after our evaluation would have already run. Orchestrator's document-fetch logic doesn't yet have a "pick the correct version" or "re-evaluate on amendment" rule — needs a decision before this ships.
Dealer jacket location is unconfirmed — may or may not be in Doc Lake; if not, that's a third document source with no integration plan yet.
Credit application PDF is likely NOT in Doc Lake — believed to be sourced via the separate LOS connectivity effort instead. Needs confirmation of exactly what that effort delivers (structured data only, or documents too).
Open strategic decision: DMP's own Intelligence Services can do one-time-configured, per-doc-type field extraction (e.g., "is this signed?", "what's the VIN?") automatically on every upload. Worth finding out how expressive their query capability is before assuming the Analyzer's Textract+Bedrock pipeline has to do 100% of the extraction work itself — there may be an opportunity to offload simple fields to DMP and keep the Analyzer focused on the genuinely conditional/compliance-specific scoring.

9. Redis Caching Strategy (Target State)
Not required for the Phase 1 pilot (~100/day); add when volume grows.
Use case	Key pattern	Behavior
Compliance rule cache	rules:{account_type}	Cache active pipe-delimited rule set; evict/refresh onRuleUpdatedEvent
Batch progress counters	batch:{batch_id}:completed	AtomicINCR per completed account, avoids row-lock contention in evaluation_db
Pre-signed URL cache	presigned:{doc_id}	TTL matches URL expiration (5 min); avoids regenerating for retries

10. Security & Encryption
At rest: S3 buckets use SSE-KMS with a customer-managed key (not the default AWS key); enable S3 Bucket Keys to cut KMS API cost. All four PostgreSQL databases and the DynamoDB table are encrypted at rest via KMS CMKs.
In transit: TLS 1.2/1.3 enforced on every inter-service call (REST, S3, SQS, MuleSoft). S3 bucket policy denies any request where aws:SecureTransport is false.
Secrets Manager inventory:
Secret	Used by
MuleSoft / Contract Service OAuth client ID & secret	Evaluation Service
DMP / Document Lake API key or mTLS cert	Evaluation Service
Bedrock & Textract IAM role	Analyzer Service
Prompt Management Service token	Analyzer Service
evaluation_db credentials	Evaluation Service
analyzer_db credentials	Analyzer Service
compliance_db credentials	Compliance Management Service
audit_db credentials	Audit Service
S3 KMS CMK IDs / SQS IAM policies	Platform / all services
IAM boundary: each service accesses only its own database. Cross-service document access happens only through explicit, time-limited pre-signed URLs — never a standing grant to another system's S3 bucket.

11. Hardening Backlog (Gap Analysis)
Not blockers for the Phase 1 pilot — track as backlog items before scaling.
Area	Priority	Gap	Recommendation
Error handling & retries	Critical	No DLQ/retry policy defined on any of the 4 SQS queues	Add a DLQ per queue, CloudWatch alarms on DLQ depth, exponential backoff, manual replay tool
Status sync idempotency	High	at-least-once SQS delivery risks duplicate processing	Idempotent writes keyed oneval_id + last_event_id (already reflected in DynamoDB schema above)
Observability	High	No tracing/correlation/dashboards	Correlate logs byeval_id; add X-Ray/OpenTelemetry; CloudWatch dashboards for queue depth, latency, Bedrock spend
DR / backup	High	No RPO/RTO or backup strategy defined	Automated PostgreSQL snapshots, cross-region S3 replication, documented RTO/RPO
Internal service auth	High	Inter-service REST auth (Evaluation ↔ Analyzer) not fully specified	mTLS or signed service-to-service JWT via API Gateway/IAM authorizer
Database-per-service	High	Single shared DB has been proposed — conflicts with isolation principle	Keep DBs physically separate, or enforce per-service IAM-scoped schemas if unavoidable
Contract selection automation	Medium	No systematic dataset/selection logic exists	Get business/BSA to define selection logic; build a dedicated selection service
Rule management	Medium	One-time DB seed, no versioning/audit trail	Build Compliance API with versioning + change events
Bedrock/Textract cost & throttling	Medium	No concurrency limits or budget alerts	Add request queuing, backoff, per-batch budgets, token-spend dashboard
Secrets rotation	Medium	Rotation policy not defined	Enable auto-rotation (30/60/90-day), scope IAM to specific secret ARNs
Data retention	Medium	No retention schedule for contract docs / audit logs	Define per TISS-310 classification; S3 lifecycle/Glacier tiering
Redis caching	Low	Not implemented	Add ElastiCache once volume exceeds pilot scale
Encryption verification	Low	Bucket Keys / deny-non-SSL policy need confirmation	Verify via AWS Config managed rules

12. Open Decisions
Pre-signed URL request pattern vs. standing IAM grant for Analyzer→S3 access — Resolved: pre-signed URL embedded directly in the SQS event at publish time (Section 8.1 v2). No callback API, no standing cross-service IAM grant.
Systematic contract-selection logic for post-Phase-1 automation (business + BSA)
Confirm Contract/Account Service as long-term substitute for LOS (LOS has no API)
Single shared DB vs. database-per-service — resolve with architecture lead
Confirm point of contact for Contract Service API access (shared services team, manager-level)
Target timeline for Compliance Management Service REST API (retire Phase 1 DB-seed shortcut)
DMP: confirm exact site/store in Doc Lake holding TFS retail contracts (pending Cervano)
DMP: confirm whether dealer jackets live in Doc Lake or need a separate source
DMP: confirm whether contracts can be amended/revised after booking, and if so, how the Orchestrator should detect and handle a new version
DMP: decide whether to use DMP's built-in Intelligence Services for simple field extraction (signed/not-signed, VIN) or keep 100% of extraction in the Analyzer's own Textract+Bedrock pipeline
Confirm what the in-progress LOS connectivity work actually delivers (structured data only, or documents too)

Companion documents: Architecture_Overview.docx, Architecture_Review_Recommendations.docx, Storage_Strategy.docx, Service_Flow_Diagrams.docx, and the standalone Diagram_*.png files.
==================================================
Build.md file

Build & Integration Roadmap
Companion to ARCHITECTURE.md. That file is the technical reference (what each service does, its schemas, its contracts). This file is about sequencing — build order, what has to be frozen before parallel work starts, what each service needs to be developed standalone before its real dependencies exist, and where the pieces get wired back together.

1. Build Order & Rationale
flowchart LR
    A["1. Analyzer Service"] --> B["2. Evaluation Orchestrator"]
    C["Audit System\n(parallel, anytime)"]
    D["4. Compliance / Rules\n(live service — last)"]
    A -.->|"needs seed rule data early"| D
    B --> E["Integration & E2E"]
    A --> E
    C --> E
 
Order	Service	Why this position
1	Analyzer Service	Highest complexity and highest technical risk (Textract accuracy, prompt quality, Bedrock scoring reliability). Building and de-risking it first means the hardest unknowns get resolved before the rest of the system is built around it.
2	Evaluation Orchestrator	Once the Analyzer's input/output contract is proven, build the orchestrator around it. Moderate complexity; its main risk isn't technical, it'sexternal (Contract/Account Service access, DMP onboarding — see Section 4).
parallel	Audit System	Simplest component in the platform (SQS → Lambda → Postgres insert). Has no functional dependency on Analyzer or Orchestrator being complete — only needs the audit event shape, which is already frozen (Section 2.3). Safe to build anytime, by anyone, without blocking or being blocked.
last	Compliance / Rules (live service)	Phase 1 doesn't need the live REST API at all — rules are seeded directly into a table (seeARCHITECTURE.md Section 3). Building the actual Compliance Management Service (API + compliance_db + versioning) is correctly lowest priority. But see the callout below — the rule content is a different dependency than the rule service.
Data dependency, not a service dependency: the Analyzer can't be meaningfully tested until it has some real or realistic rule content to score against. That doesn't require the Compliance service to exist — it just requires someone (compliance/business) to hand over a seed rule set early. Don't let "Rules is built last" become "we have no rules to test with until the end." Get seed data in week 1 even though the service itself is the last thing built.

2. Frozen Interface Contracts
These are the artifacts that let four people/teams build in parallel without integration turning into a rewrite. Once work starts against a contract, changing it means coordinating both sides — so lock these first, and version them if they need to change later.
2.1 Orchestrator → Analyzer event (analyzer-queue)
Status: frozen, v2. Full schema in ARCHITECTURE.md Section 8.1. Key points for whoever builds each side:
•	Pre-signed S3 URL travels inside the event (document_references[].presigned_url + expires_at) — Analyzer never calls back to the Orchestrator for document access.
•	schema_version field is present specifically so this can change again without breaking silently — bump it and branch on it if the shape ever changes.
•	Analyzer-side fixture note: since the Orchestrator won't exist yet when Analyzer development starts, the fixture generator (Section 3.1 below) must produce messages in exactly this shape, including realistic expires_at values.
2.2 Analyzer → Orchestrator status event (status-queue)
Status: frozen. Full schema in ARCHITECTURE.md Section 8.2. Orchestrator-side note: consume this idempotently — key on eval_id and dedupe against DynamoDB's last_event_id (Section 7.1), since SQS is at-least-once delivery.
2.3 Audit event (audit-queue)
Status: frozen (implicit in the system_audit_logs schema, ARCHITECTURE.md Section 7.5). Making it explicit here since Audit is built in parallel and every other service needs to publish to this shape correctly from day one:
{
  "service_name": "ANALYZER_SERVICE",
  "event_type": "ANALYSIS_COMPLETED",
  "account_number": "ACC-123456",
  "payload": { "eval_id": "eval-9876-xyz", "...": "..." },
  "timestamp": "2026-08-30T14:05:00Z"
}
 
Any service can start publishing to audit-queue in this shape immediately — Audit's consumer just needs to accept it and insert. No coordination needed beyond "use this shape."
2.4 Compliance rules format
Status: frozen for Phase 1 (seed table), not yet built for target state (live API). Pipe-delimited export format is in ARCHITECTURE.md Section 7.4. Analyzer should build its rule-fetching code against an interface (e.g., a RuleProvider abstraction) that reads from the seeded table now — so that swapping in the live Compliance API later doesn't touch Analyzer's scoring logic, only the provider implementation.

3. Per-Service Fixtures & Mocks Needed to Build Standalone
Building in this order means most services will, at some point, need to pretend a dependency exists before it actually does. Here's what each one needs.
3.1 Analyzer Service (built with nothing else built yet)
Dependency it doesn't have yet	What to fake instead
Real Orchestrator publishing events	A local fixture generator that publishes messages matching the frozen v2 contract (Section 2.1) to a local/devanalyzer-queue
Real contract documents behind pre-signed URLs	A small fixture set of real or synthetic contract PDFs uploaded to a dev S3 bucket, with locally-generated pre-signed URLs pointing at them
Live Compliance API	Seeded rule rows in a local Postgres instance (docker-compose), read through theRuleProvider abstraction (Section 2.4)
Prompt Management Service	Hardcoded/local prompt templates until that service exists — swap the source later, not the calling code
analyzer_db	Local Postgres via docker-compose, migrated with the DDL inARCHITECTURE.md Section 7.3
Textract / Bedrock	These are real AWS calls, not easily mocked meaningfully — use a real (dev-account) sandbox with the small fixture PDF set to keep cost/quota low during development
This fixture set (events + PDFs + expected outcomes) is the same thing the eval harness needs (see prior discussion on DeepEval/golden dataset). Build it once, use it for local dev and the automated eval suite — don't build two separate fixture sets.
3.2 Evaluation Orchestrator (built second, Analyzer now real)
Dependency	What to fake instead
Contract/Account Service (external, MuleSoft)	Mock this API locally until real access/credentials come through from the shared services team (this is an external lead-time item, not something engineering controls — track it separately, don't assume it'll be ready)
DMP / Document Lake	Mock until DMP onboarding completes (site confirmation + sandbox credentials — seeARCHITECTURE.md Section 8.4)
DynamoDB (evaluation_execution_state)	DynamoDB Local (Docker image) for dev
S3 (contract-documents)	Local/dev bucket
Analyzer	Real — this is the first true cross-service wiring, since Analyzer was built and proven in step 1
3.3 Audit System (parallel, minimal dependencies)
Needs only the frozen event shape (Section 2.3). No fixtures required beyond a few synthetic test messages — this can be built, tested, and deployed independently of everything else.
3.4 Compliance / Rules (last)
Phase 1: no service to build yet, just the seed SQL script (get this from compliance/business as early as possible — see the callout in Section 1). Target-state REST API build can start whenever, since nothing else is blocked on it as long as the RuleProvider abstraction (Section 2.4) is in place on the Analyzer side.

4. Integration Checkpoints
#	Checkpoint	Gate / done-when
1	Analyzer standalone	Passes the fixture/golden-dataset test suite end-to-end (fixture event → fixture doc → Textract → rules → Bedrock → scored result), deployed to a dev environment, invokable by directly injecting a message intoanalyzer-queue.
2	Orchestrator standalone	Can ingest a CSV, call (mocked) Contract Service + DMP, write to DynamoDB +evaluation_db, and emit an event that validates against the frozen v2 schema — not yet wired to the real Analyzer.
3	Orchestrator + Analyzer integrated	Real SQS wiring between the two services, real Textract/Bedrock, external Contract Service/DMP calls still mocked if real access isn't ready. First true end-to-end run within our own services.
4	Audit wired in	Orchestrator and Analyzer both publish real audit events; confirm they land correctly inaudit_db.
5	Real external integrations swapped in	Mocked Contract/Account Service and DMP calls replaced with real ones.Gated by external teams (shared services, DMP/Cervano), not by our own build order — track this on its own timeline.
6	Compliance live service swapped in (optional / target-state)	Seeded table replaced by the live Compliance API behind the sameRuleProvider interface — no changes needed elsewhere if the abstraction was respected in step 1.
7	UI wired end-to-end	Full user-facing flow validated: upload → orchestration → analysis → results in the dashboard.

5. Risks Tied to This Sequencing
•	External dependencies are on their own clock, not ours. Contract/Account Service API access (pending shared-services team / Jaya) and DMP onboarding (pending Cervano's site confirmation, "a day or two" for the initial answer, onboarding itself takes longer) could easily become the actual critical path regardless of how fast the Analyzer and Orchestrator get built. Track these as separate workstreams with their own status, not as a subtask of "build the Orchestrator."
•	Rule content is a business dependency, not an engineering one — don't let Analyzer sit idle waiting for realistic test data just because the Compliance service is scheduled last.
•	Contract versioning/amendment risk (from the DMP call) is still unresolved and will affect the Orchestrator's document-fetch logic once that work starts — worth getting an answer before, not during, Orchestrator development.
•	Contract changes need a version bump. If the Orchestrator↔Analyzer event shape changes again after Analyzer is built against it (like the pre-signed-URL change did), use schema_version to branch rather than breaking the other side silently.

6. Analyzer Service — AWS Onboarding Checklist & Local Dev Setup
Two separate lists: what to request from your platform/cloud team so it exists in real AWS, and what to run on your own machine so you don't need any of that to start writing code today.
6.1 What to request/register in AWS (real environment)
#	Item	Notes
1	ServiceNow CMDB / APM ID	Register the Analyzer as an application component (QSR.AM.001) — most T-Mobile landing-zone provisioning is tied to a registered APM ID, get this moving first since it can gate everything else.
2	AWS account / Landing Zone placement	Confirm which project AWS account (LZ2) this deploys into, and get added to it.
3	IAM execution role for Analyzer	Scoped to exactly what's below — nothing broader.
4	RDS/Aurora PostgreSQL instance	Foranalyzer_db (own instance, or own schema + IAM-scoped role within a shared instance, per the still-open DB-per-service decision). Apply the DDL from ARCHITECTURE.md §7.3.
5	Secrets Manager entries	analyzer_db credentials; API keys/tokens for Prompt Management Service and Compliance API once those are real (not needed for Phase 1 seeded-table rules).
6	SQS: analyzer-queue	Analyzer needsReceiveMessage/DeleteMessage on this one. Also request SendMessage permission on status-queue and audit-queue (owned by Orchestrator/Audit teams respectively — Analyzer doesn't create these, just needs send access).
7	Dead Letter Queue on analyzer-queue	Set this up now, not as an afterthought — matches the hardening backlog item in the Architecture Review doc.
8	Bedrock + Textract IAM permissions	bedrock:InvokeModel scoped to the specific model ARN(s) in use; textract:AnalyzeDocument / StartDocumentAnalysis / GetDocumentAnalysis.
9	CloudWatch Log Group	For Lambda/Fargate logs, eventually forwarded to Splunk (QSR.SL.001).
10	VPC/networking placement	If Analyzer needs private connectivity to RDS — coordinate with the platform team's existing VPC/subnet layout, don't stand up your own.
11	Container image source	If deploying as a container, base image must come from T-Mobile Harbor (QSR.CM.001).
12	GitLab CI/CD pipeline	Corporate GitLab repo with SAST/SCA/DAST stages (QSR.SV.001) — this is also where the eval-harness regression gate from the earlier discussion plugs in.
One thing that simplifies this list: Analyzer does not need any S3 or KMS IAM permissions at all. A pre-signed URL is self-authorizing — whoever holds the URL can perform that exact action as if they were the original signer (the Orchestrator), regardless of their own IAM identity. So Analyzer's role has zero S3/KMS surface for document access; it just needs outbound HTTPS network egress to reach the URL. That's a direct, concrete benefit of the v2 event contract (§2.1) over a standing IAM grant.
6.2 Local dev setup — no real AWS needed to start
Real dependency	Local stand-in
SQS (analyzer-queue, status-queue, audit-queue)	LocalStack (Docker container emulating SQS, S3, DynamoDB, Secrets Manager) — this is the "pub/sub" piece: run queues locally, publish/consume exactly like real SQS, same SDK calls.
S3 (contract-documents + pre-signed URLs)	Either LocalStack S3, or — recommended — a real smalldev-account S3 bucket, since pre-signed URL signature validation is easier to get right against real S3 than an emulation. Low cost, no production data involved.
analyzer_db (PostgreSQL)	Local Postgres viadocker-compose, migrated with the DDL from ARCHITECTURE.md §7.3.
Orchestrator (doesn't exist yet)	A small fixture-publisher script that pushes v2-contract-shaped JSON (§2.1) onto the localanalyzer-queue.
Compliance rules	Seeded rows in the local Postgres instance, read through aRuleProvider interface (§2.4) so swapping to the real API later is a one-line change.
Prompt Management Service	A local JSON/YAML file of prompt templates behind aPromptProvider interface — same swap-later pattern.
Textract / Bedrock	Not meaningfully fakeable — these need real AWS calls since mocking model output defeats the point of testing accuracy. Use a real dev/sandbox AWS account against the small fixture PDF set to keep cost controlled.
Minimal docker-compose.yml sketch to get the fakeable pieces running in one command:
services:
  localstack:
    image: localstack/localstack
    environment:
      - SERVICES=sqs,s3
    ports:
      - "4566:4566"
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_DB=analyzer_db
      - POSTGRES_PASSWORD=devpassword
    ports:
      - "5432:5432"
    volumes:
      - ./db/migrations:/docker-entrypoint-initdb.d
 
Bring this up, point the Analyzer app's config at localhost:4566 (SQS/S3) and localhost:5432 (Postgres), run the fixture-publisher script to drop a message on analyzer-queue, and you have a fully local, no-real-AWS execution path for everything except Textract/Bedrock.

Related: ARCHITECTURE.md (schemas, contracts, component detail), Architecture_Review_Recommendations.docx (production-hardening gap list — DLQs, observability, etc. worth keeping in mind as each service is built, not just retrofitted later).