import os
import json
import pytest
import numpy as np
import logging
from google.cloud import firestore
from pymongo import MongoClient
from google import genai
from dotenv import load_dotenv
import sys

# Ensure the 'code' directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import process_full_pipeline, setup_logger

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

# Offset for average similarity test (e.g., 0.05 means pass if avg_sim >= threshold + 0.05)
AVERAGE_SIMILARITY_OFFSET = 0.05

def cosine_similarity(v1, v2):
    """Calculates cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    return dot_product / (norm_v1 * norm_v2)

def ticket_to_text(data, fields):
    """Converts a ticket dictionary to a string for embedding."""
    text_parts = [f"{k}: {data.get(k, '')}" for k in fields if data.get(k) is not None]
    return " | ".join(text_parts)

@pytest.fixture(scope="session")
def clients():
    api_key = os.getenv("GOOGLE_API_KEY")
    mongo_uri = os.getenv("MONGO_URI")
    db_firestore = firestore.Client()
    mongo_client = MongoClient(mongo_uri)
    genai_client = genai.Client(api_key=api_key)
    return db_firestore, mongo_client, genai_client

def test_pipeline_embedding_accuracy(clients):
    """
    TDD Contract: Runs the pipeline and verifies each ticket is semantically close to ground truth.
    """
    # Configuration via env vars (useful for pytest running)
    run_triage = os.getenv("TEST_RUN_TRIAGE", "True").lower() == "true"
    run_retrieval = os.getenv("TEST_RUN_RETRIEVAL", "True").lower() == "true"
    run_answer = os.getenv("TEST_RUN_ANSWER", "True").lower() == "true"
    sim_threshold = float(os.getenv("TEST_SIMILARITY_THRESHOLD", "0.75"))
    verbosity = os.getenv("TEST_VERBOSITY", "info")
    
    logger = setup_logger(verbosity)
    logger.info(f"--- STARTING INDIVIDUAL TICKET EVALUATION ---")
    
    db_firestore, mongo_client, genai_client = clients
    col_truth = mongo_client["support_triage"]["test_ground_truth"]
    
    similarities = []
    
    # Determine comparison fields dynamically based on active agents
    comparison_fields = []
    if run_triage:
        comparison_fields.extend(["product_area", "request_type"])
    if run_answer:
        comparison_fields.extend(["status", "response", "justification"])
        
    def evaluate_ticket(ticket_id, predicted_data, pipeline_logger):
        # Fetch ground truth
        truth_doc = col_truth.find_one({"_id": ticket_id})
        if not truth_doc:
            return
            
        pred_text = ticket_to_text(predicted_data, comparison_fields)
        truth_text = ticket_to_text(truth_doc, comparison_fields)
        
        pred_embed = genai_client.models.embed_content(
            model='gemini-embedding-2',
            contents=pred_text
        ).embeddings[0].values
        
        truth_embed = genai_client.models.embed_content(
            model='gemini-embedding-2',
            contents=truth_text
        ).embeddings[0].values
        
        similarity = cosine_similarity(pred_embed, truth_embed)
        similarities.append((ticket_id, similarity))
        
        pipeline_logger.info(f"Ticket {ticket_id} Actual Sim: {similarity:.4f}")

    # 1. Run the configured pipeline
    process_full_pipeline(
        run_triage=run_triage, 
        run_retrieval=run_retrieval, 
        run_answer=run_answer, 
        verbosity=verbosity,
        target_similarity=sim_threshold,
        eval_callback=evaluate_ticket
    )
    
    failed_tickets = []
    for tid, sim in similarities:
        if sim < sim_threshold:
            failed_tickets.append(tid)

    if similarities:
        avg_sim = sum(sim for _, sim in similarities) / len(similarities)
        logger.info(f"Average Pipeline Similarity: {avg_sim:.4f}")
    
    assert not failed_tickets, f"{len(failed_tickets)} tickets failed the similarity threshold ({sim_threshold})."


def test_pipeline_average_similarity(clients):
    """
    TDD Contract: Verifies that the average semantic similarity across the dataset 
    is within the target threshold minus an acceptable offset.
    """
    run_triage = os.getenv("TEST_RUN_TRIAGE", "True").lower() == "true"
    run_retrieval = os.getenv("TEST_RUN_RETRIEVAL", "True").lower() == "true"
    run_answer = os.getenv("TEST_RUN_ANSWER", "True").lower() == "true"
    sim_threshold = float(os.getenv("TEST_SIMILARITY_THRESHOLD", "0.75"))
    verbosity = os.getenv("TEST_VERBOSITY", "info")
    
    logger = setup_logger(verbosity)
    logger.info(f"--- STARTING DATASET AVERAGE EVALUATION ---")
    
    db_firestore, mongo_client, genai_client = clients
    col_truth = mongo_client["support_triage"]["test_ground_truth"]
    
    similarities = []
    
    comparison_fields = []
    if run_triage:
        comparison_fields.extend(["product_area", "request_type"])
    if run_answer:
        comparison_fields.extend(["status", "response", "justification"])
        
    def evaluate_ticket(ticket_id, predicted_data, pipeline_logger):
        truth_doc = col_truth.find_one({"_id": ticket_id})
        if not truth_doc:
            return
            
        pred_text = ticket_to_text(predicted_data, comparison_fields)
        truth_text = ticket_to_text(truth_doc, comparison_fields)
        
        pred_embed = genai_client.models.embed_content(
            model='gemini-embedding-2',
            contents=pred_text
        ).embeddings[0].values
        
        truth_embed = genai_client.models.embed_content(
            model='gemini-embedding-2',
            contents=truth_text
        ).embeddings[0].values
        
        similarity = cosine_similarity(pred_embed, truth_embed)
        similarities.append((ticket_id, similarity))
        pipeline_logger.debug(f"Ticket {ticket_id} Actual Sim: {similarity:.4f}")

    # Re-run is fine for TDD loop verification, but normally we'd rely on state
    process_full_pipeline(
        run_triage=run_triage, 
        run_retrieval=run_retrieval, 
        run_answer=run_answer, 
        verbosity=verbosity,
        eval_callback=evaluate_ticket
    )
    
    if similarities:
        avg_sim = sum(sim for _, sim in similarities) / len(similarities)
        logger.info(f"Average Pipeline Similarity for dataset: {avg_sim:.4f}")
    else:
        avg_sim = 0.0
        logger.warning("No similarities calculated in average test.")
    
    # The average similarity should be above the threshold plus the offset to ensure overall quality
    target_average = sim_threshold + AVERAGE_SIMILARITY_OFFSET
    logger.info(f"Target Average: {target_average:.4f} (Threshold: {sim_threshold} + Offset: {AVERAGE_SIMILARITY_OFFSET})")
    
    assert avg_sim >= target_average, f"Dataset average similarity {avg_sim:.4f} is below target {target_average:.4f}"


if __name__ == "__main__":
    # Allow manual CLI overrides if run directly
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--triage", action="store_true", help="Test Triage Agent")
    parser.add_argument("-r", "--retrieval", action="store_true", help="Test Retrieval Agent")
    parser.add_argument("-a", "--answer", action="store_true", help="Test Responder Agent")
    parser.add_argument("-v", "--verbosity", choices=["debug", "info", "warning", "error"], default="info")
    parser.add_argument("-s", "--similarity", type=float, default=0.75)
    args = parser.parse_args()
    
    run_triage = args.triage
    run_retrieval = args.retrieval
    run_answer = args.answer
    if not (run_triage or run_retrieval or run_answer):
        run_triage = run_retrieval = run_answer = True

    os.environ["TEST_RUN_TRIAGE"] = str(run_triage)
    os.environ["TEST_RUN_RETRIEVAL"] = str(run_retrieval)
    os.environ["TEST_RUN_ANSWER"] = str(run_answer)
    os.environ["TEST_SIMILARITY_THRESHOLD"] = str(args.similarity)
    os.environ["TEST_VERBOSITY"] = args.verbosity
    
    # Manual execution logic
    load_dotenv(ENV_PATH)
    c_m_uri = os.getenv("MONGO_URI")
    c_ak = os.getenv("GOOGLE_API_KEY")
    c_clients = (firestore.Client(), MongoClient(c_m_uri), genai.Client(api_key=c_ak))
    
    test_pipeline_embedding_accuracy(c_clients)
    test_pipeline_average_similarity(c_clients)
    
    print("\n\n--- EVALUATION COMPLETE ---")
    input("Press Enter to exit...")
