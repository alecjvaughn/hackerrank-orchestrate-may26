import os
import argparse
import pandas as pd
from uuid import uuid4
from pymongo import MongoClient
from google.cloud import firestore
from dotenv import load_dotenv
from schemas import TriageQueueTicket

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

def destroy_ground_truth(mongo_client, collection_name="test_ground_truth"):
    """
    Drops the collection in MongoDB.
    """
    print(f"Destroying existing MongoDB ground truth data in {collection_name}...")
    db = mongo_client["support_triage"]
    db[collection_name].delete_many({})

def create_ground_truth(mongo_client, df, collection_name="test_ground_truth"):
    """
    Populates the collection in MongoDB with unredacted data.
    Strictly uses the field names from output.csv.
    """
    print(f"Creating MongoDB ground truth data in {collection_name}...")
    db = mongo_client["support_triage"]
    col_truth = db[collection_name]
    
    mongo_docs = []
    for _, row in df.iterrows():
        # Strictly use output.csv field names
        truth_doc = {
            "_id": str(row.get("_ticket_id")),
            "issue": str(row.get("Issue", "")),
            "subject": str(row.get("Subject", "")),
            "company": str(row.get("Company", "")),
            "response": str(row.get("Response", "")),
            "product_area": str(row.get("Product Area", "")),
            "status": str(row.get("Status", "")),
            "request_type": str(row.get("Request Type", "")),
            "justification": str(row.get("Justification", "")) 
        }
        mongo_docs.append(truth_doc)
        
    if mongo_docs:
        col_truth.insert_many(mongo_docs)
    print(f"Inserted {len(mongo_docs)} unredacted tickets into MongoDB '{collection_name}'.")

def clear_firestore_queue(firestore_client, collection_name="triage_queue"):
    """
    Clears the collection in Firestore.
    """
    print(f"Clearing existing Firestore queue in {collection_name}...")
    col_queue = firestore_client.collection(collection_name)
    docs = col_queue.list_documents(page_size=100)
    count = 0
    for doc in docs:
        doc.delete()
        count += 1
    print(f"Deleted {count} documents from Firestore '{collection_name}'.")

def populate_firestore_queue(firestore_client, df, collection_name="triage_queue"):
    """
    Populates the collection in Firestore with redacted data.
    Fields after 'company' are redacted.
    """
    print(f"Populating Firestore queue in {collection_name}...")
    col_queue = firestore_client.collection(collection_name)
    
    count = 0
    for _, row in df.iterrows():
        ticket_id = str(row.get("_ticket_id"))
        
        # Explicitly redacted: only pass Issue, Subject, and Company
        queue_ticket = TriageQueueTicket(
            ticket_id=ticket_id,
            issue=str(row.get("Issue", "")),
            subject=str(row.get("Subject", "")),
            company=str(row.get("Company", "")),
            processed=False
        )
        col_queue.document(ticket_id).set(queue_ticket.model_dump())
        count += 1
        
    print(f"Inserted {count} redacted tickets into Firestore '{collection_name}'.")

def initialize_queues(mode="test"):
    """
    Main entry point for queue initialization.
    'test': uses sample data and populates MongoDB ground truth.
    'normal': uses production data and only populates the Firestore queue.
    """
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("Error: MONGO_URI missing from .env.local")
        return

    # 1. Initialize Clients
    mongo_client = MongoClient(mongo_uri)
    db_firestore = firestore.Client()

    # 2. Read Data
    csv_path = "support_tickets/sample_support_tickets.csv" if mode == "test" else "support_tickets/support_tickets.csv"
    
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return
        
    df = pd.read_csv(csv_path)
    print(f"Read {len(df)} tickets from {csv_path} (Mode: {mode.upper()}).")
    
    # Generate common ticket IDs for linking
    df["_ticket_id"] = [str(uuid4()) for _ in range(len(df))]

    # 3. Execution
    if mode == "test":
        destroy_ground_truth(mongo_client)
        clear_firestore_queue(db_firestore)
        create_ground_truth(mongo_client, df)
        populate_firestore_queue(db_firestore, df)
    else:
        clear_firestore_queue(db_firestore)
        populate_firestore_queue(db_firestore, df)
        
    print("\nInitialization complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize support ticket queues.")
    parser.add_argument("--mode", choices=["test", "normal"], default="test", help="Mode: 'test' (sample data + ground truth) or 'normal' (production data)")
    args = parser.parse_args()
    initialize_queues(mode=args.mode)
