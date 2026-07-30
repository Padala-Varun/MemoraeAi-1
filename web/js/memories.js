/**
 * MemoraeAI — Memories Dashboard Logic
 * Memory browser, stats, filtering, and forget functionality.
 */

document.addEventListener('DOMContentLoaded', () => {
    AppState.load();
    if (!AppState.requireAuth()) return;

    initMemoriesUI();
    loadAllMemories();
});

let allMemories = { episodic: [], semantic: [], profile: null, goals: [] };
let currentFilter = 'all';

// ── Initialize UI ──
function initMemoriesUI() {
    // Set user info in nav
    const username = AppState.get('username') || 'User';
    const avatarEl = document.getElementById('nav-user-avatar');
    const nameEl = document.getElementById('nav-user-name');
    if (avatarEl) avatarEl.textContent = username.charAt(0).toUpperCase();
    if (nameEl) nameEl.textContent = username;

    // Filter tabs
    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentFilter = tab.dataset.filter;
            renderMemories();
        });
    });

    // Forget form
    document.getElementById('forget-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = document.getElementById('forget-input');
        const text = input.value.trim();
        if (!text) return;

        const btn = document.getElementById('forget-btn');
        btn.disabled = true;
        btn.textContent = 'Forgetting...';

        try {
            const result = await api.forgetMemory(AppState.get('userId'), text);
            Toast.success(result.message || `Removed ${result.total_deleted} memory(ies).`);
            input.value = '';
            await loadAllMemories(); // Refresh
        } catch (error) {
            Toast.error('Forget failed: ' + error.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Forget';
        }
    });

    // Logout
    document.getElementById('logout-btn')?.addEventListener('click', () => AppState.logout());
}

// ── Load All Memories ──
async function loadAllMemories() {
    const userId = AppState.get('userId');
    const grid = document.getElementById('memories-grid');

    grid.innerHTML = `
        <div style="grid-column:1/-1;display:flex;justify-content:center;padding:60px;">
            <div class="spinner"></div>
        </div>`;

    try {
        const data = await api.listMemories(userId);
        allMemories = {
            episodic: data.episodic || [],
            semantic: data.semantic || [],
            profile: data.profile || null,
            goals: data.goals || [],
        };

        updateStats();
        renderMemories();
    } catch (error) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1;">
                <div class="empty-state-icon">⚠️</div>
                <div class="empty-state-title">Connection Error</div>
                <div class="empty-state-description">${escapeHtml(error.message)}</div>
            </div>`;
    }
}

// ── Stats ──
function updateStats() {
    document.getElementById('stat-episodic').textContent = allMemories.episodic.length;
    document.getElementById('stat-semantic').textContent = allMemories.semantic.length;
    document.getElementById('stat-profile').textContent = allMemories.profile ? '✓' : '—';
    document.getElementById('stat-goals').textContent = allMemories.goals.length;
}

// ── Render Memories ──
function renderMemories() {
    const grid = document.getElementById('memories-grid');
    let cards = [];

    // Profile section (always shows if filter=all or filter=profile)
    if ((currentFilter === 'all' || currentFilter === 'profile') && allMemories.profile) {
        cards.push(renderProfileCard(allMemories.profile));
    }

    // Goals
    if (currentFilter === 'all' || currentFilter === 'goal') {
        allMemories.goals.forEach(g => cards.push(renderGoalCard(g)));
    }

    // Semantic facts
    if (currentFilter === 'all' || currentFilter === 'semantic') {
        allMemories.semantic.forEach(f => cards.push(renderSemanticCard(f)));
    }

    // Episodic memories
    if (currentFilter === 'all' || currentFilter === 'episodic') {
        allMemories.episodic.forEach(m => cards.push(renderEpisodicCard(m)));
    }

    if (cards.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column:1/-1;">
                <div class="empty-state-icon">🧠</div>
                <div class="empty-state-title">No Memories Yet</div>
                <div class="empty-state-description">
                    Start chatting and I'll automatically remember important things about you.
                </div>
            </div>`;
        return;
    }

    grid.innerHTML = cards.join('');
}

// ── Card Renderers ──

function renderEpisodicCard(memory) {
    const importance = memory.importance_score || 5;
    return `
        <div class="memory-card glass-card">
            <div class="memory-card-header">
                <span class="badge badge-episodic">⚡ Episodic</span>
                <div class="memory-importance">
                    <div class="importance-bar">
                        ${renderImportanceBar(importance)}
                    </div>
                    <span>${importance}/10</span>
                </div>
            </div>
            <div class="memory-content">${escapeHtml(memory.content || '')}</div>
            ${memory.source_quote ? `<div class="memory-quote">"${escapeHtml(memory.source_quote)}"</div>` : ''}
            <div class="memory-card-footer">
                <span class="memory-date">${memory.created_at ? formatDate(memory.created_at) : ''}</span>
                <span class="badge badge-active">Active</span>
            </div>
        </div>`;
}

function renderSemanticCard(fact) {
    const importance = fact.importance_score || 5;
    const subject = fact.subject || '?';
    const predicate = fact.predicate || '?';
    const obj = fact.object || '?';

    return `
        <div class="memory-card glass-card">
            <div class="memory-card-header">
                <span class="badge badge-semantic">🔗 Semantic</span>
                <div class="memory-importance">
                    <div class="importance-bar">
                        ${renderImportanceBar(importance)}
                    </div>
                    <span>${importance}/10</span>
                </div>
            </div>
            <div class="triple-display">
                <span class="triple-subject">${escapeHtml(subject)}</span>
                <span class="triple-arrow">→</span>
                <span class="triple-predicate">${escapeHtml(predicate)}</span>
                <span class="triple-arrow">→</span>
                <span class="triple-object">${escapeHtml(obj)}</span>
            </div>
            ${fact.content ? `<div class="memory-content">${escapeHtml(fact.content)}</div>` : ''}
            <div class="memory-card-footer">
                <span>Confidence: ${((fact.confidence || 0) * 100).toFixed(0)}%</span>
                <span class="badge badge-active">Active</span>
            </div>
        </div>`;
}

function renderProfileCard(profile) {
    const fields = [];

    if (profile.name) {
        fields.push({ label: 'Name', value: profile.name });
    }

    if (profile.preferences && typeof profile.preferences === 'object') {
        Object.entries(profile.preferences).forEach(([k, v]) => {
            fields.push({ label: k, value: v });
        });
    }

    if (profile.traits && Array.isArray(profile.traits) && profile.traits.length > 0) {
        fields.push({ label: 'Traits', value: profile.traits.join(', ') });
    }

    if (fields.length === 0) {
        fields.push({ label: 'Status', value: 'Profile exists but no details extracted yet.' });
    }

    return `
        <div class="memory-card glass-card profile-card" style="grid-column:1/-1;">
            <div class="memory-card-header">
                <span class="badge badge-profile">👤 Profile</span>
                <span style="font-size:0.72rem;color:var(--text-muted);">
                    Updated ${profile.updated_at ? formatDate(profile.updated_at) : 'recently'}
                </span>
            </div>
            ${fields.map(f => `
                <div class="profile-field">
                    <span class="profile-field-label">${escapeHtml(f.label)}</span>
                    <span class="profile-field-value">${escapeHtml(String(f.value))}</span>
                </div>
            `).join('')}
        </div>`;
}

function renderGoalCard(goal) {
    const status = goal.status || 'active';
    const statusClass = status === 'active' ? 'goal-active' : 'goal-completed';
    const statusIcon = status === 'active' ? '🎯' : '✅';

    return `
        <div class="memory-card glass-card goal-card ${statusClass}">
            <div class="goal-status-icon">${statusIcon}</div>
            <div class="goal-info">
                <div class="goal-description">${escapeHtml(goal.description || '')}</div>
                <div class="goal-meta">
                    <span class="badge badge-goal">${escapeHtml(status)}</span>
                    ${goal.priority ? `<span style="margin-left:8px;">Priority: ${goal.priority}/10</span>` : ''}
                </div>
            </div>
        </div>`;
}

// ── Helpers ──
function renderImportanceBar(score) {
    let html = '';
    for (let i = 1; i <= 10; i++) {
        html += `<div class="importance-segment ${i <= score ? 'filled' : ''}"></div>`;
    }
    return html;
}
