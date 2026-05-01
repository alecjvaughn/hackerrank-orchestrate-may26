import os
import pytest
from pymongo import MongoClient
from google.cloud import firestore
from dotenv import load_dotenv

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """
    Ensures environment variables are loaded.
    """
    load_dotenv(ENV_PATH)

def test_mongodb_data_io():
    """
    Verifies that we can connect to MongoDB Atlas, write a test document,
    read it back, wait for user validation with console URI, and then delete it.
    """
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        pytest.skip("MONGO_URI not found in environment.")
    
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client["test_database_io"]
        collection = db["test_collection_io"]
        
        # 1. Write
        test_data = {"phase": 2, "test_key": "test_value"}
        result = collection.insert_one(test_data)
        doc_id = result.inserted_id
        assert doc_id is not None, "Failed to insert document into MongoDB"
        
        # 2. Read
        doc = collection.find_one({"_id": doc_id})
        assert doc is not None, "Failed to read document from MongoDB"
        assert doc["test_key"] == "test_value"
        
        # 3. User Validation with URI
        print("\n\n--- [PHASE 2] MONGODB VALIDATION ---")
        print(f"Document written to: test_database_io.test_collection_io")
        print(f"Document ID: {doc_id}")
        print("Check MongoDB Atlas: https://cloud.mongodb.com/v2#/clusters")
        input("Press Enter to approve deletion and clean up...")
        
        # 4. Cleanup
        collection.delete_one({"_id": doc_id})
        print("MongoDB cleanup successful!")
    except Exception as e:
        pytest.fail(f"MongoDB data I/O failed: {e}")

def test_firestore_data_io():
    """
    Verifies that we can connect to Firestore, write a test document,
    read it back, wait for user validation with console URI, and then delete it.
    """
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    project_id = os.getenv("GCP_PROJECT_ID")
    if not creds_path or not os.path.exists(creds_path):
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not found or invalid.")
    
    try:
        db = firestore.Client()
        collection_name = "test_collection_io"
        doc_id = "test_document_io"
        doc_ref = db.collection(collection_name).document(doc_id)
        
        # 1. Write
        test_data = {"phase": 2, "test_key": "test_value"}
        doc_ref.set(test_data)
        
        # 2. Read
        doc = doc_ref.get()
        assert doc.exists, "Failed to write or find document in Firestore"
        data = doc.to_dict()
        assert data["test_key"] == "test_value"
        
        # 3. User Validation with URI
        print("\n\n--- [PHASE 2] FIRESTORE VALIDATION ---")
        if project_id:
            firestore_uri = f"https://console.cloud.google.com/firestore/databases/-default-/data/panel/{collection_name}/{doc_id}?project={project_id}"
        else:
            firestore_uri = "https://console.cloud.google.com/firestore"
            
        print(f"Document written to path: {doc_ref.path}")
        print(f"Check Firestore Console: {firestore_uri}")
        input("Press Enter to approve deletion and clean up...")
        
        # 4. Cleanup
        doc_ref.delete()
        print("Firestore cleanup successful!")
    except Exception as e:
        pytest.fail(f"Firestore data I/O failed: {e}")

if __name__ == "__main__":
    # Manual run support
    load_dotenv(ENV_PATH)
    test_mongodb_data_io()
    test_firestore_data_io()
