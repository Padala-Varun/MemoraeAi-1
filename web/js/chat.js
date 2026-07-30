/**
 * MemoraeAI — Chat Page Logic
 * Session management, message send/receive, typing indicator.
 */

document.addEventListener('DOMContentLoaded', () => {
    AppState.load();
    if (!AppState.requireAuth()) return;

    initChatUI();
    loadSessions();
});

let isSending = false;

// ── Initialize Chat UI ──
function initChatUI() {
    // Set user info in nav
    const username = AppState.get('username') || 'User';
    const avatarEl = document.getElementById('nav-user-avatar');
    const nameEl = document.getElementById('nav-user-name');
    if (avatarEl) avatarEl.textContent = username.charAt(0).toUpperCase();
    if (nameEl) nameEl.textContent = username;

    // Message input
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    input.addEventListener('input', () => {
        // Auto-resize textarea
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 160) + 'px';
        sendBtn.disabled = !input.value.trim();
    });

    sendBtn.addEventListener('click', sendMessage);

    // New chat button
    document.getElementById('new-chat-btn')?.addEventListener('click', startNewChat);

    // Sidebar toggle (mobile)
    document.getElementById('sidebar-toggle')?.addEventListener('click', toggleSidebar);
    document.getElementById('sidebar-overlay')?.addEventListener('click', toggleSidebar);

    // Logout
    document.getElementById('logout-btn')?.addEventListener('click', () => AppState.logout());

    // Suggestion chips
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            input.value = chip.textContent;
            input.dispatchEvent(new Event('input'));
            input.focus();
        });
    });
}

// ── Sessions ──
async function loadSessions() {
    const userId = AppState.get('userId');
    const listEl = document.getElementById('session-list');

    try {
        const sessions = await api.getSessions(userId);

        if (!sessions || sessions.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state" style="padding: 32px 16px;">
                    <div class="empty-state-icon">💬</div>
                    <div class="empty-state-description">No conversations yet.<br>Start a new chat!</div>
                </div>`;
            return;
        }

        listEl.innerHTML = sessions.map(s => `
            <div class="session-item ${s.session_id === AppState.get('currentSessionId') ? 'active' : ''}"
                 data-session-id="${escapeHtml(s.session_id)}"
                 onclick="selectSession('${escapeHtml(s.session_id)}')">
                <span class="session-icon">💬</span>
                <div class="session-info">
                    <div class="session-title">${escapeHtml(s.title)}</div>
                    <div class="session-meta">${s.message_count} msgs · ${formatDate(s.created_at)}</div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load sessions:', error);
    }
}

function selectSession(sessionId) {
    AppState.set('currentSessionId', sessionId);

    // Update active state
    document.querySelectorAll('.session-item').forEach(el => {
        el.classList.toggle('active', el.dataset.sessionId === sessionId);
    });

    loadHistory(sessionId);
    closeSidebarMobile();
}

function startNewChat() {
    AppState.set('currentSessionId', null);

    document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));

    const messagesEl = document.getElementById('messages-container');
    messagesEl.innerHTML = '';
    showWelcome();

    document.getElementById('chat-input').focus();
    closeSidebarMobile();
}

// ── Chat History ──
async function loadHistory(sessionId) {
    const userId = AppState.get('userId');
    const messagesEl = document.getElementById('messages-container');

    hideWelcome();
    messagesEl.innerHTML = `
        <div style="display:flex;justify-content:center;padding:40px;">
            <div class="spinner"></div>
        </div>`;

    try {
        const messages = await api.getHistory(userId, sessionId, 50);
        messagesEl.innerHTML = '';

        if (!messages || messages.length === 0) {
            showWelcome();
            return;
        }

        messages.forEach(msg => appendMessage(msg.role, msg.content, false));
        scrollToBottom();
    } catch (error) {
        messagesEl.innerHTML = '';
        showWelcome();
        Toast.error('Failed to load chat history.');
    }
}

// ── Send Message ──
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message || isSending) return;

    isSending = true;
    const userId = AppState.get('userId');
    const sessionId = AppState.get('currentSessionId');

    // Clear input
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('send-btn').disabled = true;

    // Hide welcome, show user message
    hideWelcome();
    appendMessage('user', message);
    scrollToBottom();

    // Show typing indicator
    showTypingIndicator();

    try {
        const result = await api.sendMessage(userId, message, sessionId);

        // Set session ID if new
        if (!sessionId) {
            AppState.set('currentSessionId', result.session_id);
            loadSessions(); // Refresh sidebar
        }

        // Remove typing, show response
        hideTypingIndicator();
        appendMessage('assistant', result.response);
        scrollToBottom();

        // Show extraction badge briefly
        if (result.memories_extracted) {
            showExtractionBadge();
        }

    } catch (error) {
        hideTypingIndicator();
        appendMessage('assistant', 'Sorry, I encountered an error. Please try again.');
        Toast.error(error.message);
    } finally {
        isSending = false;
        input.focus();
    }
}

// ── Message Rendering ──
function appendMessage(role, content, animate = true) {
    const messagesEl = document.getElementById('messages-container');
    const username = AppState.get('username') || 'U';
    const initial = username.charAt(0).toUpperCase();
    const time = formatTime(new Date());

    const msgEl = document.createElement('div');
    msgEl.className = `message message-${role}`;
    if (animate) msgEl.style.animation = 'fade-in 0.3s ease-out';

    if (role === 'user') {
        msgEl.innerHTML = `
            <div class="message-bubble">
                <div class="message-text">${escapeHtml(content)}</div>
                <div class="message-time">${time}</div>
            </div>
            <div class="message-avatar">${initial}</div>`;
    } else {
        msgEl.innerHTML = `
            <div class="message-avatar">🧠</div>
            <div class="message-bubble">
                <div class="message-text">${formatAssistantMessage(content)}</div>
                <div class="message-time">${time}</div>
            </div>`;
    }

    messagesEl.appendChild(msgEl);
}

function formatAssistantMessage(text) {
    // Simple markdown-like formatting
    let html = escapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Code
    html = html.replace(/`(.*?)`/g, '<code style="background:rgba(99,102,241,0.15);padding:2px 6px;border-radius:4px;font-family:var(--font-mono);font-size:0.85em;">$1</code>');
    // Line breaks
    html = html.replace(/\n/g, '<br>');
    return html;
}

// ── Typing Indicator ──
function showTypingIndicator() {
    const messagesEl = document.getElementById('messages-container');
    const typingEl = document.createElement('div');
    typingEl.className = 'message message-typing message-assistant';
    typingEl.id = 'typing-indicator';
    typingEl.innerHTML = `
        <div class="message-avatar">🧠</div>
        <div class="message-bubble">
            <div class="typing-indicator">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
        </div>`;
    messagesEl.appendChild(typingEl);
    scrollToBottom();
}

function hideTypingIndicator() {
    document.getElementById('typing-indicator')?.remove();
}

// ── Extraction Badge ──
function showExtractionBadge() {
    const badge = document.getElementById('extraction-badge');
    if (badge) {
        badge.classList.add('visible');
        setTimeout(() => badge.classList.remove('visible'), 3000);
    }
}

// ── Welcome Screen ──
function showWelcome() {
    const welcome = document.getElementById('welcome-container');
    const messages = document.getElementById('messages-container');
    if (welcome) welcome.style.display = 'flex';
    if (messages) messages.style.display = 'none';
}

function hideWelcome() {
    const welcome = document.getElementById('welcome-container');
    const messages = document.getElementById('messages-container');
    if (welcome) welcome.style.display = 'none';
    if (messages) messages.style.display = 'flex';
}

// ── Sidebar Toggle (mobile) ──
function toggleSidebar() {
    const sidebar = document.getElementById('chat-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('visible');
}

function closeSidebarMobile() {
    if (window.innerWidth <= 768) {
        const sidebar = document.getElementById('chat-sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        sidebar.classList.remove('open');
        overlay.classList.remove('visible');
    }
}

// ── Scroll ──
function scrollToBottom() {
    const el = document.getElementById('messages-container');
    if (el) {
        requestAnimationFrame(() => {
            el.scrollTop = el.scrollHeight;
        });
    }
}
