import os
import json
from google.cloud import firestore
from pymongo import MongoClient
from google import genai
from google.genai import types
from dotenv import load_dotenv
from prompts import TRIAGE_SYSTEM_PROMPT
from schemas import TriageQueueTicket

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

def get_db_clients():
    """Initializes and returns the database clients."""
    mongo_uri = os.getenv("MONGO_URI")
    db_firestore = firestore.Client()
    mongo_client = MongoClient(mongo_uri)
    return db_firestore, mongo_client

def process_triage_queue():
    """
    Triage phase of the pipeline:
    1. Fetches unprocessed tickets from Firestore.
    2. Retrieves grounding context from MongoDB.
    3. Calls Gemini to predict the Product Area.
    4. Updates Firestore with predictions and confidence.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY missing from environment.")
        return

    db_firestore, mongo_client = get_db_clients()
    genai_client = genai.Client(api_key=api_key)
    
    col_queue = db_firestore.collection("triage_queue")
    db_mongo = mongo_client["support_triage"]
    col_kb = db_mongo["knowledge_base"]
    
    # Fetch unprocessed tickets
    tickets = list(col_queue.where("processed", "==", False).stream())
    print(f"Found {len(tickets)} unprocessed tickets in the queue.")
    
    for doc in tickets:
        ticket_data = doc.to_dict()
        ticket_id = doc.id
        
        company = ticket_data.get("company", "unknown").lower()
        print(f"Triaging ticket {ticket_id} for {company}...")
        
        # Grounding: Fetch index chunks for this ecosystem from MongoDB
        kb_chunks = list(col_kb.find({"ecosystem": company}))
        kb_context = "\n\n".join([chunk["content"] for chunk in kb_chunks])
        
        # Construct the classification prompt
        user_prompt = f"""
        TICKET DATA:
        Issue: {ticket_data.get('issue')}
        Subject: {ticket_data.get('subject')}
        Company: {ticket_data.get('company')}
        
        GROUNDING CONTEXT (Available Categories):
        {kb_context}
        """
        
        try:
            # Call Gemini with structured output
            response = genai_client.models.generate_content(
                model='gemini-2.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction=TRIAGE_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                ),
                contents=user_prompt
            )
            
            result = json.loads(response.text)
            
            # Update Firestore
            predicted_area = result.get("product_area")
            confidence = result.get("confidence", 0.0)
            
            # Use current confidence_scores array if it exists
            scores = ticket_data.get("confidence_scores", [])
            scores.append(float(confidence))
            
            col_queue.document(ticket_id).update({
                "predicted_product_area": predicted_area,
                "confidence_scores": scores,
                "predicted_request_type": result.get("request_type"),
                "processed": True
            })
            
            print(f"Successfully triaged: {predicted_area} (Conf: {confidence})")
            
        except Exception as e:
            print(f"Failed to triage ticket {ticket_id}: {e}")

if __name__ == "__main__":
    process_triage_queue()
