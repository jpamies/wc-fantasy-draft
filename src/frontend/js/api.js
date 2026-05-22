/* API client — wraps fetch with JWT auth */
const API = {
    BASE: '/api/v1',

    getToken() { return localStorage.getItem('wcf_token'); },
    setToken(t) { localStorage.setItem('wcf_token', t); },
    clearToken() { localStorage.removeItem('wcf_token'); },
    getTeamId() { return localStorage.getItem('wcf_team_id'); },
    setTeamId(id) { localStorage.setItem('wcf_team_id', id); },
    getLeagueId() { return localStorage.getItem('wcf_league_id'); },
    setLeagueId(id) { localStorage.setItem('wcf_league_id', id); },
    isCommissioner() { return localStorage.getItem('wcf_is_commissioner') === 'true'; },
    setCommissioner(v) { localStorage.setItem('wcf_is_commissioner', String(v)); },

    getCurrentTeam() {
        return {
            team_id: this.getTeamId(),
            league_id: this.getLeagueId(),
            is_commissioner: this.isCommissioner(),
        };
    },

    isLoggedIn() { return !!this.getToken(); },

    logout() {
        this.clearToken();
        localStorage.removeItem('wcf_team_id');
        localStorage.removeItem('wcf_league_id');
        localStorage.removeItem('wcf_is_commissioner');
        localStorage.removeItem('wcf_team_name');
    },

    async request(path, opts = {}) {
        const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
        const token = this.getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(this.BASE + path, { ...opts, headers });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || JSON.stringify(err));
        }
        return res.json();
    },

    get(path) { return this.request(path); },
    post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); },
    patch(path, body) { return this.request(path, { method: 'PATCH', body: JSON.stringify(body) }); },
    delete(path) { return this.request(path, { method: 'DELETE' }); },
};

function formatMoney(val) {
    if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
    if (val >= 1_000) return `${(val / 1_000).toFixed(0)}K`;
    return String(val);
}

/**
 * Format a backend datetime string in Europe/Madrid time.
 * Accepts both UTC ISO (with Z) and naive strings (treated as Madrid by browser).
 */
function formatMadrid(s) {
    if (!s) return '—';
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleString('es-ES', {
        timeZone: 'Europe/Madrid',
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

function posBadge(pos) {
    return `<span class="badge badge-${pos.toLowerCase()}">${pos}</span>`;
}

function showToast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4000);
}

function showModal(html) {
    document.getElementById('modal-content').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
}

document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target.id === 'modal-overlay') closeModal();
});
