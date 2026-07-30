/**
 * MemoraeAI — State Management
 * Simple client-side state stored in localStorage.
 */

const STATE_KEY = 'memorae_state';

const AppState = {
    _state: null,

    _defaults() {
        return {
            userId: null,
            username: null,
            currentSessionId: null,
            isLoggedIn: false,
        };
    },

    load() {
        try {
            const stored = localStorage.getItem(STATE_KEY);
            this._state = stored ? JSON.parse(stored) : this._defaults();
        } catch {
            this._state = this._defaults();
        }
        return this._state;
    },

    save() {
        try {
            localStorage.setItem(STATE_KEY, JSON.stringify(this._state));
        } catch (e) {
            console.warn('Failed to save state:', e);
        }
    },

    get(key) {
        if (!this._state) this.load();
        return this._state[key];
    },

    set(key, value) {
        if (!this._state) this.load();
        this._state[key] = value;
        this.save();
    },

    login(userId, username) {
        this._state = {
            ...this._defaults(),
            userId,
            username,
            isLoggedIn: true,
        };
        this.save();
    },

    logout() {
        this._state = this._defaults();
        this.save();
        window.location.href = 'index.html';
    },

    isLoggedIn() {
        if (!this._state) this.load();
        return this._state.isLoggedIn && this._state.userId;
    },

    requireAuth() {
        if (!this.isLoggedIn()) {
            window.location.href = 'index.html';
            return false;
        }
        return true;
    },
};

// ── Toast Notifications ──
const Toast = {
    _container: null,

    _getContainer() {
        if (!this._container) {
            this._container = document.createElement('div');
            this._container.className = 'toast-container';
            this._container.id = 'toast-container';
            document.body.appendChild(this._container);
        }
        return this._container;
    },

    show(message, type = 'info', duration = 3500) {
        const container = this._getContainer();
        const icons = { success: '✓', error: '✗', info: 'ℹ' };

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;

        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 5000); },
    info(msg) { this.show(msg, 'info'); },
};

// ── Utility: time formatting ──
function formatTime(date) {
    return new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now - d;
    const mins = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return d.toLocaleDateString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
