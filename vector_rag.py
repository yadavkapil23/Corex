from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI
# Use the generic HuggingFaceEmbeddings for the smaller model
from langchain_huggingface import HuggingFaceEmbeddings
import os
from dotenv import load_dotenv

load_dotenv()

# Set cache directories with fallback for permission issues
os.environ.setdefault('HF_HOME', '/tmp/huggingface_cache')
os.environ.setdefault('TRANSFORMERS_CACHE', '/tmp/huggingface_cache/transformers')
os.environ.setdefault('HF_DATASETS_CACHE', '/tmp/huggingface_cache/datasets')

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b")

if not NVIDIA_API_KEY:
    raise RuntimeError(
        "NVIDIA_API_KEY is not set. This app requires an NVIDIA NIM API key "
        "(https://build.nvidia.com) — set it in your .env file."
    )


class _StringLLM:
    """Wraps a chat model so .invoke(prompt) returns a plain string, matching
    the interface the rest of the app expects."""

    def __init__(self, chat_model):
        self._chat_model = chat_model

    def invoke(self, prompt: str) -> str:
        return self._chat_model.invoke(prompt).content


print(f"Using NVIDIA NIM model: {NVIDIA_MODEL}")
llm = _StringLLM(ChatOpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY,
    model=NVIDIA_MODEL,
    temperature=0.2,
    max_tokens=512,
))

NVIDIA_VISION_MODEL = os.environ.get("NVIDIA_VISION_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
vision_llm = ChatOpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY,
    model=NVIDIA_VISION_MODEL,
    temperature=0.0,
    max_tokens=2048,
    timeout=60,
)


def extract_text_from_image(image_bytes: bytes, mime_type: str) -> str:
    """
    OCR an image via NVIDIA's hosted vision model.

    Args:
        image_bytes: Raw image file bytes
        mime_type: e.g. "image/png", "image/jpeg"

    Returns:
        Extracted text content of the image.
    """
    import base64
    from langchain_core.messages import HumanMessage

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    message = HumanMessage(content=[
        {"type": "text", "text": "Extract and transcribe all text visible in this image. Return only the extracted text, with no commentary."},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
    ])
    response = vision_llm.invoke([message])
    return response.content.strip()

# Use the lighter all-MiniLM-L6-v2 embeddings model
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2") 

# --- DOCUMENT LOADING & CHUNKING ---
loader = PyPDFLoader("data/sample.pdf") # Correct path for Docker: data/sample.pdf
documents = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = text_splitter.split_documents(documents)

if not chunks:
    raise ValueError("No document chunks found.")

# Initialize FAISS and retriever
vectorstore = FAISS.from_documents(chunks, embeddings)
retriever = vectorstore.as_retriever()

# FAISS uses L2 distance by default: lower = more similar. Chunks scoring above
# this are considered irrelevant "noise" matches and dropped before generation.
# Calibrated empirically against all-MiniLM-L6-v2: prose documents score ~1.5-1.8
# for vague queries, but short/sparse content (OCR output, code snippets) can
# score up to ~2.0 even when genuinely relevant, so the threshold is set above that.
RELEVANCE_DISTANCE_THRESHOLD = 2.1


def _retrieve_relevant(vectorstore: FAISS, query: str, k: int = 4):
    """
    Retrieve chunks with their similarity distance, filtered to relevant matches only.

    Returns:
        List of (doc, score) tuples, most relevant first.
    """
    scored_docs = vectorstore.similarity_search_with_score(query, k=k)
    return [(doc, score) for doc, score in scored_docs if score <= RELEVANCE_DISTANCE_THRESHOLD]


def _format_sources(scored_docs) -> list:
    sources = []
    for doc, score in scored_docs:
        page = doc.metadata.get("page")
        source_file = doc.metadata.get("source", "document")
        label = f"{os.path.basename(source_file)}" + (f", page {page + 1}" if page is not None else "")
        sources.append(label)
    return sources


def _answer_from_docs(scored_docs, query: str, conversation_history: list = None):
    """
    Generate an answer grounded in retrieved chunks.

    Returns:
        Tuple of (answer, sources) or (None, []) if nothing relevant was retrieved.
    """
    if not scored_docs:
        return None, []

    context = "\n\n".join([doc.page_content for doc, _ in scored_docs])

    prompt = "You are a helpful assistant engaged in a conversation.\n\n"

    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:  # Last 10 messages
            role = "User" if msg["role"] == "user" else "Assistant"
            history_lines.append(f"{role}: {msg['content']}")
        history_text = '\n'.join(history_lines)
        prompt += f"Previous conversation:\n{history_text}\n\n"

    prompt += f"""Answer the question using ONLY the context below. If the context doesn't contain the answer, say you don't know — do not make anything up.

Context:
{context}

Current question: {query}
Answer:"""

    raw_output = llm.invoke(prompt)
    answer = raw_output.replace(prompt, "").strip()
    return answer, _format_sources(scored_docs)


def query_vector_store(query: str, conversation_history: list = None):
    """
    Retrieve from the built-in sample-document vector store and generate a grounded answer.

    Args:
        query: The user's current question
        conversation_history: List of previous messages (optional)

    Returns:
        Tuple of (answer, sources) — answer is None if nothing relevant was retrieved.
    """
    if conversation_history is None:
        conversation_history = []

    scored_docs = _retrieve_relevant(vectorstore, query)
    return _answer_from_docs(scored_docs, query, conversation_history)


def build_vectorstore_from_file(file_path: str) -> FAISS:
    """
    Build a standalone FAISS vector store from a single uploaded PDF or TXT file.

    Args:
        file_path: Path to the uploaded file on disk

    Returns:
        A FAISS vector store built from the file's chunks

    Raises:
        ValueError: if the file type is unsupported or no text could be extracted
    """
    if file_path.lower().endswith(".pdf"):
        loader = PyPDFLoader(file_path)
    elif file_path.lower().endswith(".txt"):
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError("Unsupported file type. Please upload a PDF or TXT file.")

    docs = loader.load()
    chunks = text_splitter.split_documents(docs)
    if not chunks:
        raise ValueError("No text could be extracted from the uploaded document.")

    return FAISS.from_documents(chunks, embeddings)


def build_vectorstore_from_text(text: str, source_name: str) -> FAISS:
    """
    Build a standalone FAISS vector store from raw extracted text (e.g. OCR output).

    Args:
        text: Extracted text content
        source_name: Label to attach as the chunk's source metadata

    Returns:
        A FAISS vector store built from the text's chunks

    Raises:
        ValueError: if no chunks could be produced
    """
    from langchain_core.documents import Document

    doc = Document(page_content=text, metadata={"source": source_name})
    chunks = text_splitter.split_documents([doc])
    if not chunks:
        raise ValueError("No text could be extracted from the uploaded image.")

    return FAISS.from_documents(chunks, embeddings)


def query_uploaded_document(vectorstore: FAISS, query: str, conversation_history: list = None):
    """
    Retrieve from a user-uploaded document's vector store and generate a grounded answer.

    Args:
        vectorstore: FAISS vector store built from the uploaded document
        query: The user's current question
        conversation_history: List of previous messages (optional)

    Returns:
        Tuple of (answer, sources). Answer falls back to a not-found message
        if nothing relevant was retrieved.
    """
    if conversation_history is None:
        conversation_history = []

    scored_docs = _retrieve_relevant(vectorstore, query)
    answer, sources = _answer_from_docs(scored_docs, query, conversation_history)
    if answer is None:
        answer = "I couldn't find anything relevant to that question in the uploaded document."
    return answer, sources