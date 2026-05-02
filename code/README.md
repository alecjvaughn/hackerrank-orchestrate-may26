# HackerRank Orchestrate: Support Triage Agent

## Project Overview
This project builds an AI-driven, terminal-based support triage agent designed to handle support tickets across three major ecosystems: **HackerRank**, **Claude (Anthropic)**, and **Visa**. The agent uses a Retrieval-Augmented Generation (RAG) architecture to provide grounded, accurate responses based strictly on the provided support corpus.

### Key Goals
- **Request Classification:** Identify request types (product issue, feature request, bug, invalid).
- **Domain Triage:** Route issues to the correct product area.
- **Safety & Escalation:** Determine whether to reply directly or escalate sensitive/complex issues to a human.
- **Grounded Responses:** Generate answers using only the provided markdown corpus, avoiding hallucinations.

---

## Code Structure

- **`code/main.py`**: The canonical entry point for the HackerRank evaluation. It handles reading the input CSV and orchestrating the processing loop.
- **`code/ingest.py`**: A utility script to parse the `data/` directory, extract metadata from markdown files, and upload them to a **MongoDB Atlas** cluster for vector search.
- **`code/tests/`**:
    - **`test_connections.py`**: (Phase 1) Verifies basic connectivity to MongoDB, Firestore, and the Gemini AI model.
    - **`test_data_io.py`**: (Phase 2) Performs full data I/O tests (Write -> Read -> Delete) on MongoDB and Firestore, including manual validation steps with console URIs.

---

## Execution Plan & Progress

### ✅ Phase 1: Environment & Infrastructure Verification
- [x] Create virtual environment and install dependencies.
- [x] Configure `.env.local` for secret management.
- [x] Implement and pass connectivity pings for MongoDB Atlas, Google Cloud Firestore, and Gemini 2.5 Flash.

### 🔄 Phase 2: Data Ingestion (In Progress)
- [x] Implement `ingest.py` for recursive markdown parsing.
- [ ] Run ingestion to populate MongoDB Atlas knowledge base.
- [ ] Create vector search index in MongoDB Atlas.

### 📅 Phase 3: Multi-Agent Orchestration Loop
- [ ] Implement `main.py` as a Firestore-based event publisher/listener.
- [ ] Implement a background worker to perform the RAG lookup and LLM generation.
- [ ] Implement a custom TDD evaluation loop against `sample_support_tickets.csv`.

### 📅 Phase 4: Refinement & Submission
- [ ] Iteratively improve retrieval accuracy.
- [ ] Finalize escalation logic and safety guards.
- [ ] Generate `output.csv` for final submission.

---

## Getting Started

1. **Activate Environment:**
   ```bash
   source venv/bin/activate
   ```
2. **Run Infrastructure Tests:**
   ```bash
   pytest code/tests/test_data_io.py -v -s
   ```
3. **Ingest Knowledge Base:**
   ```bash
   python code/ingest.py
   ```
