import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Literal, Optional

router = APIRouter()

from rag import get_smart_rag_response, answer_from_attached_image
from vector_rag import (
    build_vectorstore_from_file,
    build_vectorstore_from_text,
    query_uploaded_document,
    extract_text_from_image,
)

# Pydantic models for request/response validation
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class QueryRequest(BaseModel):
    query: str
    conversation_history: List[Message] = []
    attached_image_text: Optional[str] = None
    attached_image_name: Optional[str] = None

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

class OcrResponse(BaseModel):
    text: str

@router.post("/query/")
async def query_rag_system(request: QueryRequest):
    try:
        # Convert Pydantic models to dicts for processing
        history = [msg.dict() for msg in request.conversation_history]

        if request.attached_image_text:
            response = answer_from_attached_image(
                request.query, request.attached_image_text, history
            )
            return QueryResponse(
                query=request.query,
                response=response,
                source=f"Scanned Image ({request.attached_image_name})" if request.attached_image_name else "Scanned Image",
            )

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
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
IMAGE_MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()

    if ext in ALLOWED_IMAGE_EXTENSIONS:
        try:
            image_bytes = await file.read()
            extracted_text = extract_text_from_image(image_bytes, IMAGE_MIME_TYPES[ext])
            vectorstore = build_vectorstore_from_text(extracted_text, file.filename)
            document_id = str(uuid.uuid4())
            _uploaded_vectorstores[document_id] = vectorstore
            return UploadResponse(document_id=document_id, filename=file.filename)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, TXT, PNG, and JPG files are supported.")

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

@router.post("/ocr/extract", response_model=OcrResponse)
async def ocr_extract(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PNG and JPG images are supported.")

    try:
        image_bytes = await file.read()
        extracted_text = extract_text_from_image(image_bytes, IMAGE_MIME_TYPES[ext])
        return OcrResponse(text=extracted_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    _uploaded_vectorstores.pop(document_id, None)
    return {"status": "deleted"}

@router.post("/documents/query", response_model=QueryResponse)
async def query_document(request: DocumentQueryRequest):
    vectorstore = _uploaded_vectorstores.get(request.document_id)
    if vectorstore is None:
        raise HTTPException(status_code=404, detail="Document not found. Please upload it again.")

    try:
        history = [msg.dict() for msg in request.conversation_history]
        answer, sources = query_uploaded_document(vectorstore, request.query, history)
        source_label = "Uploaded Document" + (f" ({'; '.join(sources)})" if sources else "")
        return QueryResponse(query=request.query, response=answer, source=source_label)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
