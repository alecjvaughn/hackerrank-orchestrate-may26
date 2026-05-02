import os
import pytest
import pandas as pd
from pymongo import MongoClient
from google.cloud import firestore
from dotenv import load_dotenv
import sys

# Ensure the 'code' directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from init_queue import (
    initialize_queues,
    destroy_ground_truth,
    clear_firestore_queue
)

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

@pytest.fixture(scope="session")
def mongo_client():
    uri = os.getenv("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI not found.")
    return MongoClient(uri)

@pytest.fixture(scope="session")
def firestore_client():
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds:
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not found.")
    return firestore.Client()

def test_cleanup_dummy_entry(mongo_client, firestore_client):
    """
    Tests the cleanup functions safely by using dummy collections, 
    protecting the real sample data needed for the next phase.
    """
    dummy_mongo_col = "dummy_ground_truth"
    dummy_fs_col = "dummy_triage_queue"
    
    # 1. Insert dummy into MongoDB
    db_mongo = mongo_client["support_triage"]
    db_mongo[dummy_mongo_col].insert_one({"dummy": "data"})
    assert db_mongo[dummy_mongo_col].count_documents({}) == 1
    
    # 2. Insert dummy into Firestore
    doc_ref = firestore_client.collection(dummy_fs_col).document("dummy_doc")
    doc_ref.set({"dummy": "data"})
    assert doc_ref.get().exists
    
    # 3. Test Cleanup Functions
    destroy_ground_truth(mongo_client, collection_name=dummy_mongo_col)
    clear_firestore_queue(firestore_client, collection_name=dummy_fs_col)
    
    # 4. Verify Cleanup
    assert db_mongo[dummy_mongo_col].count_documents({}) == 0
    assert not doc_ref.get().exists
    print("\nDummy cleanup test passed safely.")

def test_init_queue_integration(mongo_client, firestore_client):
    """
    Integration test: Verifies that initialize_queues(mode='test') 
    actually populates MongoDB and Firestore with real data.
    LEAVES the data intact for the next phase.
    """
    # 1. Run initialization
    initialize_queues(mode="test")
    
    # 2. Verify MongoDB Ground Truth
    db_mongo = mongo_client["support_triage"]
    col_truth = db_mongo["test_ground_truth"]
    
    truth_count = col_truth.count_documents({})
    assert truth_count == 10, f"Expected 10 ground truth records, found {truth_count}"
    
    sample_mongo = col_truth.find_one()
    assert "expected_response" in sample_mongo
    assert len(sample_mongo["expected_response"]) > 0
    
    # 3. Verify Firestore Redacted Queue
    col_queue = firestore_client.collection("triage_queue")
    docs = list(col_queue.stream())
    assert len(docs) == 10, f"Expected 10 queue records, found {len(docs)}"
    
    sample_fs = docs[0].to_dict()
    assert "issue" in sample_fs
    assert "subject" in sample_fs
    # Verification of Redaction
    assert "expected_response" not in sample_fs
    assert "Response" not in sample_fs
    assert "Status" not in sample_fs
    assert "Product Area" not in sample_fs
    
    # 4. User Verification Pause
    print("\n\n--- INTEGRATION VERIFICATION ---")
    print("Real data has been initialized in your databases.")
    print("This data is REQUIRED for the next phase. It will NOT be deleted.")
    print("Check MongoDB Atlas (Unredacted): https://cloud.mongodb.com/v2#/clusters")
    print("Check Firestore Console (Redacted): https://console.cloud.google.com/firestore")
    
    input("Press Enter to verify and proceed (data will remain intact)...")
    print("Verification complete. Sample data protected.")

if __name__ == "__main__":
    # Manual run support
    load_dotenv(ENV_PATH)
    m = MongoClient(os.getenv("MONGO_URI"))
    f = firestore.Client()
    test_cleanup_dummy_entry(m, f)
    test_init_queue_integration(m, f)
