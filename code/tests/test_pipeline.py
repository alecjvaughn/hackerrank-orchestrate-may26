import os
import pytest
from google.cloud import firestore
from dotenv import load_dotenv
import sys

# Ensure the 'code' directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import process_triage_queue

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

def test_triage_pipeline_integration():
    """
    Integration test: Runs the triage pipeline and verifies 
    that Firestore tickets are updated with predictions.
    """
    db_firestore = firestore.Client()
    col_queue = db_firestore.collection("triage_queue")
    
    # 1. Run the pipeline
    print("\nStarting triage pipeline...")
    process_triage_queue()
    
    # 2. Verify results in Firestore
    # Fetch all processed tickets
    processed_docs = list(col_queue.where("processed", "==", True).stream())
    
    # We expect all 10 sample tickets to be processed
    assert len(processed_docs) == 10, f"Expected 10 processed tickets, found {len(processed_docs)}"
    
    for doc in processed_docs:
        data = doc.to_dict()
        assert data["predicted_product_area"] is not None, f"Ticket {doc.id} missing prediction"
        assert len(data["confidence_scores"]) > 0, f"Ticket {doc.id} missing confidence scores"
        assert data["processed"] is True
        print(f"Verified Ticket {doc.id}: {data['predicted_product_area']} (Conf: {data['confidence_scores'][-1]})")

    # 3. User Verification Pause
    print("\n\n--- PIPELINE VERIFICATION (STEP 5) ---")
    print("The triage pipeline has processed the redacted sample queue.")
    print("Check Firestore Console to see the predictions and confidence scores.")
    print("Check Firestore URI: https://console.cloud.google.com/firestore")
    
    input("Press Enter to complete the test...")
    print("Step 5 verification complete.")

if __name__ == "__main__":
    # Manual run support
    test_triage_pipeline_integration()
