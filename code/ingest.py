import os
import re
import argparse
from pathlib import Path
from pymongo import MongoClient
from google import genai
from dotenv import load_dotenv
from schemas import KnowledgeBaseChunk

# Path to .env.local
ENV_PATH = ".env.local"
load_dotenv(ENV_PATH)

def generate_embedding(client: genai.Client, text: str) -> list[float]:
    """
    Generates a vector embedding for the given text using gemini-embedding-2.
    """
    result = client.models.embed_content(
        model='gemini-embedding-2',
        contents=text
    )
    return result.embeddings[0].values

def chunk_by_markdown_headers(content: str, max_chunk_size: int = 1500) -> list[str]:
    """
    Splits markdown content by headers (## or #).
    This provides the best ROI for index files by keeping related links 
    (under the same category header) grouped together semantically.
    """
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in content.split('\n'):
        # If it's a header and we already have content, finalize the current chunk
        if re.match(r'^#{1,3}\s', line) and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = len(line)
        else:
            # If adding this line exceeds a soft max size, split anyway
            if current_length + len(line) > max_chunk_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_length = len(line)
            else:
                current_chunk.append(line)
                current_length += len(line) + 1 # +1 for newline
                
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
        
    return chunks

def ingest_corpus(mode: str = "minimal"):
    """
    Ingests the corpus into MongoDB Atlas.
    
    mode: "minimal" (only index files) or "full" (all markdown files).
    """
    mongo_uri = os.getenv("MONGO_URI")
    api_key = os.getenv("GOOGLE_API_KEY")
    
    if not mongo_uri or not api_key:
        print("Error: MONGO_URI or GOOGLE_API_KEY missing from .env.local")
        return

    client = MongoClient(mongo_uri)
    db = client["support_triage"]
    collection = db["knowledge_base"]
    
    genai_client = genai.Client(api_key=api_key)
    data_path = Path("data")
    
    files_to_process = []
    
    if mode == "minimal":
        print(f"[{mode.upper()}] Preparing to ingest core index and support files...")
        # Include visa/index.md and visa/support.md as requested
        files_to_process = [
            data_path / "visa" / "index.md",
            data_path / "visa" / "support.md",
            data_path / "hackerrank" / "index.md",
            data_path / "claude" / "index.md"
        ]
    else:
        print(f"[{mode.upper()}] Preparing to ingest the entire corpus...")
        ecosystems = ["visa", "hackerrank", "claude"]
        for eco in ecosystems:
            files_to_process.extend(list((data_path / eco).rglob("*.md")))
            
    db_chunks = []
    
    for file_path in files_to_process:
        if not file_path.exists():
            print(f"Warning: {file_path} not found. Skipping.")
            continue
            
        ecosystem = file_path.parts[1] if len(file_path.parts) > 1 else "unknown"
        print(f"Processing {ecosystem}: {file_path.name}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # ROI EVALUATION: Header grouping is best for index files to maintain category context.
        text_chunks = chunk_by_markdown_headers(content)
        
        for i, text_chunk in enumerate(text_chunks):
            if not text_chunk.strip():
                continue
                
            embedding = generate_embedding(genai_client, text_chunk)
            
            chunk_doc = KnowledgeBaseChunk(
                ecosystem=ecosystem,
                file_path=str(file_path.relative_to(data_path)),
                chunk_index=i,
                content=text_chunk,
                embedding=embedding
            )
            
            db_chunks.append(chunk_doc.model_dump())
    
    if db_chunks:
        # Clear existing knowledge base before new ingestion
        collection.delete_many({})
        collection.insert_many(db_chunks)
        print(f"Successfully ingested {len(db_chunks)} chunks into MongoDB Atlas.")
    else:
        print("No files found to ingest.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest support corpus into MongoDB Atlas.")
    parser.add_argument("--mode", choices=["minimal", "full"], default="minimal", help="Ingestion mode")
    args = parser.parse_args()
    
    ingest_corpus(mode=args.mode)
