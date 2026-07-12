from vector_rag import query_uploaded_document, llm
import wikipedia
from typing import List, Dict
# REMOVED: All duplicate model/pipeline/tokenizer imports and initialization code

# The 'llm' instance is now imported from vector_rag.py and is ready to use.
wikipedia.set_lang("en")

def format_conversation_context(history: List[Dict], max_messages: int = 10) -> str:
    """
    Formats conversation history into a context string for the LLM.
    Keeps only the most recent messages to prevent token overflow.
    
    Args:
        history: List of message dicts with 'role' and 'content' keys
        max_messages: Maximum number of messages to include (default: 10)
    
    Returns:
        Formatted conversation history string
    """
    if not history:
        return ""
    
    # Keep only the last N messages
    recent_history = history[-max_messages:]
    
    formatted_lines = []
    for msg in recent_history:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted_lines.append(f"{role}: {msg['content']}")
    
    return "\n".join(formatted_lines)

_UNANSWERED_PHRASES = (
    "don't know",
    "do not know",
    "don't have",
    "do not have",
    "doesn't contain",
    "does not contain",
    "doesn't have",
    "does not have",
    "cannot answer",
    "can't answer",
    "no relevant information",
    "no information",
    "not mentioned in the",
    "not contain information",
    "unable to answer",
    "unable to find",
)


def _is_unanswered(answer: str) -> bool:
    """
    Detect an LLM refusal ("I don't know", "I don't have information on that",
    etc.) so the fallback chain treats it as retrieval having effectively
    failed, rather than a real grounded answer.
    """
    normalized = answer.strip().lower()
    if not normalized:
        return True
    # Refusals are typically short, standalone statements — a longer answer
    # that merely mentions one of these phrases in passing should still count
    # as a real answer.
    if len(normalized) > 150:
        return False
    return any(phrase in normalized for phrase in _UNANSWERED_PHRASES)


def answer_from_attached_image(query: str, image_text: str, conversation_history: List[Dict] = None) -> str:
    """
    Answer a question grounded in text OCR'd from a one-shot attached image.
    Bypasses document retrieval entirely — the image text IS the context.

    Args:
        query: The user's question
        image_text: Text extracted from the attached image via OCR
        conversation_history: List of previous messages (optional)

    Returns:
        The generated answer.
    """
    context_str = format_conversation_context(conversation_history or [])

    prompt = "You are a helpful assistant engaged in a conversation.\n\n"
    if context_str:
        prompt += f"Previous conversation:\n{context_str}\n\n"
    prompt += f"""Answer the question using ONLY the text below, extracted from an image the user attached. If it doesn't contain the answer, say so — do not make anything up.

Extracted image text:
{image_text}

Current question: {query}
Answer:"""

    result = llm.invoke(prompt)
    return result.replace(prompt, "").strip()


async def get_smart_rag_response(query: str, conversation_history: List[Dict] = None) -> tuple[str, str]:
    """
    Get a response for General chat mode: pure conversational chat, no document
    retrieval. Tries Wikipedia first (for factual lookups), then falls back to
    the LLM's own knowledge. Document Q&A is handled separately by
    answer_from_uploaded_document(), scoped to "My Document" mode only.

    Args:
        query: The user's current question
        conversation_history: List of previous messages (optional)

    Returns:
        Tuple of (response, source)
    """
    print(" Received Query:", query)

    if conversation_history is None:
        conversation_history = []

    context_str = format_conversation_context(conversation_history)

    # First: Wikipedia, for factual lookups
    try:
        summary = wikipedia.summary(query, sentences=5)
        print("Wikipedia summary found.")

        prompt = "You are a helpful assistant engaged in a conversation.\n"
        if context_str:
            prompt += f"\nPrevious conversation:\n{context_str}\n\n"
        prompt += f"""Use the following Wikipedia information to answer the current question as clearly as possible.

Wikipedia Context:
{summary}

Current question: {query}
Answer:"""
        result = llm.invoke(prompt)
        answer = result.replace(prompt, "").strip()
        return answer, "Wikipedia"
    except wikipedia.exceptions.PageError:
        print("Wikipedia page not found.")
    except wikipedia.exceptions.DisambiguationError as e:
        return f"The query is ambiguous. Did you mean: {', '.join(e.options[:5])}", "Wikipedia"
    except Exception as e:
        print("Error during Wikipedia lookup:", e)

    # Finally: Fallback to a raw LLM guess, with no grounding
    try:
        print("Fallback: LLM with conversation context (ungrounded)")

        fallback_prompt = "You are a knowledgeable assistant engaged in a conversation.\n\n"
        if context_str:
            fallback_prompt += f"Previous conversation:\n{context_str}\n\n"
        fallback_prompt += f"Current question: {query}\nAnswer:"

        llm_answer = llm.invoke(fallback_prompt)
        answer = llm_answer.replace(fallback_prompt, "").strip()
        if answer and "not sure" not in answer.lower():
            return answer.strip(), "LLM"
    except Exception as e:
        print("Error during LLM fallback:", e)

    return "Sorry, I couldn't find any information to answer your question.", "System"


def answer_from_uploaded_document(vectorstore, query: str, conversation_history: List[Dict] = None) -> tuple[str, str]:
    """
    Get a response for "My Document" mode: retrieve from the uploaded document
    first. If it doesn't contain the answer, fall back to the LLM's own
    knowledge rather than dead-ending on "I don't know" — the fallback is
    clearly labeled so it's obvious the answer isn't grounded in the document.

    Args:
        vectorstore: FAISS vector store built from the uploaded document
        query: The user's current question
        conversation_history: List of previous messages (optional)

    Returns:
        Tuple of (response, source)
    """
    if conversation_history is None:
        conversation_history = []

    answer, sources = query_uploaded_document(vectorstore, query, conversation_history)
    if answer and not _is_unanswered(answer):
        source_label = "Uploaded Document" + (f" ({'; '.join(sources)})" if sources else "")
        return answer, source_label

    # The document didn't have the answer — fall back to the LLM's own knowledge
    context_str = format_conversation_context(conversation_history)
    fallback_prompt = "You are a knowledgeable assistant engaged in a conversation.\n\n"
    if context_str:
        fallback_prompt += f"Previous conversation:\n{context_str}\n\n"
    fallback_prompt += f"Current question: {query}\nAnswer:"

    llm_answer = llm.invoke(fallback_prompt)
    fallback_answer = llm_answer.replace(fallback_prompt, "").strip()
    return fallback_answer, "General Knowledge"
