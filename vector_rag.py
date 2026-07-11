from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
# Use the generic HuggingFaceEmbeddings for the smaller model
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_huggingface import HuggingFacePipeline
# Remove BitsAndBytesConfig import
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import os
from dotenv import load_dotenv

load_dotenv()

# Set cache directories with fallback for permission issues
os.environ.setdefault('HF_HOME', '/tmp/huggingface_cache')
os.environ.setdefault('TRANSFORMERS_CACHE', '/tmp/huggingface_cache/transformers')
os.environ.setdefault('HF_DATASETS_CACHE', '/tmp/huggingface_cache/datasets')

# --- MODEL INITIALIZATION (Minimal Footprint) ---
print("Loading Qwen2-0.5B-Instruct...")
model_name = "Qwen/Qwen2-0.5B-Instruct" 

# Removed: quantization_config = BitsAndBytesConfig(load_in_8bit=True) 

tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
# Removed: quantization_config parameter from from_pretrained
model = AutoModelForCausalLM.from_pretrained(
    model_name, 
    device_map="cpu", 
    trust_remote_code=True
)

llm_pipeline = pipeline(
    "text-generation", 
    model=model, 
    tokenizer=tokenizer, 
    max_new_tokens=256, 
    do_sample=True,
    temperature=0.5,
    top_p=0.9,
)
llm = HuggingFacePipeline(pipeline=llm_pipeline)

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

# Expose the necessary components for rag.py to import
def _answer_from_docs(docs, query: str, conversation_history: list = None) -> str:
    if not docs:
        return None
    context = "\n\n".join([doc.page_content for doc in docs])

    prompt = "You are a helpful assistant engaged in a conversation.\n\n"

    if conversation_history:
        history_lines = []
        for msg in conversation_history[-10:]:  # Last 10 messages
            role = "User" if msg["role"] == "user" else "Assistant"
            history_lines.append(f"{role}: {msg['content']}")
        history_text = '\n'.join(history_lines)
        prompt += f"Previous conversation:\n{history_text}\n\n"

    prompt += f"""Use the following context from documents to answer the current question:

{context}

Current question: {query}
Answer:"""

    raw_output = llm.invoke(prompt)
    return raw_output.replace(prompt, "").strip()


def query_vector_store(query: str, conversation_history: list = None) -> str:
    """
    Query the built-in sample-document vector store with conversation context.

    Args:
        query: The user's current question
        conversation_history: List of previous messages (optional)

    Returns:
        Answer string or None if no documents found
    """
    if conversation_history is None:
        conversation_history = []

    docs = retriever.invoke(query)
    return _answer_from_docs(docs, query, conversation_history)


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


def query_uploaded_document(vectorstore: FAISS, query: str, conversation_history: list = None) -> str:
    """
    Query a user-uploaded document's vector store with conversation context.

    Args:
        vectorstore: FAISS vector store built from the uploaded document
        query: The user's current question
        conversation_history: List of previous messages (optional)

    Returns:
        Answer string, or a not-found message if nothing relevant was retrieved
    """
    if conversation_history is None:
        conversation_history = []

    docs = vectorstore.as_retriever().invoke(query)
    answer = _answer_from_docs(docs, query, conversation_history)
    return answer or "I couldn't find anything relevant to that question in the uploaded document."