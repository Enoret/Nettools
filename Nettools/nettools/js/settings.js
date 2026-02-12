/* =========================================
   NetTools - Settings Page
   ========================================= */

const SettingsPage = {
    initialized: false,

    // Default colors
    defaults: {
        accent: '#ffa801',
        bg: '#f1f5f9',
        bgDark: '#0b1120',
        download: '#3b82f6',
        upload: '#8b5cf6',
    },

    init() {
        if (!this.initialized) {
            this.bindEvents();
            this.initialized = true;
        }
        this.loadSettings();
        this.loadCustomColors();
    },

    bindEvents() {
        // Save settings
        document.getElementById('saveSettingsBtn').addEventListener('click', () => this.saveSettings());

        // Export data
        document.getElementById('exportDataBtn').addEventListener('click', () => this.exportData());

        // Clear tests
        document.getElementById('clearTestsBtn').addEventListener('click', () => {
            showConfirm(
                'Limpiar Historial',
                '¿Seguro que quieres eliminar todos los resultados de tests de velocidad? Esta accion no se puede deshacer.',
                () => this.clearTests()
            );
        });

        // Clear devices
        document.getElementById('clearDevicesBtn').addEventListener('click', () => {
            showConfirm(
                'Reiniciar Dispositivos',
                '¿Seguro que quieres eliminar todos los dispositivos descubiertos? Esta accion no se puede deshacer.',
                () => this.clearDevices()
            );
        });

        // Telegram test
        document.getElementById('testTelegramBtn').addEventListener('click', () => this.testTelegram());

        // Color pickers
        this.bindColorPicker('accentColor', '--accent', 'accent');
        this.bindColorPicker('bgColor', '--bg-primary', 'bg');
        this.bindColorPicker('downloadColor', '--download-color', 'download');
        this.bindColorPicker('uploadColor', '--upload-color', 'upload');
    },

    bindColorPicker(prefix, cssVar, storageKey) {
        const picker = document.getElementById(`${prefix}Picker`);
        const hex = document.getElementById(`${prefix}Hex`);
        const reset = document.getElementById(`reset${prefix.charAt(0).toUpperCase() + prefix.slice(1)}`);

        if (!picker || !hex) return;

        picker.addEventListener('input', (e) => {
            hex.value = e.target.value;
            this.applyColor(cssVar, e.target.value, storageKey);
        });

        hex.addEventListener('change', (e) => {
            const val = e.target.value;
            if (/^#[0-9a-fA-F]{6}$/.test(val)) {
                picker.value = val;
                this.applyColor(cssVar, val, storageKey);
            }
        });

        if (reset) {
            reset.addEventListener('click', () => {
                const defaultVal = this.getDefaultColor(storageKey);
                picker.value = defaultVal;
                hex.value = defaultVal;
                localStorage.removeItem(`nettools-color-${storageKey}`);
                // Remove inline override to revert to CSS default
                document.documentElement.style.removeProperty(cssVar);
                if (storageKey === 'accent') {
                    this.removeAccentOverrides();
                }
                if (storageKey === 'bg') {
                    document.documentElement.style.removeProperty('--bg-primary');
                }
                if (storageKey === 'download') {
                    document.documentElement.style.removeProperty('--download-color');
                    document.documentElement.style.removeProperty('--gauge-download');
                }
                if (storageKey === 'upload') {
                    document.documentElement.style.removeProperty('--upload-color');
                    document.documentElement.style.removeProperty('--gauge-upload');
                }
                // Refresh charts
                if (typeof SpeedTestPage !== 'undefined' && SpeedTestPage.chartsInitialized) {
                    setTimeout(() => SpeedTestPage.updateChartTheme(), 100);
                }
                Toast.info('Color restablecido');
            });
        }
    },

    getDefaultColor(key) {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        switch (key) {
            case 'accent': return this.defaults.accent;
            case 'bg': return isDark ? this.defaults.bgDark : this.defaults.bg;
            case 'download': return this.defaults.download;
            case 'upload': return this.defaults.upload;
            default: return '#ffa801';
        }
    },

    applyColor(cssVar, value, storageKey) {
        document.documentElement.style.setProperty(cssVar, value);
        localStorage.setItem(`nettools-color-${storageKey}`, value);

        // Apply related variables
        if (storageKey === 'accent') {
            this.applyAccentOverrides(value);
        }
        if (storageKey === 'download') {
            document.documentElement.style.setProperty('--gauge-download', value);
        }
        if (storageKey === 'upload') {
            document.documentElement.style.setProperty('--gauge-upload', value);
        }

        // Refresh charts
        if (typeof SpeedTestPage !== 'undefined' && SpeedTestPage.chartsInitialized) {
            setTimeout(() => SpeedTestPage.updateChartTheme(), 100);
        }
    },

    applyAccentOverrides(color) {
        document.documentElement.style.setProperty('--accent', color);
        document.documentElement.style.setProperty('--accent-hover', this.darkenColor(color, 15));
        document.documentElement.style.setProperty('--accent-light', this.lightenColor(color, 90));
        document.documentElement.style.setProperty('--border-focus', color);
        document.documentElement.style.setProperty('--sidebar-active-text', this.darkenColor(color, 10));
    },

    removeAccentOverrides() {
        ['--accent', '--accent-hover', '--accent-light', '--border-focus', '--sidebar-active-text'].forEach(v => {
            document.documentElement.style.removeProperty(v);
        });
    },

    darkenColor(hex, percent) {
        const num = parseInt(hex.replace('#', ''), 16);
        const r = Math.max(0, ((num >> 16) & 0xFF) - Math.round(255 * percent / 100));
        const g = Math.max(0, ((num >> 8) & 0xFF) - Math.round(255 * percent / 100));
        const b = Math.max(0, (num & 0xFF) - Math.round(255 * percent / 100));
        return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
    },

    lightenColor(hex, percent) {
        const num = parseInt(hex.replace('#', ''), 16);
        const r = Math.min(255, ((num >> 16) & 0xFF) + Math.round(255 * percent / 100));
        const g = Math.min(255, ((num >> 8) & 0xFF) + Math.round(255 * percent / 100));
        const b = Math.min(255, (num & 0xFF) + Math.round(255 * percent / 100));
        return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
    },

    loadCustomColors() {
        // Load saved custom colors from localStorage
        const colors = {
            accent: localStorage.getItem('nettools-color-accent'),
            bg: localStorage.getItem('nettools-color-bg'),
            download: localStorage.getItem('nettools-color-download'),
            upload: localStorage.getItem('nettools-color-upload'),
        };

        if (colors.accent) {
            this.applyColor('--accent', colors.accent, 'accent');
            this.updatePickerUI('accentColor', colors.accent);
        }
        if (colors.bg) {
            document.documentElement.style.setProperty('--bg-primary', colors.bg);
            this.updatePickerUI('bgColor', colors.bg);
        }
        if (colors.download) {
            document.documentElement.style.setProperty('--download-color', colors.download);
            document.documentElement.style.setProperty('--gauge-download', colors.download);
            this.updatePickerUI('downloadColor', colors.download);
        }
        if (colors.upload) {
            document.documentElement.style.setProperty('--upload-color', colors.upload);
            document.documentElement.style.setProperty('--gauge-upload', colors.upload);
            this.updatePickerUI('uploadColor', colors.upload);
        }
    },

    updatePickerUI(prefix, value) {
        const picker = document.getElementById(`${prefix}Picker`);
        const hex = document.getElementById(`${prefix}Hex`);
        if (picker) picker.value = value;
        if (hex) hex.value = value;
    },

    async loadSettings() {
        try {
            const settings = await API.settings.getAll();
            this.applySettings(settings);
        } catch {
            // Load from localStorage
            this.applySettings(this.getLocalSettings());
        }
    },

    applySettings(settings) {
        if (settings.auto_speed_test !== undefined) {
            document.getElementById('autoSpeedTest').checked = settings.auto_speed_test;
        }
        if (settings.speed_test_frequency) {
            document.getElementById('speedTestFrequency').value = settings.speed_test_frequency;
        }
        if (settings.speed_test_retention) {
            document.getElementById('speedTestRetention').value = settings.speed_test_retention;
        }
        if (settings.auto_network_scan !== undefined) {
            document.getElementById('autoNetworkScan').checked = settings.auto_network_scan;
        }
        if (settings.network_scan_frequency) {
            document.getElementById('networkScanFrequency').value = settings.network_scan_frequency;
        }
        if (settings.network_range) {
            document.getElementById('networkRange').value = settings.network_range;
        }
        if (settings.notify_new_devices !== undefined) {
            document.getElementById('notifyNewDevices').checked = settings.notify_new_devices;
        }
        // Telegram
        if (settings.telegram_enabled !== undefined) {
            document.getElementById('telegramEnabled').checked = settings.telegram_enabled;
        }
        if (settings.telegram_bot_token !== undefined) {
            document.getElementById('telegramBotToken').value = settings.telegram_bot_token || '';
        }
        if (settings.telegram_chat_id !== undefined) {
            document.getElementById('telegramChatId').value = settings.telegram_chat_id || '';
        }
        // Timezone
        if (settings.timezone !== undefined) {
            document.getElementById('timezoneSelect').value = settings.timezone;
        }
    },

    getLocalSettings() {
        const saved = localStorage.getItem('nettools-settings');
        if (saved) {
            try { return JSON.parse(saved); } catch {}
        }
        return {
            auto_speed_test: true,
            speed_test_frequency: '60',
            speed_test_retention: '30',
            auto_network_scan: true,
            network_scan_frequency: '15',
            network_range: '192.168.1.0/24',
            notify_new_devices: true,
            telegram_enabled: false,
            telegram_bot_token: '',
            telegram_chat_id: '',
            timezone: '1',
        };
    },

    async saveSettings() {
        const settings = {
            auto_speed_test: document.getElementById('autoSpeedTest').checked,
            speed_test_frequency: document.getElementById('speedTestFrequency').value,
            speed_test_retention: document.getElementById('speedTestRetention').value,
            auto_network_scan: document.getElementById('autoNetworkScan').checked,
            network_scan_frequency: document.getElementById('networkScanFrequency').value,
            network_range: document.getElementById('networkRange').value,
            notify_new_devices: document.getElementById('notifyNewDevices').checked,
            telegram_enabled: document.getElementById('telegramEnabled').checked,
            telegram_bot_token: document.getElementById('telegramBotToken').value.trim(),
            telegram_chat_id: document.getElementById('telegramChatId').value.trim(),
            timezone: document.getElementById('timezoneSelect').value,
        };

        try {
            await API.settings.update(settings);
            Toast.success('Configuracion guardada');
        } catch {
            // Save locally
            localStorage.setItem('nettools-settings', JSON.stringify(settings));
            Toast.success('Configuracion guardada localmente');
        }
    },

    async exportData() {
        try {
            const data = await API.exportData();
            this.downloadJSON(data, 'nettools-export.json');
        } catch {
            // Export local data
            const exportData = {
                exported_at: new Date().toISOString(),
                settings: this.getLocalSettings(),
                devices: NetworkPage.devices || [],
                message: 'Datos exportados desde modo demo',
            };
            this.downloadJSON(exportData, 'nettools-export.json');
        }
        Toast.success('Datos exportados');
    },

    downloadJSON(data, filename) {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    },

    async clearTests() {
        try {
            await API.speedtest.clearAll();
            Toast.success('Historial de tests eliminado');
        } catch {
            Toast.success('Historial limpiado (demo)');
        }
        // Reset SpeedTestPage UI
        if (typeof SpeedTestPage !== 'undefined' && SpeedTestPage.chartsInitialized) {
            SpeedTestPage._lastResultCount = 0;
            // Clear stats
            document.getElementById('bestDownload').textContent = '-- Mbps';
            document.getElementById('bestUpload').textContent = '-- Mbps';
            document.getElementById('bestPing').textContent = '-- ms';
            document.getElementById('totalTests').textContent = '0';
            // Clear gauges
            document.getElementById('downloadValue').textContent = '--';
            document.getElementById('uploadValue').textContent = '--';
            document.getElementById('livePing').textContent = '-- ms';
            document.getElementById('liveJitter').textContent = '-- ms';
            document.getElementById('liveServer').textContent = '--';
            document.getElementById('liveISP').textContent = '--';
            SpeedTestPage.updateGauge(SpeedTestPage.gaugeDownload, 0);
            SpeedTestPage.updateGauge(SpeedTestPage.gaugeUpload, 0);
            // Clear charts
            SpeedTestPage.chartHistory.updateSeries([
                { name: 'Descarga', data: [] },
                { name: 'Subida', data: [] },
            ]);
            SpeedTestPage.chartPing.updateSeries([
                { name: 'Ping', data: [] },
                { name: 'Jitter', data: [] },
            ]);
            SpeedTestPage.chartHourly.updateOptions({ xaxis: { categories: [] } });
            SpeedTestPage.chartHourly.updateSeries([
                { name: 'Descarga', data: [] },
                { name: 'Subida', data: [] },
            ]);
            // Clear recent tests table
            const tbody = document.getElementById('recentTestsBody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No hay tests registrados</td></tr>';
            }
        }
    },

    async clearDevices() {
        try {
            await API.devices.clearAll();
            Toast.success('Dispositivos reiniciados');
            NetworkPage.devices = [];
            NetworkPage.updateStats();
            NetworkPage.renderDevices();
        } catch {
            NetworkPage.devices = [];
            NetworkPage.updateStats();
            NetworkPage.renderDevices();
            Toast.success('Dispositivos reiniciados (demo)');
        }
    },

    async testTelegram() {
        const btn = document.getElementById('testTelegramBtn');
        const origHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Enviando...';

        // Save current settings first so backend has the token/chat_id
        await this.saveSettings();

        try {
            await API.settings.testTelegram();
            Toast.success('Mensaje de prueba enviado correctamente');
        } catch (err) {
            Toast.error(err.message || 'Error al enviar mensaje de prueba');
        } finally {
            btn.disabled = false;
            btn.innerHTML = origHTML;
        }
    }
};
