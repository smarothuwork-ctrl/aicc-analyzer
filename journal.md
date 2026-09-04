# AICC Analyzer Development Journal

## Purpose
This file tracks the architecture decisions, implementation progress, and reasoning for the AICC Analyzer service as it evolves from a minimal FastAPI app into a LangGraph-based analyzer service.

## Current State
- Repository: aicc-analyzer
- Current branch: story1
- Scope: analyzer service first, mocked integrations first, service-by-service architecture
- Architecture direction: LangGraph inside the Analyzer Service, while the platform remains service-oriented and event-driven

## Architecture Decisions
### Decision 1: Use LangGraph for the Analyzer workflow
We will use LangGraph as the orchestration framework for the Analyzer Service.

Why:
- the analyzer is the AI-heavy, multi-step decision engine
- the workflow naturally breaks into nodes such as document fetch, extraction, rule loading, LLM evaluation, and result publishing
- LangGraph supports future agentic behavior without forcing a monolithic implementation
- it keeps the workflow explicit, testable, and extensible

### Decision 2: Keep services independent by repo
Each major component will live in its own repository:
- Analyzer Service repo
- Audit Service repo
- Orchestrator Service repo
- Compliance Service repo
- optional shared contracts repo for API/event schema definitions

Why:
- independent lifecycle and deployment
- cleaner team ownership
- easier scaling and isolation
- aligns with the event-driven, service-oriented design

### Decision 3: Start with mocked integrations
We will first implement the Analyzer Service with mocked extraction, rule loading, and result publishing.

Why:
- accelerate development of the service contract and workflow
- keep the architecture valid before adding AWS/LLM dependencies
- allow rapid testing and iteration

### Decision 4: Keep the orchestrator deterministic
The orchestrator remains a simple state-tracking service and does not own AI logic or LLM execution.

Why:
- aligns with the documented design principle of deterministic orchestration versus non-deterministic analysis
- allows future evolution of the analyzer without breaking orchestrator contracts

## Architecture Direction
### Platform pattern
- Deterministic orchestrator service handles workflow state
- Analyzer service owns AI/extraction/scoring logic
- Audit service is a separate concern
- Compliance service owns rules and thresholds
- Each service should be independently deployable and versioned

### Why LangGraph
LangGraph is suitable for the Analyzer Service because the workflow is naturally step-based:
1. receive request
2. load document references
3. fetch rules
4. extract document text
5. evaluate against rules
6. return result
7. emit status event

This allows future evolution into a more agentic analyzer without forcing the orchestrator to know about LLM internals.

## Project Structure Notes
- Root contains project metadata and build docs
- src contains the runtime application
- src/main.py is the FastAPI entrypoint
- src/settings.py contains config loading
- src/aicc_analyzer/ contains the application package
- tests contains unit, integration, and component tests

## Design Principles Followed
- Keep each service independent
- Favor clear contracts over hidden coupling
- Build the analyzer service in isolation first
- Use mocked integrations before AWS or external dependencies
- Keep architecture simple and extensible

## Progress Log
### 2026-09-02
- Reviewed architecture from claude.md and Build.md
- Confirmed the platform is designed around service boundaries and event-driven interaction
- Confirmed the Analyzer Service is the non-deterministic AI/compliance evaluation layer
- Confirmed LangGraph is a good fit for future agentic evolution inside Analyzer
- Established the working direction: build analyzer first with mocked integrations

## Next Steps
1. Implement the minimal analyzer service skeleton
2. Add Pydantic models for evaluation request/response
3. Add analyzer service logic using mock rules and mock document extraction
4. Add tests for the happy path and validation path
5. Later introduce LangGraph orchestration around this logic
6. Keep service contracts stable for future integration with orchestrator and audit repos

## Notes
This file should continue to evolve as the design changes. It acts as a living implementation journal rather than a final architecture document.
