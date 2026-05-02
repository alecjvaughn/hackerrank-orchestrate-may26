# HackerRank Orchestrate: Support Triage Agent

## Project Overview
This project builds an AI-driven, terminal-based support triage agent designed to handle support tickets across three major ecosystems: **HackerRank**, **Claude (Anthropic)**, and **Visa**. The agent uses a Retrieval-Augmented Generation (RAG) architecture to provide grounded, accurate responses based strictly on the provided support corpus.

---

## Agentic Architecture
We employ a multi-agent separation of concerns to ensure high reliability and compliance with evaluation criteria:
- **Triage Agent:** Classifies the `Product Area` and `Request Type`.
- **Retrieval Agent:** Formulates search queries and fetches grounded context from the MongoDB Vector Store.
- **Responder Agent:** Drafts professional responses and justifies the decision to either `reply` or `escalate`.

---

## Current Execution Plan (TDD Contract)

We are treating the provided sample data as a contract to iteratively build and verify the pipeline.

### 1. Agentic Design & Prompting
- [x] Read `evaluation_criteria.md` and `problem_statement.md`.
- [x] Define system prompts for Triage, Retrieval, and Responder agents.

### 2. Schema & Chunking Strategy
- [x] Plan filterable Firestore schemas for the `triage_queue` (with feature flags and confidence arrays).
- [x] Plan MongoDB schemas for the `knowledge_base` and `test_ground_truth`.

### 3. Minimal Knowledge Ingestion
- [x] Process only `data/*/index.md` files.
- [x] Generate embeddings using `gemini-embedding-2` and upload to MongoDB Atlas.

### 4. Queue Initialization
- [x] Write unredacted sample tickets to MongoDB `test_ground_truth`.
- [x] Write redacted sample tickets (Issue, Subject, Company only) to Firestore `triage_queue`.

### 5. Automated Triage (Phase 2 Tests)
- [ ] Process the redacted queue to predict `Product Area` and calculate confidence scores.
- [ ] Use MongoDB vector store for grounding.

### 6. Output Generation
- [ ] Compile processed results into a test `output.csv`.

### 7. Evaluation & Comparison
- [ ] Compare predictions against MongoDB ground truth.
- [ ] Iterate on prompts and retrieval logic until accuracy targets are met.

### 8. Console App & Production
- [ ] Implement terminal-based navigation and UI.
- [ ] Process the remaining production support tickets.

---

## Infrastructure Status
- **MongoDB Atlas:** Connected & Verified (I/O tested).
- **GCP Firestore:** Connected & Verified (I/O tested).
- **Gemini (Embedding & Chat):** Connected & Verified (Quota/Usage tested).

---

## Getting Started
1. **Activate Environment:** `source venv/bin/activate`
2. **Run Connection Tests:** `pytest code/tests/test_data_io.py -v -s`
3. **Ingest Core Corpus:** `python code/ingest.py --mode minimal`
4. **Initialize Test Queue:** `python code/init_queue.py --mode test`
