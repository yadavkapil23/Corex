document.addEventListener('DOMContentLoaded', () => {
  const queryInput = document.getElementById('queryInput');
  const askButton = document.getElementById('askButton');
  const chatMessages = document.getElementById('chatMessages');

  // 💬 Conversation state management
  let conversationHistory = [];

  // 📄 Document mode state
  let currentMode = 'general'; // 'general' | 'document'
  let uploadedDocument = null; // { documentId, filename }

  // 🖼️ One-shot OCR attachment state (General mode only)
  let attachedImageText = null; // extracted text, folded into the next query only
  let attachedImageName = null;

  function addUserMessage(content, imageDataUrl = null) {
    conversationHistory.push({
      role: 'user',
      content: content,
      timestamp: Date.now(),
      imageDataUrl: imageDataUrl
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
  function renderUserMessage(content, timestamp = null, imageDataUrl = null) {
    const ts = timestamp || Date.now();
    const imagePreview = imageDataUrl
      ? `<img class="attached-image-thumb" src="${imageDataUrl}" alt="Attached image" />`
      : '';
    return `
      <div class="message user" data-timestamp="${ts}">
        <div class="msg-meta"><span class="msg-sender">You</span></div>
        ${imagePreview}
        <div class="message-text">${escapeHtml(content)}</div>
      </div>
    `;
  }

  function renderAssistantMessage(content, source, index) {
    const sourceBadge = source ? `<span class="source-badge">${escapeHtml(source)}</span>` : '';
    return `
      <div class="message assistant">
        <div class="msg-meta">
          <span class="msg-sender">Corex</span>${sourceBadge}
          <button class="speak-btn" data-msg-index="${index}" title="Read aloud">
            <i class="fas fa-volume-high"></i>
          </button>
        </div>
        <div class="message-text">${formatAnswer(content)}</div>
      </div>
    `;
  }

  function renderLoadingMessage() {
    return `
      <div class="message assistant">
        <div class="msg-meta"><span class="msg-sender">Corex</span></div>
        <div class="loading-message">
          <span>Thinking...</span>
          <div class="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>
    `;
  }

  function renderWelcomeMessage() {
    return `
      <div class="welcome-message">
        <h2>Welcome to Corex</h2>
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

    let html = '<div class="chat-scroll-inner">';
    conversationHistory.forEach((msg, index) => {
      if (msg.role === 'user') {
        html += renderUserMessage(msg.content);
      } else {
        html += renderAssistantMessage(msg.content, msg.source, index);
      }
    });
    html += '</div>';
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

    if (currentMode === 'document' && !uploadedDocument) {
      alert('Please upload a document first.');
      return;
    }

    // Add user message to conversation
    addUserMessage(query);
    displayAllMessages();

    // Clear input
    queryInput.value = '';

    // Show loading message
    const loadingMessage = renderLoadingMessage();
    const inner = chatMessages.querySelector('.chat-scroll-inner');
    if (inner) inner.innerHTML += loadingMessage;
    scrollToBottom();

    // Carry the one-shot OCR text (if attached) as separate fields so the
    // backend can ground the answer directly, skipping document retrieval.
    const imageText = attachedImageText;
    const imageName = attachedImageName;
    clearAttachedImage();

    try {
      const endpoint = currentMode === 'document' ? '/documents/query' : '/query/';
      const body = currentMode === 'document'
        ? { query, document_id: uploadedDocument.documentId, conversation_history: getHistory() }
        : { query, conversation_history: getHistory(), attached_image_text: imageText, attached_image_name: imageName };

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${response.status}`);
      }
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

  // 🔀 Mode switching
  const modeGeneralBtn = document.getElementById('modeGeneralBtn');
  const modeDocumentBtn = document.getElementById('modeDocumentBtn');
  const documentPanel = document.getElementById('documentPanel');
  const sessionTitle = document.getElementById('sessionTitle');

  function setMode(mode) {
    currentMode = mode;
    modeGeneralBtn.classList.toggle('active', mode === 'general');
    modeDocumentBtn.classList.toggle('active', mode === 'document');
    documentPanel.hidden = mode !== 'document';
    sessionTitle.textContent = mode === 'document' ? 'My Document' : 'General Chat';
    queryInput.placeholder = mode === 'document' ? 'Ask a question about your document' : 'Compose your message...';
  }

  modeGeneralBtn.addEventListener('click', () => setMode('general'));
  modeDocumentBtn.addEventListener('click', () => setMode('document'));

  // 📁 Sidebar collapse toggle
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
  });

  // 📄 Document upload handling
  const documentFileInput = document.getElementById('documentFileInput');
  const uploadStatus = document.getElementById('uploadStatus');
  const documentUploadEl = document.getElementById('documentUpload');
  const activeDocumentEl = document.getElementById('activeDocument');
  const activeDocumentNameEl = document.getElementById('activeDocumentName');
  const removeDocumentBtn = document.getElementById('removeDocumentBtn');

  documentFileInput.addEventListener('change', async () => {
    const file = documentFileInput.files[0];
    if (!file) return;

    uploadStatus.textContent = `Uploading ${file.name}...`;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/documents/upload', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${response.status}`);
      }

      const data = await response.json();
      uploadedDocument = { documentId: data.document_id, filename: data.filename };
      uploadStatus.textContent = '';
      activeDocumentNameEl.textContent = data.filename;
      documentUploadEl.hidden = true;
      activeDocumentEl.hidden = false;
    } catch (err) {
      uploadStatus.textContent = `Upload failed: ${err.message}`;
    } finally {
      documentFileInput.value = '';
    }
  });

  removeDocumentBtn.addEventListener('click', async () => {
    if (uploadedDocument) {
      try {
        await fetch(`/documents/${uploadedDocument.documentId}`, { method: 'DELETE' });
      } catch (err) {
        console.error('Failed to delete document on server:', err);
      }
    }
    uploadedDocument = null;
    documentUploadEl.hidden = false;
    activeDocumentEl.hidden = true;
    uploadStatus.textContent = '';
  });

  // 🖼️ One-shot image attach + OCR (General mode) — scans an image inline for
  // a single question, then discards the extracted text (no vector store).
  const imageAttachInput = document.getElementById('imageAttachInput');
  const attachedImagePreview = document.getElementById('attachedImagePreview');
  const attachedImageNameEl = document.getElementById('attachedImageName');
  const removeAttachedImageBtn = document.getElementById('removeAttachedImageBtn');

  function clearAttachedImage() {
    attachedImageText = null;
    attachedImageName = null;
    attachedImagePreview.hidden = true;
    imageAttachInput.value = '';
  }

  imageAttachInput.addEventListener('change', async () => {
    const file = imageAttachInput.files[0];
    if (!file) return;

    attachedImageNameEl.textContent = `Scanning ${file.name}...`;
    attachedImagePreview.hidden = false;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/ocr/extract', { method: 'POST', body: formData });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${response.status}`);
      }
      const data = await response.json();
      attachedImageText = data.text;
      attachedImageName = file.name;
      attachedImageNameEl.textContent = file.name;
    } catch (err) {
      alert(`Failed to scan image: ${err.message}`);
      clearAttachedImage();
    }
  });

  removeAttachedImageBtn.addEventListener('click', clearAttachedImage);

  // 🎙️ Voice input (browser Speech-to-Text)
  const micButton = document.getElementById('micButton');
  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognitionImpl) {
    const recognition = new SpeechRecognitionImpl();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    let listening = false;

    recognition.addEventListener('result', (e) => {
      const transcript = e.results[0][0].transcript;
      queryInput.value = transcript;
    });

    recognition.addEventListener('end', () => {
      listening = false;
      micButton.classList.remove('listening');
    });

    recognition.addEventListener('error', () => {
      listening = false;
      micButton.classList.remove('listening');
    });

    micButton.addEventListener('click', () => {
      if (listening) {
        recognition.stop();
        return;
      }
      listening = true;
      micButton.classList.add('listening');
      recognition.start();
    });
  } else {
    micButton.disabled = true;
    micButton.title = 'Voice input is not supported in this browser';
  }

  // 🔊 Read-aloud (browser Text-to-Speech), delegated since messages re-render
  chatMessages.addEventListener('click', (e) => {
    const btn = e.target.closest('.speak-btn');
    if (!btn) return;
    const index = Number(btn.dataset.msgIndex);
    const msg = conversationHistory[index];
    if (!msg || !window.speechSynthesis) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(msg.content);
    window.speechSynthesis.speak(utterance);
  });

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

  // Dropdown menu functionality
  const optionsBtn = document.getElementById('optionsBtn');
  const optionsMenu = document.getElementById('optionsMenu');
  const downloadTxtBtn = document.getElementById('downloadTxt');
  const downloadPdfBtn = document.getElementById('downloadPdf');
  const clearChatBtn = document.getElementById('clearChatBtn');

  // Toggle dropdown menu
  optionsBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    optionsMenu.classList.toggle('show');
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (!optionsBtn.contains(e.target) && !optionsMenu.contains(e.target)) {
      optionsMenu.classList.remove('show');
    }
  });

  // Download as TXT
  downloadTxtBtn.addEventListener('click', () => {
    downloadChatAsTxt();
    optionsMenu.classList.remove('show');
  });

  // Download as PDF
  downloadPdfBtn.addEventListener('click', () => {
    downloadChatAsPdf();
    optionsMenu.classList.remove('show');
  });

  // New session (clear chat)
  clearChatBtn.addEventListener('click', () => {
    clearConversation();
    displayAllMessages();
  });

  // Download functions
  function downloadChatAsTxt() {
    if (conversationHistory.length === 0) {
      alert('No conversation to download');
      return;
    }

    let content = 'Corex Chat History\n';
    content += '='.repeat(50) + '\n\n';
    
    conversationHistory.forEach((msg, index) => {
      const timestamp = new Date(msg.timestamp).toLocaleString();
      const role = msg.role === 'user' ? 'You' : 'Corex';
      const source = msg.source ? ` (${msg.source})` : '';
      
      content += `[${timestamp}] ${role}${source}:\n`;
      content += msg.content + '\n\n';
    });

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `corex-chat-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function downloadChatAsPdf() {
    if (conversationHistory.length === 0) {
      alert('No conversation to download');
      return;
    }

    try {
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF();
      
      // Set up the document
      let yPosition = 20;
      const pageHeight = doc.internal.pageSize.height;
      const pageWidth = doc.internal.pageSize.width;
      const margin = 20;
      const maxWidth = pageWidth - (margin * 2);
      
      // Helper function to add text with word wrapping
      function addTextWithWrap(text, x, y, maxWidth, fontSize = 10) {
        doc.setFontSize(fontSize);
        const lines = doc.splitTextToSize(text, maxWidth);
        doc.text(lines, x, y);
        return y + (lines.length * (fontSize * 0.4));
      }
      
      // Helper function to check if we need a new page
      function checkNewPage(requiredSpace) {
        if (yPosition + requiredSpace > pageHeight - 20) {
          doc.addPage();
          yPosition = 20;
          return true;
        }
        return false;
      }
      
      // Title
      doc.setFontSize(16);
      doc.setFont(undefined, 'bold');
      doc.text('Corex Chat History', pageWidth / 2, yPosition, { align: 'center' });
      yPosition += 10;
      
      // Date
      doc.setFontSize(10);
      doc.setFont(undefined, 'normal');
      doc.text(`Generated on: ${new Date().toLocaleString()}`, pageWidth / 2, yPosition, { align: 'center' });
      yPosition += 15;
      
      // Add a line
      doc.line(margin, yPosition, pageWidth - margin, yPosition);
      yPosition += 10;
      
      // Process each message
      conversationHistory.forEach((msg, index) => {
        const timestamp = new Date(msg.timestamp).toLocaleString();
        const role = msg.role === 'user' ? 'You' : 'Corex';
        const source = msg.source ? ` (${msg.source})` : '';
        
        // Check if we need a new page for this message
        const messageText = `[${timestamp}] ${role}${source}:\n${msg.content}`;
        const estimatedHeight = (messageText.split('\n').length * 4) + 10;
        
        if (checkNewPage(estimatedHeight)) {
          // Add a continuation marker
          doc.setFontSize(8);
          doc.text('...continued from previous page...', margin, yPosition);
          yPosition += 5;
        }
        
        // Message header
        doc.setFontSize(10);
        doc.setFont(undefined, 'bold');
        yPosition = addTextWithWrap(`[${timestamp}] ${role}${source}:`, margin, yPosition, maxWidth, 10);
        
        // Message content
        doc.setFont(undefined, 'normal');
        yPosition = addTextWithWrap(msg.content, margin + 5, yPosition, maxWidth - 5, 9);
        
        // Add some space between messages
        yPosition += 8;
        
        // Add a subtle line between messages (except for the last one)
        if (index < conversationHistory.length - 1) {
          doc.setDrawColor(200, 200, 200);
          doc.line(margin, yPosition, pageWidth - margin, yPosition);
          yPosition += 5;
        }
      });
      
      // Save the PDF
      const fileName = `corex-chat-${new Date().toISOString().split('T')[0]}.pdf`;
      doc.save(fileName);
      
    } catch (error) {
      console.error('Error generating PDF:', error);
      alert('Error generating PDF. Please try downloading as TXT instead.');
    }
  }

  // Scroll to bottom when new messages arrive
  const observer = new MutationObserver(() => {
    scrollToBottom();
  });
  observer.observe(chatMessages, { childList: true, subtree: true });

  // Initialize
  displayAllMessages();
});