import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Literal, Optional

router = APIRouter()

from rag import get_smart_rag_response
from vector_rag import build_vectorstore_from_file, query_uploaded_document

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

class DocumentQueryRequest(BaseModel):
    query: str
    document_id: str
    conversation_history: List[Message] = []

class UploadResponse(BaseModel):
    document_id: str
    filename: str

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


# In-memory store of uploaded documents' vector stores, keyed by document_id.
# Single-process, non-persistent: resets on server restart, not shared across workers.
_uploaded_vectorstores = {}

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".txt"}

@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        vectorstore = build_vectorstore_from_file(tmp_path)
        document_id = str(uuid.uuid4())
        _uploaded_vectorstores[document_id] = vectorstore

        return UploadResponse(document_id=document_id, filename=file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@router.post("/documents/query", response_model=QueryResponse)
async def query_document(request: DocumentQueryRequest):
    vectorstore = _uploaded_vectorstores.get(request.document_id)
    if vectorstore is None:
        raise HTTPException(status_code=404, detail="Document not found. Please upload it again.")

    try:
        history = [msg.dict() for msg in request.conversation_history]
        answer = query_uploaded_document(vectorstore, request.query, history)
        return QueryResponse(query=request.query, response=answer, source="Uploaded Document")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
