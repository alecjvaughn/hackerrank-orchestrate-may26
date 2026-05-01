import os
import pytest
from pymongo import MongoClient
from google.cloud import firestore
from google import genai
from dotenv import load_dotenv, dotenv_values

# Path to .env.local
ENV_PATH = ".env.local"

def get_env_keys():
    """
    Returns the list of keys found in the .env.local file.
    """
    if not os.path.exists(ENV_PATH):
        return []
    return list(dotenv_values(ENV_PATH).keys())

@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """
    Loads environment variables from .env.local.
    """
    load_dotenv(ENV_PATH)

def test_secrets_loaded():
    """
    Verifies that all keys present in .env.local are successfully loaded
    into the environment and are not empty.
    """
    keys = get_env_keys()
    if not keys:
        pytest.skip(f"{ENV_PATH} is empty or missing.")
    
    for key in keys:
        value = os.getenv(key)
        assert value is not None, f"Environment variable {key} was not loaded."
        assert value.strip() != "", f"Environment variable {key} is empty."
        print(f"Verified: {key}")

def test_mongodb_connection():
    """
    Verifies that we can connect to MongoDB Atlas and ping the server.
    """
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        pytest.skip("MONGO_URI not found in environment.")
    
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ismaster')
        print("MongoDB connection successful!")
    except Exception as e:
        pytest.fail(f"MongoDB connection failed: {e}")

def test_firestore_connection():
    """
    Verifies that we can connect to Firestore.
    """
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not found or invalid.")
    
    try:
        db = firestore.Client()
        # Attempt to list collections as a ping
        collections = list(db.collections())
        print(f"Firestore connection successful! Found {len(collections)} collections.")
    except Exception as e:
        pytest.fail(f"Firestore connection failed: {e}")

def test_gemini_model_ping():
    """
    Verifies that we can connect to the Gemini model and perform a simple ping.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("GOOGLE_API_KEY not found in environment.")
    
    try:
        client = genai.Client(api_key=api_key)
        # Using gemini-2.5-flash as discovered in models.list()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents="ping"
        )
        assert response.text is not None
        print("Gemini model ping successful!")
    except Exception as e:
        pytest.fail(f"Gemini model ping failed: {e}")

if __name__ == "__main__":
    # Manual run support
    load_dotenv(ENV_PATH)
    test_secrets_loaded()
    test_mongodb_connection()
    test_firestore_connection()
    test_gemini_model_ping()
