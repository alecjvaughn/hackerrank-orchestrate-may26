import os
import pandas as pd
from uuid import uuid4
from google.cloud import firestore
from dotenv import load_dotenv
from schemas import TriageQueueTicket

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

# Global constants for the sync engine
DEFAULT_REINIT_COUNT = 10

def get_firestore_client():
    """Initializes and returns the Firestore client."""
    return firestore.Client()

def sync_tickets(mode="test", limit=None, collection_name=None):
    """
    Syncs tickets from the CSV file to Firestore.
    Does NOT modify the source CSV files.
    
    mode: "test" (reads sample_support_tickets.csv) or "normal" (reads support_tickets.csv)
    limit: Number of NEW tickets to sync (None for all).
    collection_name: Explicit Firestore collection to sync to.
    """
    db = get_firestore_client()
    
    if not collection_name:
        collection_name = "triage_queue_qas" if mode == "test" else "triage_queue_prd"
        
    csv_path = "support_tickets/sample_support_tickets.csv" if mode == "test" else "support_tickets/support_tickets.csv"
    
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return 0

    # Read the source CSV (read-only)
    df = pd.read_csv(csv_path)
    
    # Get existing ticket issues in Firestore to avoid duplicates
    existing_docs = list(db.collection(collection_name).stream())
    existing_fingerprints = set([f"{d.to_dict().get('issue')}|{d.to_dict().get('subject')}" for d in existing_docs])

    col_ref = db.collection(collection_name)
    count = 0
    
    for _, row in df.iterrows():
        if limit is not None and count >= limit:
            break
            
        issue = str(row.get("Issue", row.get("issue", "")))
        subject = str(row.get("Subject", row.get("subject", "")))
        fingerprint = f"{issue}|{subject}"
        
        if fingerprint in existing_fingerprints:
            continue
            
        ticket_id = str(uuid4())
        
        # New tickets start in PENDING state
        ticket = TriageQueueTicket(
            ticket_id=ticket_id,
            issue=issue,
            subject=subject,
            company=str(row.get("Company", row.get("company", ""))),
            ticket_state="PENDING"
        )
        
        col_ref.document(ticket_id).set(ticket.model_dump())
        count += 1
        
    print(f"Successfully synced {count} new tickets to {collection_name} from {csv_path}.")
    return count

def reset_firestore_collection(collection_name):
    """Clears all documents from a Firestore collection."""
    db = get_firestore_client()
    col_ref = db.collection(collection_name)
    docs = col_ref.list_documents(page_size=100)
    deleted_count = 0
    for doc in docs:
        doc.delete()
        deleted_count += 1
    print(f"Reset complete. Deleted {deleted_count} documents from {collection_name}.")
    return deleted_count

def reinitialize_queue(mode="test", count=DEFAULT_REINIT_COUNT, collection_name=None):
    """
    Performs a clean initialization: resets the collection and syncs a specific number of entries.
    """
    if not collection_name:
        collection_name = "triage_queue_qas" if mode == "test" else "triage_queue_prd"
    
    reset_firestore_collection(collection_name)
    return sync_tickets(mode=mode, limit=count, collection_name=collection_name)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sync support tickets from CSV to Firestore.")
    parser.add_argument("--mode", choices=["test", "normal"], default="test")
    parser.add_argument("--limit", type=int, help="Limit number of tickets to sync")
    parser.add_argument("--reinit", action="store_true", help="Perform a clean re-initialization (reset + sync)")
    args = parser.parse_args()
    
    target_col = "triage_queue_qas" if args.mode == "test" else "triage_queue_prd"
    
    if args.reinit:
        # Use provided limit or fallback to global constant
        limit = args.limit if args.limit is not None else DEFAULT_REINIT_COUNT
        reinitialize_queue(mode=args.mode, count=limit, collection_name=target_col)
    else:
        sync_tickets(mode=args.mode, limit=args.limit, collection_name=target_col)
