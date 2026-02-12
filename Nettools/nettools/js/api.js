/* =========================================
   NetTools - API Client
   ========================================= */

const API_BASE = '/api';

const API = {
    // --- Helper ---
    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        };

        try {
            const response = await fetch(url, config);
            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Error desconocido' }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            return await response.json();
        } catch (err) {
            if (err.name === 'TypeError' && err.message.includes('fetch')) {
                throw new Error('No se pudo conectar con el servidor');
            }
            throw err;
        }
    },

    // --- Speed Test ---
    speedtest: {
        async run(serverId = null) {
            const body = serverId ? { server_id: serverId } : {};
            return API.request('/speedtest/run', {
                method: 'POST',
                body: JSON.stringify(body),
            });
        },

        async getServers() {
            return API.request('/speedtest/servers');
        },

        async getResults(params = {}) {
            const query = new URLSearchParams(params).toString();
            return API.request(`/speedtest/results${query ? '?' + query : ''}`);
        },

        async getLatest() {
            return API.request('/speedtest/latest');
        },

        async getStats() {
            return API.request('/speedtest/stats');
        },

        async getStatus() {
            return API.request('/speedtest/status');
        },

        async delete(id) {
            return API.request(`/speedtest/results/${id}`, { method: 'DELETE' });
        },

        async clearAll() {
            return API.request('/speedtest/results', { method: 'DELETE' });
        }
    },

    // --- Devices ---
    devices: {
        async getAll(params = {}) {
            const query = new URLSearchParams(params).toString();
            return API.request(`/devices${query ? '?' + query : ''}`);
        },

        async get(id) {
            return API.request(`/devices/${id}`);
        },

        async create(data) {
            return API.request('/devices', {
                method: 'POST',
                body: JSON.stringify(data),
            });
        },

        async update(id, data) {
            return API.request(`/devices/${id}`, {
                method: 'PUT',
                body: JSON.stringify(data),
            });
        },

        async delete(id) {
            return API.request(`/devices/${id}`, { method: 'DELETE' });
        },

        async scan() {
            return API.request('/devices/scan', { method: 'POST' });
        },

        async getScanStatus() {
            return API.request('/devices/scan/status');
        },

        async clearAll() {
            return API.request('/devices', { method: 'DELETE' });
        },

        async getHistory(params = {}) {
            const query = new URLSearchParams(params).toString();
            return API.request(`/devices/history${query ? '?' + query : ''}`);
        }
    },

    // --- Ping ---
    ping: {
        async single(ip) {
            return API.request('/ping', {
                method: 'POST',
                body: JSON.stringify({ ip }),
            });
        },

        async multiple(ips) {
            return API.request('/ping/batch', {
                method: 'POST',
                body: JSON.stringify({ ips }),
            });
        }
    },

    // --- Traceroute ---
    traceroute: {
        async run(target, maxHops = 30) {
            return API.request('/traceroute', {
                method: 'POST',
                body: JSON.stringify({ target, max_hops: maxHops }),
            });
        }
    },

    // --- NSLookup ---
    nslookup: {
        async run(domain, recordType = 'A', dnsServer = null) {
            const body = { domain, record_type: recordType };
            if (dnsServer) body.dns_server = dnsServer;
            return API.request('/nslookup', {
                method: 'POST',
                body: JSON.stringify(body),
            });
        },

        async reverse(ip) {
            return API.request('/nslookup/reverse', {
                method: 'POST',
                body: JSON.stringify({ ip }),
            });
        }
    },

    // --- Settings ---
    settings: {
        async getAll() {
            return API.request('/settings');
        },

        async update(data) {
            return API.request('/settings', {
                method: 'PUT',
                body: JSON.stringify(data),
            });
        },

        async testTelegram() {
            return API.request('/settings/telegram/test', { method: 'POST' });
        }
    },

    // --- Export ---
    async exportData() {
        return API.request('/export');
    }
};
