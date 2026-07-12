from vector_rag import query_vector_store, llm # <--- FIX: Import llm here!
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
    "i don't know",
    "i do not know",
    "don't have that information",
    "do not have that information",
    "doesn't contain the answer",
    "does not contain the answer",
    "cannot answer",
    "can't answer",
    "no relevant information",
    "not mentioned in the",
    "not contain information",
)


def _is_unanswered(answer: str) -> bool:
    """
    Detect an LLM refusal ("I don't know" etc.) so the fallback chain treats it
    as retrieval having effectively failed, rather than a real grounded answer.
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
    Get a RAG-first response: always retrieve from the local document store first
    and generate a grounded answer from it. Only when retrieval finds nothing
    relevant do we fall back to Wikipedia, then a raw LLM guess.

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

    # First: Retrieval-Augmented Generation over the local document store
    try:
        print("Retrieving from local vector store")
        answer, sources = query_vector_store(query, conversation_history)
        if answer and not _is_unanswered(answer):
            source_label = "Local Document" + (f" ({'; '.join(sources)})" if sources else "")
            return answer, source_label
    except Exception as e:
        print("Error during local vector search:", e)

    # Second: Fallback to Wikipedia when retrieval found nothing relevant
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
