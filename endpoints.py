from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Literal

router = APIRouter()

from rag import get_smart_rag_response

# Pydantic models for request/response validation
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class QueryRequest(BaseModel):
    query: str
    conversation_history: List[Message] = []

class QueryResponse(BaseModel):
    query: str
    response: str
    source: str

@router.post("/query/")
async def query_rag_system(request: QueryRequest):
    try:
        # Convert Pydantic models to dicts for processing
        history = [msg.dict() for msg in request.conversation_history]
        response, source = await get_smart_rag_response(request.query, history)
        return QueryResponse(
            query=request.query,
            response=response,
            source=source
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
