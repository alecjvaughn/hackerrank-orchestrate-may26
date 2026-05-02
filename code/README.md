# HackerRank Orchestrate: Support Triage Agent

## Project Overview
This project builds an AI-driven, terminal-based support triage agent designed to handle support tickets across three major ecosystems: **HackerRank**, **Claude (Anthropic)**, and **Visa**. The agent uses a Retrieval-Augmented Generation (RAG) architecture to provide grounded, accurate responses based strictly on the provided support corpus.

---

## Agentic Architecture
We employ a multi-agent separation of concerns to ensure high reliability and compliance with evaluation criteria:
- **Triage Agent:** Classifies the `product_area` and `request_type`.
- **Retrieval Agent:** Formulates search queries and fetches grounded context from the MongoDB Vector Store.
- **Responder Agent:** Drafts professional responses and justifies the decision to either `reply` or `escalate`.

---

## Current Execution Plan (TDD Contract)

We are treating the provided sample data as a contract to iteratively build and verify the pipeline.

### 1. Agentic Design & Prompting
- [x] Read `evaluation_criteria.md` and `problem_statement.md`.
- [x] Define system prompts for Triage, Retrieval, and Responder agents.

### 2. Schema & Chunking Strategy
- [x] Plan filterable Firestore schemas for the `triage_queue` (strictly using `output.csv` field names).
- [x] Plan MongoDB schemas for the `knowledge_base` and `test_ground_truth`.

### 3. Minimal Knowledge Ingestion
- [x] Process only `data/*/index.md` files.
- [x] Generate embeddings using `gemini-embedding-2` and upload to MongoDB Atlas.

### 4. Queue Initialization
- [x] Write unredacted sample tickets to MongoDB `test_ground_truth`.
- [x] Write redacted sample tickets (Issue, Subject, Company only) to Firestore `triage_queue`.

### 5. Automated Triage (Agent Iteration 1)
- [x] Process the redacted queue to predict `product_area` and `request_type`.
- [x] Ground triage in the MongoDB vector store.
- [x] Verify accuracy using embedding closeness (cosine similarity threshold 0.75).

### 6. Output Generation
- [x] Compile processed results into `support_tickets/test_predictions.csv`.

### 7. Full Pipeline Evaluation
- [x] Integrate Retrieval and Responder agents.
- [x] Verify full output (including response and justification) using embedding closeness.

### 8. Console App & Production
- [x] Implement terminal-based navigation and UI.
- [ ] Process the remaining production support tickets into `support_tickets/support_tickets.csv`.

---

## Running the UI Test (QAS Mode)
The UI features a **QAS Mode** designed specifically for administrators to verify the application's functionality using clean sample data, isolated from production.

1.  **Activate your environment:**
    ```bash
    source venv/bin/activate
    ```
2.  **Launch the App in QAS mode:**
    ```bash
    python code/app.py --qas
    ```
3.  **Run the Setup Wizard:**
    Upon startup, the app will ask: *"Would you like to run the QAS Setup Wizard?"*.
    - Select **`y`**.
    - The wizard will automatically:
        1.  **Re-initialize** your QAS Firestore queue with fresh sample tickets.
        2.  **Ingest** the core knowledge base (index files) into MongoDB.
        3.  **Process** the entire sample queue through the full multi-agent pipeline.
4.  **Explore the Dashboard:**
    Once the wizard finishes, you will enter the main dashboard where you can view triaged tickets, edit fields manually, or sync more from the sample CSV.

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
5. **Run Pipeline Test:** `pytest code/tests/test_pipeline.py -v -s`
6. **Generate Test Output:** `python code/main.py --action output --mode test`
