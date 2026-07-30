/**
 * MemoraeAI — API Client
 * Fetch wrapper for all backend endpoints.
 */

const API_BASE = 'http://localhost:8000';

class MemoraeAPI {
    constructor(baseUrl = API_BASE) {
        this.baseUrl = baseUrl;
    }

    async _request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        };

        try {
            const response = await fetch(url, config);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                throw new Error('Cannot connect to MemoraeAI server. Is it running on ' + this.baseUrl + '?');
            }
            throw error;
        }
    }

    // ── User ──
    async login(username) {
        return this._request('/api/user/login', {
            method: 'POST',
            body: JSON.stringify({ username }),
        });
    }

    // ── Chat ──
    async sendMessage(userId, message, sessionId = null) {
        const body = { user_id: userId, message };
        if (sessionId) body.session_id = sessionId;
        return this._request('/api/chat/send', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    async getHistory(userId, sessionId, limit = 50) {
        return this._request('/api/chat/history', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId, session_id: sessionId, limit }),
        });
    }

    async getSessions(userId) {
        return this._request('/api/chat/sessions', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId }),
        });
    }

    // ── Memories ──
    async listMemories(userId) {
        return this._request('/api/memories/list', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId }),
        });
    }

    async forgetMemory(userId, searchText) {
        return this._request('/api/memories/forget', {
            method: 'POST',
            body: JSON.stringify({ user_id: userId, search_text: searchText }),
        });
    }

    // ── Health ──
    async healthCheck() {
        return this._request('/health');
    }
}

// Singleton instance
const api = new MemoraeAPI();
