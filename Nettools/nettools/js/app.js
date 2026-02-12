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
            settings: { icon: 'ri-settings-3-line', text: 'Ajustes' },
        };
        const titleInfo = titles[page] || titles.speed;
        document.getElementById('topbarTitle').innerHTML = `
            <i class="${titleInfo.icon}"></i>
            <h1>${titleInfo.text}</h1>
        `;

        // Show/hide auto-status indicator (only relevant on speed & network)
        const autoStatus = document.getElementById('autoStatusIndicator');
        const autoSeparator = document.querySelector('.topbar-separator');
        if (autoStatus) autoStatus.style.display = (page === 'speed' || page === 'network') ? '' : 'none';
        if (autoSeparator) autoSeparator.style.display = (page === 'speed' || page === 'network') ? '' : 'none';

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
        return d.toLocaleDateString('es-ES', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    },

    formatDateShort(dateStr) {
        const d = new Date(dateStr);
        return d.toLocaleDateString('es-ES', {
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
        return names[type] || 'Dispositivo';
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
});
