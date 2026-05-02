from pydantic import BaseModel, Field
from typing import List, Optional

# ==========================================
# MongoDB Atlas Schemas
# ==========================================

class KnowledgeBaseChunk(BaseModel):
    """
    Schema for document chunks stored in MongoDB Atlas for Vector Search.
    """
    ecosystem: str  # "hackerrank", "claude", "visa"
    file_path: str
    chunk_index: int
    content: str
    embedding: List[float]  # Vector embedding from gemini-embedding-2

class GroundTruthTicket(BaseModel):
    """
    Schema for the unredacted original support tickets, 
    strictly using the field names from output.csv.
    """
    ticket_id: str = Field(alias="_id")
    issue: str
    subject: str
    company: str
    response: str
    product_area: str
    status: str
    request_type: str
    justification: str

# ==========================================
# Google Cloud Firestore Schemas
# ==========================================

class TriageQueueTicket(BaseModel):
    """
    Schema for the queue processed by the agentic pipeline.
    Strictly using the original field names from output.csv.
    Fields after 'company' are redacted initially.
    """
    ticket_id: str
    issue: str
    subject: str
    company: str
    
    # Feature flag for queue filtering
    processed: bool = False
    
    # Agent Outputs
    product_area: Optional[str] = None
    status: Optional[str] = None
    request_type: Optional[str] = None
    response: Optional[str] = None
    justification: Optional[str] = None
