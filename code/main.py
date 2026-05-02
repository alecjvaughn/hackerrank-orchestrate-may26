import os
import json
import logging
import argparse
import pandas as pd
import numpy as np
from google.cloud import firestore
from pymongo import MongoClient
from google import genai
from google.genai import types
from dotenv import load_dotenv
from prompts import TRIAGE_SYSTEM_PROMPT, RESPONDER_SYSTEM_PROMPT

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

def setup_logger(verbosity="info"):
    """Sets up the logger with configurable verbosity and writes to a standard file."""
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'pipeline.log')

    # Map string verbosity to logging levels
    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR
    }
    
    logger = logging.getLogger('pipeline')
    # Avoid adding multiple handlers if setup_logger is called multiple times
    if not logger.handlers:
        logger.setLevel(logging.DEBUG) # Catch all, filter at handler level
        
        # File handler (always minimum INFO, or lower if requested)
        file_level = min(logging.INFO, level_map.get(verbosity.lower(), logging.INFO))
        fh = logging.FileHandler(log_file)
        fh.setLevel(file_level)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(level_map.get(verbosity.lower(), logging.INFO))
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
    return logger

def get_db_clients():
    """Initializes and returns the database clients."""
    mongo_uri = os.getenv("MONGO_URI")
    db_firestore = firestore.Client()
    mongo_client = MongoClient(mongo_uri)
    return db_firestore, mongo_client

def cosine_similarity(v1, v2):
    """Calculates cosine similarity between two vectors."""
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def generate_embedding(client: genai.Client, text: str) -> list[float]:
    """Generates a vector embedding for the given text."""
    result = client.models.embed_content(
        model='gemini-embedding-2',
        contents=text
    )
    return result.embeddings[0].values

def process_full_pipeline(run_triage=True, run_retrieval=True, run_answer=True, verbosity="info", target_similarity=None, eval_callback=None):
    """
    Configurable multi-agent pipeline:
    1. Triage: Classifies Product Area and Request Type.
    2. Retrieval: Fetches relevant support docs from MongoDB.
    3. Response: Drafts the response and justification.
    """
    logger = setup_logger(verbosity)
    logger.info(f"Starting pipeline. Agents: Triage={run_triage}, Retrieval={run_retrieval}, Answer={run_answer}")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY missing from environment.")
        return

    db_firestore, mongo_client = get_db_clients()
    genai_client = genai.Client(api_key=api_key)
    
    col_queue = db_firestore.collection("triage_queue")
    db_mongo = mongo_client["support_triage"]
    col_kb = db_mongo["knowledge_base"]
    
    # Fetch tickets
    tickets = list(col_queue.stream())
    
    queue_msg = f"Queue size: {len(tickets)}"
    if target_similarity is not None:
        queue_msg += f" | Target Similarity: {target_similarity}"
    logger.info(queue_msg)
    
    for doc in tickets:
        ticket_data = doc.to_dict()
        ticket_id = doc.id
        issue_text = ticket_data.get('issue', '')
        
        logger.info(f"Processing Ticket {ticket_id}...")
        
        try:
            # We initialize local variables from existing ticket data if not running triage
            product_area = ticket_data.get("product_area")
            request_type = ticket_data.get("request_type")
            top_context = ""
            res_result = {}

            # --- STEP 1: TRIAGE ---
            if run_triage:
                logger.debug(f"[{ticket_id}] Running Triage Agent...")
                triage_response = genai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    config=types.GenerateContentConfig(
                        system_instruction=TRIAGE_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                    ),
                    contents=f"ISSUE: {issue_text}\nSUBJECT: {ticket_data.get('subject')}\nCOMPANY: {ticket_data.get('company')}"
                )
                triage_result = json.loads(triage_response.text)
                product_area = triage_result.get("product_area")
                request_type = triage_result.get("request_type")
                logger.debug(f"[{ticket_id}] Triage Result: Area={product_area}, Type={request_type}")
            
            # --- STEP 2: RETRIEVAL ---
            # Even if we don't run retrieval agent explicitly, we still fetch chunks if we run the responder
            if run_retrieval and product_area:
                logger.debug(f"[{ticket_id}] Running Retrieval Agent for area: {product_area}...")
                query_embed = generate_embedding(genai_client, issue_text)
                
                company_eco = ticket_data.get("company", "unknown").lower()
                chunks = list(col_kb.find({"ecosystem": company_eco}))
                
                if chunks:
                    scored_chunks = []
                    for chunk in chunks:
                        sim = cosine_similarity(query_embed, chunk["embedding"])
                        scored_chunks.append((sim, chunk["content"]))
                    
                    scored_chunks.sort(key=lambda x: x[0], reverse=True)
                    top_context = "\n\n".join([c[1] for c in scored_chunks[:3]])
                    logger.debug(f"[{ticket_id}] Retrieved grounded context from knowledge base.")
                else:
                    logger.warning(f"[{ticket_id}] No grounding chunks found for ecosystem: {company_eco}")
            
            # --- STEP 3: RESPONDER ---
            if run_answer:
                logger.debug(f"[{ticket_id}] Running Responder Agent...")
                responder_prompt = f"""
                TICKET:
                Issue: {issue_text}
                Product Area: {product_area}
                Request Type: {request_type}
                
                CONTEXT FROM KNOWLEDGE BASE:
                {top_context}
                """
                
                response_data = genai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    config=types.GenerateContentConfig(
                        system_instruction=RESPONDER_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                    ),
                    contents=responder_prompt
                )
                res_result = json.loads(response_data.text)
                logger.debug(f"[{ticket_id}] Responder Status: {res_result.get('status')}")
            
            # --- UPDATE FIRESTORE ---
            # Strictly use original field names
            update_data = {"processed": True}
            if run_triage:
                update_data["product_area"] = product_area
                update_data["request_type"] = request_type
            if run_answer:
                update_data["status"] = res_result.get("status")
                update_data["response"] = res_result.get("response")
                update_data["justification"] = res_result.get("justification")
            
            col_queue.document(ticket_id).update(update_data)
            logger.info(f"Ticket {ticket_id} processed successfully.")
            
            # --- EVALUATION CALLBACK ---
            if eval_callback:
                full_predicted_data = ticket_data.copy()
                full_predicted_data.update(update_data)
                eval_callback(ticket_id, full_predicted_data, logger)
            
        except Exception as e:
            logger.error(f"Failed to process ticket {ticket_id}: {e}")

def generate_output(mode="test", verbosity="info"):
    """Writes processed tickets from Firestore to CSV."""
    logger = setup_logger(verbosity)
    if mode == "normal":
        output_path = "support_tickets/support_tickets.csv"
    else:
        output_path = "support_tickets/test_predictions.csv"
        
    db_firestore, _ = get_db_clients()
    col_queue = db_firestore.collection("triage_queue")
    docs = list(col_queue.where("processed", "==", True).stream())
    
    data = []
    fields = ["issue", "subject", "company", "response", "product_area", "status", "request_type", "justification"]
    
    for doc in docs:
        ticket_data = doc.to_dict()
        row = {field: ticket_data.get(field, "") for field in fields}
        data.append(row)
        
    if data:
        df = pd.DataFrame(data)
        df = df[fields]
        df.to_csv(output_path, index=False)
        logger.info(f"Successfully generated {output_path} with {len(data)} records.")
    else:
        logger.warning("No processed tickets found to write.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Support Triage multi-agent pipeline.")
    parser.add_argument("--action", choices=["run", "output"], default="run", help="Action to perform.")
    parser.add_argument("--mode", choices=["test", "normal"], default="test", help="Mode: 'test' or 'normal'")
    parser.add_argument("-t", "--triage", action="store_true", help="Run Triage Agent")
    parser.add_argument("-r", "--retrieval", action="store_true", help="Run Retrieval Agent")
    parser.add_argument("-a", "--answer", action="store_true", help="Run Responder (Answer) Agent")
    parser.add_argument("-v", "--verbosity", choices=["debug", "info", "warning", "error"], default="info", help="Logging verbosity")
    args = parser.parse_args()
    
    if args.action == "run":
        run_triage = args.triage
        run_retrieval = args.retrieval
        run_answer = args.answer
        
        # Default to all if no specific agent flags are specified
        if not (run_triage or run_retrieval or run_answer):
            run_triage = run_retrieval = run_answer = True
            
        process_full_pipeline(
            run_triage=run_triage, 
            run_retrieval=run_retrieval, 
            run_answer=run_answer,
            verbosity=args.verbosity
        )
    elif args.action == "output":
        generate_output(mode=args.mode, verbosity=args.verbosity)
