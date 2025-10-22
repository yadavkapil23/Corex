document.addEventListener('DOMContentLoaded', () => {
  const queryInput = document.getElementById('queryInput');
  const askButton = document.getElementById('askButton');
  const chatMessages = document.getElementById('chatMessages');
  
  // 💬 Conversation state management
  let conversationHistory = [];

  function addUserMessage(content) {
    conversationHistory.push({
      role: 'user',
      content: content,
      timestamp: Date.now()
    });
  }

  function addAssistantMessage(content, source) {
    conversationHistory.push({
      role: 'assistant',
      content: content,
      timestamp: Date.now(),
      source: source
    });
  }

  function clearConversation() {
    conversationHistory = [];
  }

  function getHistory() {
    return conversationHistory;
  }

  // 💬 Message rendering functions
  function renderUserMessage(content) {
    return `
      <div class="message user">
        <div class="message-avatar">
          <i class="fas fa-user"></i>
        </div>
        <div class="message-content">
          <div class="message-bubble">
            <div class="message-text">${escapeHtml(content)}</div>
          </div>
        </div>
      </div>
    `;
  }

  function renderAssistantMessage(content, source) {
    const sourceBadge = source ? `<span class="source-badge">${source}</span>` : '';
    return `
      <div class="message assistant">
        <div class="message-avatar">
          <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
          ${sourceBadge}
          <div class="message-bubble">
            <div class="message-text">${formatAnswer(content)}</div>
          </div>
          <div class="message-actions">
            <button class="action-btn" title="Like">
              <i class="fas fa-thumbs-up"></i>
            </button>
            <button class="action-btn" title="Dislike">
              <i class="fas fa-thumbs-down"></i>
            </button>
            <button class="action-btn" title="Share">
              <i class="fas fa-share"></i>
            </button>
            <button class="action-btn" title="Regenerate">
              <i class="fas fa-redo"></i>
            </button>
            <button class="action-btn" title="More options">
              <i class="fas fa-ellipsis-h"></i>
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function renderLoadingMessage() {
    return `
      <div class="message assistant">
        <div class="message-avatar">
          <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
          <div class="message-bubble">
            <div class="loading-message">
              <span>Thinking...</span>
              <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderWelcomeMessage() {
    return `
      <div class="welcome-message">
        <h2>Welcome to NeoBot!</h2>
        <p>Ask me anything and I'll help you with accurate, document-backed answers.</p>
      </div>
    `;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function displayAllMessages() {
    if (conversationHistory.length === 0) {
      chatMessages.innerHTML = renderWelcomeMessage();
      return;
    }

    let html = '';
    conversationHistory.forEach(msg => {
      if (msg.role === 'user') {
        html += renderUserMessage(msg.content);
      } else {
        html += renderAssistantMessage(msg.content, msg.source);
      }
    });
    chatMessages.innerHTML = html;
    scrollToBottom();
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function formatAnswer(text) {
    if (typeof text !== "string") {
      text = String(text ?? "No response received.");
    }
    return text
      .split('\n')
      .filter(line => line.trim())
      .map(line => `<p>${line}</p>`)
      .join('');
  }

  // 🔍 Query handler
  async function handleQuery() {
    const query = queryInput.value.trim();
    if (!query) return;

    // Add user message to conversation
    addUserMessage(query);
    displayAllMessages();

    // Clear input
    queryInput.value = '';

    // Show loading message
    const loadingMessage = renderLoadingMessage();
    chatMessages.innerHTML += loadingMessage;
    scrollToBottom();

    try {
      // Send conversation history to backend
      const response = await fetch('/query/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          conversation_history: getHistory()
        })
      });

      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const data = await response.json();

      // Remove loading message and add assistant response
      chatMessages.innerHTML = chatMessages.innerHTML.replace(loadingMessage, '');
      addAssistantMessage(data.response, data.source);
      displayAllMessages();

    } catch (err) {
      // Remove loading message and add error message
      chatMessages.innerHTML = chatMessages.innerHTML.replace(loadingMessage, '');
      addAssistantMessage(`Failed to get response: ${err.message}`, 'Error');
      displayAllMessages();
    }
  }

  // 🔗 Event listeners
  askButton.addEventListener('click', handleQuery);
  queryInput.addEventListener('keypress', e => {
    if (e.key === 'Enter') handleQuery();
  });

  // Auto-resize input
  queryInput.addEventListener('input', () => {
    queryInput.style.height = 'auto';
    queryInput.style.height = queryInput.scrollHeight + 'px';
  });

  // Scroll to bottom when new messages arrive
  const observer = new MutationObserver(() => {
    scrollToBottom();
  });
  observer.observe(chatMessages, { childList: true, subtree: true });

  // Initialize
  displayAllMessages();
});