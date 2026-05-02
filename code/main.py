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
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'pipeline.log')

    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR
    }
    
    logger = logging.getLogger('pipeline')
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        file_level = min(logging.INFO, level_map.get(verbosity.lower(), logging.INFO))
        fh = logging.FileHandler(log_file)
        fh.setLevel(file_level)
        
        ch = logging.StreamHandler()
        ch.setLevel(level_map.get(verbosity.lower(), logging.INFO))
        
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

def process_full_pipeline(collection_name="triage_queue_prd", verbosity="info", target_similarity=None, eval_callback=None):
    """
    Configurable multi-agent pipeline using states:
    1. Triage: Classifies Product Area and Request Type.
    2. Retrieval: Fetches relevant support docs from MongoDB.
    3. Response: Drafts the response and justification.
    """
    logger = setup_logger(verbosity)
    logger.info(f"Starting pipeline on collection: {collection_name}")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY missing.")
        return

    db_firestore, mongo_client = get_db_clients()
    genai_client = genai.Client(api_key=api_key)
    
    col_queue = db_firestore.collection(collection_name)
    db_mongo = mongo_client["support_triage"]
    col_kb = db_mongo["knowledge_base"]
    
    # Process only PENDING tickets
    tickets = list(col_queue.where("ticket_state", "==", "PENDING").stream())
    
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
            # --- STEP 1: TRIAGE ---
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
            
            # --- STEP 2: RETRIEVAL ---
            logger.debug(f"[{ticket_id}] Running Retrieval Agent for area: {product_area}...")
            query_embed = generate_embedding(genai_client, issue_text)
            company_eco = ticket_data.get("company", "unknown").lower()
            chunks = list(col_kb.find({"ecosystem": company_eco}))
            
            top_context = ""
            if chunks:
                scored_chunks = []
                for chunk in chunks:
                    sim = cosine_similarity(query_embed, chunk["embedding"])
                    scored_chunks.append((sim, chunk["content"]))
                scored_chunks.sort(key=lambda x: x[0], reverse=True)
                top_context = "\n\n".join([c[1] for c in scored_chunks[:3]])
            
            # --- STEP 3: RESPONDER ---
            logger.debug(f"[{ticket_id}] Running Responder Agent...")
            responder_prompt = f"TICKET:\nIssue: {issue_text}\nArea: {product_area}\nType: {request_type}\n\nCONTEXT:\n{top_context}"
            
            response_data = genai_client.models.generate_content(
                model='gemini-2.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction=RESPONDER_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
                contents=responder_prompt
            )
            res_result = json.loads(response_data.text)
            
            # --- UPDATE STATE ---
            status = res_result.get("status")
            # If status is escalated, state becomes ESCALATED, else PROCESSED
            new_state = "ESCALATED" if status.lower() == "escalated" else "PROCESSED"
            
            update_data = {
                "product_area": product_area,
                "request_type": request_type,
                "status": status,
                "response": res_result.get("response"),
                "justification": res_result.get("justification"),
                "ticket_state": new_state
            }
            
            col_queue.document(ticket_id).update(update_data)
            logger.info(f"Ticket {ticket_id} processed successfully. New state: {new_state}")
            
            if eval_callback:
                full_data = ticket_data.copy()
                full_data.update(update_data)
                eval_callback(ticket_id, full_data, logger)
            
        except Exception as e:
            logger.error(f"Failed to process ticket {ticket_id}: {e}")

def generate_output(collection_name="triage_queue_prd", mode="test", verbosity="info"):
    """Writes processed/escalated tickets from Firestore to CSV."""
    logger = setup_logger(verbosity)
    output_path = "support_tickets/test_predictions.csv" if mode == "test" else "support_tickets/support_tickets.csv"
    
    db_fs, _ = get_db_clients()
    # Pull both PROCESSED and ESCALATED for the final output
    docs = list(db_fs.collection(collection_name).where("ticket_state", "in", ["PROCESSED", "ESCALATED"]).stream())
    
    data = []
    fields = ["issue", "subject", "company", "response", "product_area", "status", "request_type", "justification"]
    for doc in docs:
        d = doc.to_dict()
        data.append({f: d.get(f, "") for f in fields})
        
    if data:
        pd.DataFrame(data)[fields].to_csv(output_path, index=False)
        logger.info(f"Generated {output_path} with {len(data)} records.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["run", "output"], default="run")
    parser.add_argument("--mode", choices=["test", "normal"], default="test")
    parser.add_argument("-v", "--verbosity", default="info")
    args = parser.parse_args()
    
    col = "triage_queue_qas" if args.mode == "test" else "triage_queue_prd"
    
    if args.action == "run":
        process_full_pipeline(collection_name=col, verbosity=args.verbosity)
    elif args.action == "output":
        generate_output(collection_name=col, mode=args.mode, verbosity=args.verbosity)
