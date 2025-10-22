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

async def get_smart_rag_response(query: str, conversation_history: List[Dict] = None) -> tuple[str, str]:
    """
    Get a smart RAG response with conversation context.
    
    Args:
        query: The user's current question
        conversation_history: List of previous messages (optional)
    
    Returns:
        Tuple of (response, source)
    """
    print(" Received Query:", query)
    
    if conversation_history is None:
        conversation_history = []
    
    # Format conversation history for context
    context_str = format_conversation_context(conversation_history)

    # First: Try Wikipedia
    try:
        summary = wikipedia.summary(query, sentences=5)
        print("Wikipedia summary found.")
        
        # Build prompt with conversation context
        prompt = f"""You are a helpful assistant engaged in a conversation.
"""
        if context_str:
            prompt += f"""
Previous conversation:
{context_str}

"""
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

    # Second: Fallback to LLM with conversation context
    try:
        print("Fallback: LLM with conversation context")
        
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

    # Finally: Fallback to Local Documents
    try:
        print("Fallback: Local vector search")
        vector_answer = query_vector_store(query, conversation_history)
        if vector_answer:
            return vector_answer, "Local Document"
    except Exception as e:
        print("Error during local vector search:", e)

    return "Sorry, I couldn't find any information to answer your question.", "System"
