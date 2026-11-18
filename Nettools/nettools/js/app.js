/* =========================================
   NetTools - Main Application
   ========================================= */

// --- Theme System ---
const Theme = {
    init() {
        const saved = localStorage.getItem('nettools-theme') || 'system';
        this.set(saved);
        this.updateButtons(saved);

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
            if (localStorage.getItem('nettools-theme') === 'system') {
                this.applySystem();
            }
        });

        // Theme button clicks
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const theme = btn.dataset.theme;
                this.set(theme);
                this.updateButtons(theme);
                localStorage.setItem('nettools-theme', theme);
            });
        });
    },

    set(theme) {
        if (theme === 'system') {
            this.applySystem();
        } else {
            document.documentElement.setAttribute('data-theme', theme);
        }
        // Redraw charts with new theme colors
        setTimeout(() => {
            if (typeof SpeedTestPage !== 'undefined' && SpeedTestPage.chartsInitialized) {
                SpeedTestPage.updateChartTheme();
            }
        }, 100);
    },

    applySystem() {
        const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    },

    updateButtons(active) {
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === active);
        });
    },

    getCurrent() {
        return document.documentElement.getAttribute('data-theme');
    },

    getColors() {
        const style = getComputedStyle(document.documentElement);
        return {
            download: style.getPropertyValue('--download-color').trim(),
            upload: style.getPropertyValue('--upload-color').trim(),
            ping: style.getPropertyValue('--ping-color').trim(),
            jitter: style.getPropertyValue('--jitter-color').trim(),
            text: style.getPropertyValue('--text-primary').trim(),
            textSecondary: style.getPropertyValue('--text-secondary').trim(),
            textTertiary: style.getPropertyValue('--text-tertiary').trim(),
            border: style.getPropertyValue('--border').trim(),
            grid: style.getPropertyValue('--chart-grid').trim(),
            chartText: style.getPropertyValue('--chart-text').trim(),
            bg: style.getPropertyValue('--bg-secondary').trim(),
            accent: style.getPropertyValue('--accent').trim(),
            gaugeTrack: style.getPropertyValue('--gauge-track').trim(),
            gaugeDownload: style.getPropertyValue('--gauge-download').trim(),
            gaugeUpload: style.getPropertyValue('--gauge-upload').trim(),
        };
    }
};

// --- Navigation / Router ---
const Router = {
    currentPage: null,

    init() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.dataset.page;
                this.navigate(page);
            });
        });

        // Load initial page from hash
        const hash = window.location.hash.replace('#', '') || 'speed';
        this.navigate(hash);
    },

    navigate(page) {
        if (this.currentPage === page) return;

        // Stop auto-refresh on previous page
        if (this.currentPage === 'speed' && typeof SpeedTestPage !== 'undefined') SpeedTestPage.stopAutoRefresh();
        if (this.currentPage === 'network' && typeof NetworkPage !== 'undefined') NetworkPage.stopAutoRefresh();

        // Update nav links
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.toggle('active', link.dataset.page === page);
        });

        // Update pages
        document.querySelectorAll('.page').forEach(p => {
            p.classList.remove('active');
        });
        const pageEl = document.getElementById(`page-${page}`);
        if (pageEl) pageEl.classList.add('active');

        // Update topbar
        const titles = {
            speed: { icon: 'ri-speed-up-line', text: 'Net Speed' },
            netcheck: { icon: 'ri-shield-check-line', text: 'Net Check' },
            network: { icon: 'ri-radar-line', text: 'Net Alert' },
            inventory: { icon: 'ri-archive-drawer-line', text: 'Inventario' },
            settings: { icon: 'ri-settings-3-line', text: 'Ajustes' },
        };
        const titleInfo = titles[page] || titles.speed;
        document.getElementById('topbarTitle').innerHTML = `
            <i class="${titleInfo.icon}"></i>
            <h1>${titleInfo.text}</h1>
        `;

        // Show/hide auto-status indicator (only relevant on speed & network)
        const autoStatus = document.getElementById('autoStatusIndicator');
        if (autoStatus) autoStatus.style.display = (page === 'speed' || page === 'network') ? '' : 'none';

        // Close mobile sidebar
        document.getElementById('sidebar').classList.remove('mobile-open');
        document.getElementById('sidebarOverlay').classList.remove('visible');

        this.currentPage = page;
        window.location.hash = page;

        // Initialize page-specific content
        if (page === 'speed') SpeedTestPage.init();
        if (page === 'netcheck') NetCheckPage.init();
        if (page === 'network') NetworkPage.init();
        if (page === 'settings') SettingsPage.init();
        if (page === 'inventory') InventoryPage.init();
    }
};

// --- Sidebar ---
const Sidebar = {
    init() {
        const sidebar = document.getElementById('sidebar');
        const toggle = document.getElementById('sidebarToggle');
        const mobileBtn = document.getElementById('mobileMenuBtn');
        const overlay = document.getElementById('sidebarOverlay');

        const collapsed = localStorage.getItem('nettools-sidebar-collapsed') === 'true';
        if (collapsed) sidebar.classList.add('collapsed');

        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('nettools-sidebar-collapsed', sidebar.classList.contains('collapsed'));
        });

        // When the sidebar width animation ends, let the charts (ApexCharts)
        // resize to the new space: they keep a fixed pixel width otherwise.
        sidebar.addEventListener('transitionend', (e) => {
            if (e.target === sidebar && e.propertyName === 'width') {
                window.dispatchEvent(new Event('resize'));
            }
        });

        mobileBtn.addEventListener('click', () => {
            sidebar.classList.add('mobile-open');
            overlay.classList.add('visible');
        });

        overlay.addEventListener('click', () => {
            sidebar.classList.remove('mobile-open');
            overlay.classList.remove('visible');
        });
    }
};

// --- Notifications panel (bell in the top bar) ---
// Same events that are sent by Telegram (new devices, scheduled speed tests,
// port changes). Stored by the server as data and rendered here in the UI
// language.
const Notifications = {
    items: [],
    unread: 0,
    _timer: null,

    init() {
        const btn = document.getElementById('notifBtn');
        const panel = document.getElementById('notifPanel');
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = panel.classList.toggle('hidden') === false;
            btn.classList.toggle('open', open);
            if (open) this.load();
        });
        document.addEventListener('click', (e) => {
            if (!panel.classList.contains('hidden') && !e.target.closest('.notif-wrap')) this.close();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.close();
        });
        document.getElementById('notifReadAll').addEventListener('click', () => this.markAllRead());
        document.getElementById('notifList').addEventListener('click', (e) => {
            const readBtn = e.target.closest('.notif-read-btn');
            const item = e.target.closest('.notif-item');
            if (!item) return;
            const id = Number(item.dataset.id);
            if (readBtn) {
                e.stopPropagation();
                this.markRead(id);
                return;
            }
            // Open the related section (and mark it as read)
            const n = this.items.find(x => x.id === id);
            if (n && !n.read) this.markRead(id);
            const page = { new_devices: 'network', port_changes: 'network', speed_test: 'speed', speed_test_failed: 'speed' }[n && n.type];
            if (page) {
                this.close();
                Router.navigate(page);
            }
        });
        this.load();
        this._timer = setInterval(() => this.load(), 30000);
    },

    close() {
        document.getElementById('notifPanel').classList.add('hidden');
        document.getElementById('notifBtn').classList.remove('open');
    },

    async load() {
        try {
            const r = await API.notifications.list();
            this.items = r.items || [];
            this.unread = r.unread || 0;
        } catch (e) {
            return;
        }
        this.render();
    },

    async markRead(id) {
        const n = this.items.find(x => x.id === id);
        if (n && !n.read) {
            n.read = true;
            this.unread = Math.max(0, this.unread - 1);
            this.render();
        }
        try { await API.notifications.read(id); } catch (e) { this.load(); }
    },

    async markAllRead() {
        this.items.forEach(n => { n.read = true; });
        this.unread = 0;
        this.render();
        try { await API.notifications.readAll(); } catch (e) { this.load(); }
    },

    esc(v) {
        const d = document.createElement('div');
        d.textContent = v == null ? '' : String(v);
        return d.innerHTML;
    },

    timeAgo(ts) {
        if (!ts) return '';
        const d = new Date(ts.replace(' ', 'T'));
        const mins = Math.round((Date.now() - d.getTime()) / 60000);
        if (isNaN(mins)) return ts;
        if (mins < 1) return I18N.t('ahora mismo');
        if (mins < 60) return I18N.t('hace {n} min', { n: mins });
        if (mins < 24 * 60) return I18N.t('hace {n} h', { n: Math.round(mins / 60) });
        return d.toLocaleString(I18N.locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    },

    describe(n) {
        const d = n.data || {};
        const esc = (v) => `<span translate="no">${this.esc(v)}</span>`;
        const mbps = (v) => (v == null ? '-' : Number(v).toFixed(0));
        switch (n.type) {
            case 'new_devices': {
                const list = d.devices || [];
                const count = d.count || list.length;
                const names = list.slice(0, 3).map(x =>
                    esc(`${x.hostname || x.ip_address || '?'}${x.ip_address && x.hostname ? ' (' + x.ip_address + ')' : ''}${x.brand ? ' · ' + x.brand : ''}`));
                return {
                    icon: 'ri-radar-line',
                    title: count === 1 ? I18N.t('Nuevo dispositivo detectado') : I18N.t('{n} nuevos dispositivos detectados', { n: count }),
                    text: names.join('<br>') + (count > 3 ? '<br>' + I18N.t('y {n} mas', { n: count - 3 }) : ''),
                };
            }
            case 'speed_test':
                return {
                    icon: d.slow ? 'ri-error-warning-line' : 'ri-speed-up-line',
                    title: d.slow ? I18N.t('Velocidad por debajo de lo esperado') : I18N.t('Test de velocidad programado'),
                    text: `↓ ${mbps(d.download)} Mbps · ↑ ${mbps(d.upload)} Mbps · ${d.ping != null ? Number(d.ping).toFixed(1) : '-'} ms` +
                          (d.slow && d.threshold ? '<br>' + I18N.t('Umbral: {n} Mbps', { n: mbps(d.threshold) }) : ''),
                };
            case 'speed_test_failed':
                return {
                    icon: 'ri-close-circle-line',
                    title: I18N.t('Test de velocidad fallido'),
                    text: this.esc(I18N.t(d.error || '')),
                };
            case 'port_changes': {
                const fmt = (ports, sign) => ports.map(p => `${sign}${p.port}${p.service ? ' ' + this.esc(p.service) : ''}`).join(', ');
                const lines = (d.changes || []).slice(0, 4).map(c =>
                    `${esc(c.name || c.ip)}: ${[fmt(c.new_ports || [], '+'), fmt(c.closed_ports || [], '−')].filter(Boolean).join(', ')}`);
                return {
                    icon: 'ri-door-open-line',
                    title: I18N.t('Cambios en puertos abiertos'),
                    text: lines.join('<br>') + ((d.changes || []).length > 4 ? '<br>' + I18N.t('y {n} mas', { n: d.changes.length - 4 }) : ''),
                };
            }
            default:
                return { icon: 'ri-notification-3-line', title: n.type, text: '' };
        }
    },

    render() {
        const badge = document.getElementById('notifBadge');
        badge.textContent = this.unread > 99 ? '99+' : this.unread;
        badge.classList.toggle('hidden', !this.unread);
        document.getElementById('notifReadAll').disabled = !this.unread;
        const list = document.getElementById('notifList');
        if (!this.items.length) {
            list.innerHTML = `<div class="notif-empty"><i class="ri-notification-off-line"></i>${I18N.t('No hay notificaciones')}</div>`;
            return;
        }
        list.innerHTML = this.items.map(n => {
            const v = this.describe(n);
            return `
                <div class="notif-item ${n.read ? '' : 'unread'}" data-id="${n.id}">
                    <div class="notif-icon ${n.level || 'info'}"><i class="${v.icon}"></i></div>
                    <div class="notif-body">
                        <div class="notif-item-title">${v.title}</div>
                        ${v.text ? `<div class="notif-item-text">${v.text}</div>` : ''}
                        <div class="notif-time">${this.timeAgo(n.created_at)}</div>
                    </div>
                    ${n.read ? '<span></span>' : `<button class="notif-read-btn" title="${I18N.t('Marcar como leida')}"><i class="ri-check-line"></i></button>`}
                </div>`;
        }).join('');
    },
};

// --- Toast Notifications ---
const Toast = {
    show(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toastContainer');
        const icons = {
            success: 'ri-check-line',
            error: 'ri-error-warning-line',
            warning: 'ri-alert-line',
            info: 'ri-information-line',
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <i class="${icons[type] || icons.info}"></i>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="ri-close-line"></i>
            </button>
        `;

        container.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => {
                toast.classList.add('removing');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        return toast;
    },

    success(msg) { return this.show(msg, 'success'); },
    error(msg) { return this.show(msg, 'error', 6000); },
    warning(msg) { return this.show(msg, 'warning'); },
    info(msg) { return this.show(msg, 'info'); },
};

// --- Confirm Dialog ---
let confirmCallback = null;

function showConfirm(title, message, callback) {
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;
    document.getElementById('confirmModal').classList.add('visible');
    confirmCallback = callback;

    document.getElementById('confirmAction').onclick = () => {
        const cb = confirmCallback;
        closeConfirm();
        if (cb) cb();
    };
}

function closeConfirm() {
    document.getElementById('confirmModal').classList.remove('visible');
    confirmCallback = null;
}

// --- Utility Functions ---
const Utils = {
    formatDate(dateStr) {
        const d = new Date(dateStr);
        return d.toLocaleDateString(I18N.locale, {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    },

    formatDateShort(dateStr) {
        const d = new Date(dateStr);
        return d.toLocaleDateString(I18N.locale, {
            day: '2-digit',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit',
        });
    },

    formatSpeed(mbps) {
        if (mbps == null || isNaN(mbps)) return '--';
        return parseFloat(mbps).toFixed(1);
    },

    formatPing(ms) {
        if (ms == null || isNaN(ms)) return '--';
        return parseFloat(ms).toFixed(1);
    },

    getDeviceIcon(type) {
        const icons = {
            router: 'ri-router-line',
            switch: 'ri-git-branch-line',
            ap: 'ri-wireless-charging-line',
            server: 'ri-server-line',
            desktop: 'ri-computer-line',
            laptop: 'ri-macbook-line',
            pc: 'ri-computer-line',
            phone: 'ri-smartphone-line',
            tablet: 'ri-tablet-line',
            printer: 'ri-printer-line',
            camera: 'ri-camera-line',
            iot: 'ri-home-smile-line',
            nas: 'ri-hard-drive-2-line',
            tv: 'ri-tv-line',
            gaming: 'ri-gamepad-line',
            other: 'ri-device-line',
        };
        return icons[type] || icons.other;
    },

    getDeviceTypeName(type) {
        const names = {
            router: 'Router',
            switch: 'Switch',
            ap: 'Punto de Acceso',
            server: 'Servidor',
            desktop: 'PC',
            laptop: 'Portatil',
            pc: 'PC',
            phone: 'Telefono',
            tablet: 'Tablet',
            printer: 'Impresora',
            camera: 'Camara',
            iot: 'IoT',
            nas: 'NAS',
            tv: 'Smart TV',
            gaming: 'Gaming',
            other: 'Dispositivo',
        };
        return I18N.t(names[type] || 'Dispositivo');
    },

    /** Numeric sort key for an IPv4 address, or null if there is none. */
    ipSortKey(ip) {
        const parts = (ip || '').trim().split('.');
        if (parts.length !== 4 || parts.some(p => !/^\d{1,3}$/.test(p))) return null;
        return parts.reduce((acc, p) => acc * 256 + Number(p), 0);
    },

    /** Bumped when a custom logo is uploaded/removed, to refresh cached images. */
    logoVersion: Date.now(),

    /**
     * Manufacturer logo tile (falls back to the device type icon when the
     * brand is empty or has no logo).
     */
    logoTile(brand, icon, extraClass = '') {
        const fallback = `<i class="${icon}"></i>`;
        if (!brand) return `<span class="inv-logo fallback ${extraClass}">${fallback}</span>`;
        const safe = String(brand).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        return `<span class="inv-logo ${extraClass}" title="${safe}">` +
               `<img src="${API.logos.url(brand, this.logoVersion)}" alt="" loading="lazy" ` +
               `onerror="this.parentNode.classList.add('fallback')">${fallback}</span>`;
    },

    debounce(fn, delay = 300) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    }
};

// --- Connection Status ---
const ConnectionStatus = {
    async check() {
        try {
            const response = await fetch(`${API_BASE}/health`, { method: 'GET' });
            this.setOnline(response.ok);
        } catch {
            this.setOnline(false);
        }
    },

    setOnline(online) {
        const dot = document.querySelector('#connectionStatus .status-dot');
        const text = document.querySelector('#connectionStatus .status-text');
        if (online) {
            dot.className = 'status-dot online';
            text.textContent = 'Conectado';
        } else {
            dot.className = 'status-dot';
            text.textContent = 'Desconectado';
        }
    },

    startPolling() {
        this.check();
        setInterval(() => this.check(), 30000);
    }
};

// --- Custom Colors (load early) ---
function loadSavedColors() {
    const accent = localStorage.getItem('nettools-color-accent');
    const bg = localStorage.getItem('nettools-color-bg');
    const dl = localStorage.getItem('nettools-color-download');
    const ul = localStorage.getItem('nettools-color-upload');

    if (accent) {
        document.documentElement.style.setProperty('--accent', accent);
        const num = parseInt(accent.replace('#', ''), 16);
        const r = Math.max(0, ((num >> 16) & 0xFF) - 38);
        const g = Math.max(0, ((num >> 8) & 0xFF) - 38);
        const b = Math.max(0, (num & 0xFF) - 38);
        document.documentElement.style.setProperty('--accent-hover', `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`);
        document.documentElement.style.setProperty('--border-focus', accent);
    }
    if (bg) document.documentElement.style.setProperty('--bg-primary', bg);
    if (dl) {
        document.documentElement.style.setProperty('--download-color', dl);
        document.documentElement.style.setProperty('--gauge-download', dl);
    }
    if (ul) {
        document.documentElement.style.setProperty('--upload-color', ul);
        document.documentElement.style.setProperty('--gauge-upload', ul);
    }
}

// --- App Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    Theme.init();
    loadSavedColors();
    Sidebar.init();
    Router.init();
    ConnectionStatus.startPolling();
    Notifications.init();
    // Language chosen in the settings (server) and the UI language for the
    // texts generated by the server (Telegram, device hints)
    API.settings.getAll().then(s => I18N.syncWithServer(s)).catch(() => {});
});
