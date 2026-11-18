/* =========================================
   NetTools - Settings Page
   ========================================= */

const SettingsPage = {
    initialized: false,
    networkRanges: [],   // extra ranges being edited: [{cidr, method, interface}]

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

        // Network ranges editor
        document.getElementById('addNetworkRangeBtn').addEventListener('click', () => this.addNetworkRange());
        document.getElementById('networkRangeInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.addNetworkRange();
        });
        document.getElementById('networkRangesList').addEventListener('click', (e) => {
            const btn = e.target.closest('[data-remove-range]');
            if (!btn) return;
            this.networkRanges = this.networkRanges.filter(r => r.cidr !== btn.dataset.removeRange);
            this.renderNetworkRanges();
        });

        // Telegram test
        document.getElementById('testTelegramBtn').addEventListener('click', () => this.testTelegram());

        // Bulk port scan
        document.getElementById('bulkPortScanBtn').addEventListener('click', () => this.startBulkPortScan());
        this.pollBulkPortScan();

        // UniFi
        document.getElementById('unifiAuth').addEventListener('change', () => this.updateUnifiAuthFields());
        document.getElementById('testUnifiBtn').addEventListener('click', () => this.testUnifi());

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
        } catch (err) {
            Toast.error(`No se pudieron cargar los ajustes: ${err.message}`);
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
        if (settings.scan_local_networks !== undefined) {
            document.getElementById('scanLocalNetworks').checked = settings.scan_local_networks;
        }
        this.loadNetworkInfo();
        if (settings.notify_new_devices !== undefined) {
            document.getElementById('notifyNewDevices').checked = settings.notify_new_devices;
        }
        if (settings.notify_speed_tests !== undefined) {
            document.getElementById('notifySpeedTests').checked = settings.notify_speed_tests;
        }
        if (settings.speed_test_alert_threshold !== undefined) {
            document.getElementById('speedTestAlertThreshold').value = settings.speed_test_alert_threshold;
        }
        if (settings.purge_stale_devices !== undefined) {
            document.getElementById('purgeStaleDevices').checked = settings.purge_stale_devices;
        }
        if (settings.stale_device_days) {
            document.getElementById('staleDeviceDays').value = settings.stale_device_days;
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
        // Port scan
        document.getElementById('autoPortScan').checked = !!settings.auto_port_scan;
        document.getElementById('portScanHour').value = settings.port_scan_hour || '3';
        document.getElementById('portScanProfile').value = settings.port_scan_profile || 'quick';
        document.getElementById('portScanScope').value = settings.port_scan_scope || 'online';
        document.getElementById('notifyNewPorts').checked = settings.notify_new_ports !== false;
        // UniFi
        document.getElementById('unifiEnabled').checked = !!settings.unifi_enabled;
        document.getElementById('unifiUrl').value = settings.unifi_url || '';
        document.getElementById('unifiAuth').value = settings.unifi_auth || 'api_key';
        document.getElementById('unifiApiKey').value = settings.unifi_api_key || '';
        document.getElementById('unifiUsername').value = settings.unifi_username || '';
        document.getElementById('unifiPassword').value = settings.unifi_password || '';
        document.getElementById('unifiSite').value = settings.unifi_site || 'default';
        document.getElementById('unifiVerifySsl').checked = !!settings.unifi_verify_ssl;
        this.updateUnifiAuthFields();
        // Timezone
        if (settings.timezone !== undefined) {
            document.getElementById('timezoneSelect').value = settings.timezone;
        }
    },

    async saveSettings() {
        const settings = {
            auto_speed_test: document.getElementById('autoSpeedTest').checked,
            speed_test_frequency: document.getElementById('speedTestFrequency').value,
            speed_test_retention: document.getElementById('speedTestRetention').value,
            auto_network_scan: document.getElementById('autoNetworkScan').checked,
            network_scan_frequency: document.getElementById('networkScanFrequency').value,
            scan_local_networks: document.getElementById('scanLocalNetworks').checked,
            network_ranges: this.networkRanges.map(r => r.cidr).join(','),
            notify_new_devices: document.getElementById('notifyNewDevices').checked,
            notify_speed_tests: document.getElementById('notifySpeedTests').checked,
            speed_test_alert_threshold: document.getElementById('speedTestAlertThreshold').value,
            purge_stale_devices: document.getElementById('purgeStaleDevices').checked,
            stale_device_days: document.getElementById('staleDeviceDays').value,
            telegram_enabled: document.getElementById('telegramEnabled').checked,
            telegram_bot_token: document.getElementById('telegramBotToken').value.trim(),
            telegram_chat_id: document.getElementById('telegramChatId').value.trim(),
            timezone: document.getElementById('timezoneSelect').value,
            auto_port_scan: document.getElementById('autoPortScan').checked,
            port_scan_hour: document.getElementById('portScanHour').value,
            port_scan_profile: document.getElementById('portScanProfile').value,
            port_scan_scope: document.getElementById('portScanScope').value,
            notify_new_ports: document.getElementById('notifyNewPorts').checked,
            ...this.getUnifiSettings(),
        };

        try {
            await API.settings.update(settings);
            Toast.success('Configuracion guardada');
            return true;
        } catch (err) {
            Toast.error(`No se pudo guardar la configuracion: ${err.message}`);
            return false;
        }
    },

    // --- Network ranges ---
    async loadNetworkInfo() {
        const localText = document.getElementById('localNetworksText');
        try {
            const info = await API.network.info();
            localText.textContent = info.local_networks.length
                ? info.local_networks.map(n => `${n.cidr} (${n.interface})`).join(', ')
                : 'ninguna detectada';
            this.networkRanges = info.ranges.filter(r => r.source === 'manual');
        } catch (err) {
            localText.textContent = 'no disponible';
            this.networkRanges = [];
        }
        this.renderNetworkRanges();
    },

    renderNetworkRanges() {
        const list = document.getElementById('networkRangesList');
        if (!this.networkRanges.length) {
            list.innerHTML = '<div class="ranges-empty">Sin redes adicionales: solo se escanea la red local.</div>';
            return;
        }
        const esc = (v) => NetworkPage.escapeHtml(String(v ?? ''));
        list.innerHTML = this.networkRanges.map(r => `
            <div class="range-row">
                <span class="range-cidr mono">${esc(r.cidr)}</span>
                <span class="range-method">
                    ${r.method === 'arp'
                        ? `<span class="range-badge arp">ARP</span>interfaz ${esc(r.interface)} · con MAC`
                        : '<span class="range-badge routed">Ping</span>red enrutada · sin MAC (por IP)'}
                </span>
                <button class="device-action-btn delete" data-remove-range="${esc(r.cidr)}" title="Quitar">
                    <i class="ri-delete-bin-line"></i>
                </button>
            </div>
        `).join('');
    },

    async addNetworkRange() {
        const input = document.getElementById('networkRangeInput');
        const value = input.value.trim();
        if (!value) return;
        try {
            const range = await API.network.check(value);
            if (this.networkRanges.some(r => r.cidr === range.cidr)) {
                Toast.warning(`${range.cidr} ya esta en la lista`);
                return;
            }
            this.networkRanges.push(range);
            this.renderNetworkRanges();
            input.value = '';
            Toast.info(`${range.cidr} anadida. Pulsa "Guardar" para aplicar.`);
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async exportData() {
        try {
            const data = await API.exportData();
            this.downloadJSON(data, 'nettools-export.json');
            Toast.success('Datos exportados');
        } catch (err) {
            Toast.error(`No se pudieron exportar los datos: ${err.message}`);
        }
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
        } catch (err) {
            Toast.error(`No se pudo limpiar el historial: ${err.message}`);
            return;
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
        } catch (err) {
            Toast.error(`No se pudieron reiniciar los dispositivos: ${err.message}`);
        }
    },

    async startBulkPortScan() {
        try {
            await API.settings.scanAllPorts();
            Toast.success('Escaneo de puertos de toda la red iniciado');
        } catch (err) {
            Toast.error(err.message || 'No se pudo iniciar el escaneo');
        }
        this.pollBulkPortScan();
    },

    async pollBulkPortScan() {
        clearTimeout(this._bulkPollTimer);
        const btn = document.getElementById('bulkPortScanBtn');
        const out = document.getElementById('bulkPortScanStatus');
        let st;
        try {
            st = await API.settings.scanAllPortsStatus();
        } catch (err) {
            return;
        }
        btn.disabled = !!st.running;
        if (st.running) {
            out.textContent = st.total
                ? `Escaneando ${st.done}/${st.total}${st.current ? ': ' + st.current : ''}...`
                : 'Iniciando escaneo...';
            this._bulkPollTimer = setTimeout(() => this.pollBulkPortScan(), 3000);
            this._bulkWasRunning = true;
        } else if (st.summary) {
            const s = st.summary;
            out.textContent = `Ultimo escaneo (${st.finished_at}): ${s.devices} dispositivos, ` +
                `${s.open_ports} puertos abiertos, ${s.changed_devices} con cambios` +
                (s.errors ? `, ${s.errors} errores` : '');
            if (this._bulkWasRunning) {
                this._bulkWasRunning = false;
                Toast.success('Escaneo de puertos completado');
                if (typeof NetworkPage !== 'undefined' && NetworkPage.loadDevices) NetworkPage.loadDevices();
            }
        }
    },

    getUnifiSettings() {
        return {
            unifi_enabled: document.getElementById('unifiEnabled').checked,
            unifi_url: document.getElementById('unifiUrl').value.trim(),
            unifi_auth: document.getElementById('unifiAuth').value,
            unifi_api_key: document.getElementById('unifiApiKey').value.trim(),
            unifi_username: document.getElementById('unifiUsername').value.trim(),
            unifi_password: document.getElementById('unifiPassword').value,
            unifi_site: document.getElementById('unifiSite').value.trim() || 'default',
            unifi_verify_ssl: document.getElementById('unifiVerifySsl').checked,
        };
    },

    updateUnifiAuthFields() {
        const mode = document.getElementById('unifiAuth').value;
        document.querySelectorAll('.unifi-auth-api_key').forEach(el => { el.hidden = mode !== 'api_key'; });
        document.querySelectorAll('.unifi-auth-login').forEach(el => { el.hidden = mode !== 'login'; });
    },

    async testUnifi() {
        const btn = document.getElementById('testUnifiBtn');
        const out = document.getElementById('unifiTestResult');
        const origHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Probando...';
        out.classList.remove('text-success', 'text-danger');
        try {
            const r = await API.settings.testUnifi(this.getUnifiSettings());
            const nets = Object.entries(r.networks || {})
                .sort((a, b) => b[1] - a[1])
                .map(([n, c]) => `${n}: ${c}`).join(', ');
            out.textContent = `OK: ${r.clients} clientes conectados${nets ? ' (' + nets + ')' : ''}`;
            out.classList.add('text-success');
            Toast.success('Conexion con UniFi correcta. Guarda la configuracion para usarla en los escaneos.');
        } catch (err) {
            out.textContent = `Error: ${err.message}`;
            out.classList.add('text-danger');
            Toast.error(err.message || 'No se pudo conectar con UniFi');
        } finally {
            btn.disabled = false;
            btn.innerHTML = origHTML;
        }
    },

    async testTelegram() {
        const btn = document.getElementById('testTelegramBtn');
        const origHTML = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Enviando...';

        // Save current settings first so backend has the token/chat_id
        const saved = await this.saveSettings();
        if (!saved) {
            btn.disabled = false;
            btn.innerHTML = origHTML;
            return;
        }

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
