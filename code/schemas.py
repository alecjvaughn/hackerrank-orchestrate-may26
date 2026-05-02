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
    embedding: List[float]  # Vector embedding from text-embedding-004

class GroundTruthTicket(BaseModel):
    """
    Schema for the unredacted original support tickets, 
    used to calculate accuracy during the TDD loop.
    """
    ticket_id: str = Field(alias="_id")
    issue: str
    subject: str
    company: str
    expected_response: str
    expected_product_area: str
    expected_status: str
    expected_request_type: str
    expected_justification: str

# ==========================================
# Google Cloud Firestore Schemas
# ==========================================

class TriageQueueTicket(BaseModel):
    """
    Schema for the queue processed by the agentic pipeline.
    Fields after 'company' are redacted initially.
    """
    ticket_id: str
    issue: str
    subject: str
    company: str
    
    # Feature flag for queue filtering
    processed: bool = False
    
    # Agent Outputs
    predicted_product_area: Optional[str] = None
    # Array storing [triage_conf, retrieval_conf, gen_conf]
    confidence_scores: List[float] = Field(default_factory=list)
    
    predicted_status: Optional[str] = None
    predicted_request_type: Optional[str] = None
    predicted_response: Optional[str] = None
    justification: Optional[str] = None
