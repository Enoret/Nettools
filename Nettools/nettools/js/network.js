/* =========================================
   NetTools - Network / Net Alert Page
   ========================================= */

const NetworkPage = {
    devices: [],
    currentFilter: 'all',
    searchQuery: '',
    sortField: 'name',
    sortDirection: 'asc',
    initialized: false,
    historyChart: null,
    historyRange: '24h',
    _refreshInterval: null,
    _lastScanCheck: 0,

    async init() {
        if (!this.initialized) {
            this.bindEvents();
            this.initialized = true;
        }
        await this.loadDevices();
        this.loadDeviceHistory();
        this.loadAutoScanStatus();
        this.startAutoRefresh();
    },

    destroy() {
        this.stopAutoRefresh();
    },

    startAutoRefresh() {
        this.stopAutoRefresh();
        // Poll every 30 seconds to check for new data from background scans
        this._refreshInterval = setInterval(() => this._autoRefreshTick(), 30000);
    },

    stopAutoRefresh() {
        if (this._refreshInterval) {
            clearInterval(this._refreshInterval);
            this._refreshInterval = null;
        }
    },

    async _autoRefreshTick() {
        // Only refresh if this page is currently visible
        if (typeof Router !== 'undefined' && Router.currentPage !== 'network') return;

        try {
            // Reload device list and history to pick up background scan results
            const devices = await API.devices.getAll();
            const changed = JSON.stringify(devices.map(d => d.id + ':' + d.is_online))
                !== JSON.stringify(this.devices.map(d => d.id + ':' + d.is_online));
            if (changed) {
                this.devices = devices;
                this.updateStats();
                this.renderDevices();
                this.loadDeviceHistory();
            }
            this.loadAutoScanStatus();
        } catch {
            // Backend not available, skip
        }
    },

    async loadAutoScanStatus() {
        const indicator = document.getElementById('autoStatusIndicator');
        const text = document.getElementById('autoStatusText');
        if (!indicator || !text) return;

        try {
            const settings = await API.settings.getAll();
            const scanStatus = await API.devices.getScanStatus();

            if (scanStatus && scanStatus.in_progress) {
                indicator.className = 'auto-status-indicator active';
                indicator.querySelector('i').className = 'ri-radar-line spinning';
                text.textContent = 'Escaneo en curso...';
            } else if (settings.auto_network_scan) {
                const freq = settings.network_scan_frequency || '15';
                indicator.className = 'auto-status-indicator active';
                indicator.querySelector('i').className = 'ri-refresh-line';
                text.textContent = `Auto-escaneo (cada ${freq} min)`;
            } else {
                indicator.className = 'auto-status-indicator disabled';
                indicator.querySelector('i').className = 'ri-stop-circle-line';
                text.textContent = 'Auto-escaneo off';
            }
        } catch {
            indicator.className = 'auto-status-indicator disabled';
            indicator.querySelector('i').className = 'ri-wifi-off-line';
            text.textContent = 'Sin backend';
        }
    },

    bindEvents() {
        // Search
        document.getElementById('deviceSearch').addEventListener('input',
            Utils.debounce((e) => {
                this.searchQuery = e.target.value.toLowerCase();
                this.renderDevices();
            })
        );

        // Filters
        document.querySelectorAll('#page-network .filter-group .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#page-network .filter-group .filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentFilter = btn.dataset.filter;
                this.renderDevices();
            });
        });

        // Scan
        document.getElementById('scanNetworkBtn').addEventListener('click', () => this.scanNetwork());

        // Add device
        document.getElementById('addDeviceBtn').addEventListener('click', () => this.openModal());

        // Modal
        document.getElementById('modalClose').addEventListener('click', () => this.closeModal());
        document.getElementById('modalCancel').addEventListener('click', () => this.closeModal());
        document.getElementById('modalSave').addEventListener('click', () => this.saveDevice());

        // Close modal on overlay click
        document.getElementById('deviceModal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('deviceModal')) this.closeModal();
        });

        // Chart range buttons
        document.querySelectorAll('.chart-range-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.chart-range-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.historyRange = btn.dataset.range;
                this.loadDeviceHistory();
            });
        });
    },

    // --- Load Devices ---
    async loadDevices() {
        try {
            this.devices = await API.devices.getAll();
        } catch {
            // Demo data
            this.devices = this.getDemoDevices();
        }
        this.updateStats();
        this.renderDevices();
    },

    updateStats() {
        const total = this.devices.length;
        const online = this.devices.filter(d => d.is_online).length;
        const offline = total - online;
        const newDevices = this.devices.filter(d => d.status === 'new').length;

        document.getElementById('totalDevices').textContent = total;
        document.getElementById('onlineDevices').textContent = online;
        document.getElementById('offlineDevices').textContent = offline;
        document.getElementById('newDevices').textContent = newDevices;
    },

    // --- Sorting ---
    setSort(field) {
        if (this.sortField === field) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortField = field;
            this.sortDirection = 'asc';
        }
        this.renderDevices();
    },

    sortDevices(devices) {
        const dir = this.sortDirection === 'asc' ? 1 : -1;
        return [...devices].sort((a, b) => {
            let valA, valB;
            switch (this.sortField) {
                case 'name':
                    valA = (a.custom_name || a.hostname || '').toLowerCase();
                    valB = (b.custom_name || b.hostname || '').toLowerCase();
                    break;
                case 'ip':
                    // Sort IPs numerically
                    valA = (a.ip_address || '').split('.').map(n => n.padStart(3, '0')).join('.');
                    valB = (b.ip_address || '').split('.').map(n => n.padStart(3, '0')).join('.');
                    break;
                case 'mac':
                    valA = (a.mac_address || '').toLowerCase();
                    valB = (b.mac_address || '').toLowerCase();
                    break;
                case 'brand':
                    valA = (a.brand || '').toLowerCase();
                    valB = (b.brand || '').toLowerCase();
                    break;
                case 'location':
                    valA = (a.location || '').toLowerCase();
                    valB = (b.location || '').toLowerCase();
                    break;
                case 'status':
                    // Online first, then by status type
                    const onlineA = a.is_online ? 0 : 1;
                    const onlineB = b.is_online ? 0 : 1;
                    if (onlineA !== onlineB) return (onlineA - onlineB) * dir;
                    valA = a.status || '';
                    valB = b.status || '';
                    break;
                default:
                    valA = '';
                    valB = '';
            }
            if (valA < valB) return -1 * dir;
            if (valA > valB) return 1 * dir;
            return 0;
        });
    },

    // --- Render ---
    getFilteredDevices() {
        return this.devices.filter(d => {
            // Filter
            if (this.currentFilter !== 'all') {
                if (this.currentFilter === 'online' && !d.is_online) return false;
                if (this.currentFilter === 'offline' && d.is_online) return false;
                if (this.currentFilter === 'new' && d.status !== 'new') return false;
                if (this.currentFilter === 'saved' && d.status !== 'saved') return false;
                if (this.currentFilter === 'manual' && d.status !== 'manual') return false;
            }

            // Search
            if (this.searchQuery) {
                const search = this.searchQuery;
                const match =
                    (d.custom_name || '').toLowerCase().includes(search) ||
                    (d.hostname || '').toLowerCase().includes(search) ||
                    (d.ip_address || '').toLowerCase().includes(search) ||
                    (d.mac_address || '').toLowerCase().includes(search) ||
                    (d.brand || '').toLowerCase().includes(search) ||
                    (d.description || '').toLowerCase().includes(search) ||
                    (d.location || '').toLowerCase().includes(search);
                if (!match) return false;
            }

            return true;
        });
    },

    renderColumnHeaders() {
        const sortIcon = (field) => {
            if (this.sortField !== field) return '<i class="ri-arrow-up-down-line"></i>';
            return this.sortDirection === 'asc'
                ? '<i class="ri-arrow-up-s-line"></i>'
                : '<i class="ri-arrow-down-s-line"></i>';
        };
        const activeClass = (field) => this.sortField === field ? 'active' : '';

        return `
            <div class="devices-list-header">
                <span class="col-status"></span>
                <span class="col-icon"></span>
                <span class="col-header col-name ${activeClass('name')}" data-sort="name">
                    Nombre ${sortIcon('name')}
                </span>
                <span class="col-header col-ip ${activeClass('ip')}" data-sort="ip">
                    IP ${sortIcon('ip')}
                </span>
                <span class="col-header col-mac ${activeClass('mac')}" data-sort="mac">
                    MAC ${sortIcon('mac')}
                </span>
                <span class="col-header col-brand ${activeClass('brand')}" data-sort="brand">
                    Marca ${sortIcon('brand')}
                </span>
                <span class="col-header col-location ${activeClass('location')}" data-sort="location">
                    Ubicacion ${sortIcon('location')}
                </span>
                <span class="col-header col-state ${activeClass('status')}" data-sort="status">
                    Estado ${sortIcon('status')}
                </span>
                <span class="col-actions"></span>
            </div>
        `;
    },

    renderDevices() {
        const grid = document.getElementById('devicesGrid');
        const filtered = this.getFilteredDevices();

        if (filtered.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <i class="ri-radar-line"></i>
                    <h3>${this.devices.length === 0 ? 'Sin dispositivos' : 'Sin resultados'}</h3>
                    <p>${this.devices.length === 0
                        ? 'Escanea la red o registra dispositivos manualmente'
                        : 'No se encontraron dispositivos con los filtros actuales'}</p>
                    ${this.devices.length === 0 ? `
                        <button class="btn btn-primary" onclick="document.getElementById('scanNetworkBtn').click()">
                            <i class="ri-radar-line"></i> Escanear Ahora
                        </button>
                    ` : ''}
                </div>
            `;
            return;
        }

        // Sort devices
        const sorted = this.sortDevices(filtered);

        // Render column headers + device cards
        grid.innerHTML = this.renderColumnHeaders() + sorted.map(device => this.renderDeviceCard(device)).join('');

        // Bind sort headers
        grid.querySelectorAll('.col-header[data-sort]').forEach(col => {
            col.addEventListener('click', () => {
                this.setSort(col.dataset.sort);
            });
        });

        // Bind card actions
        grid.querySelectorAll('.device-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const device = this.devices.find(d => d.id === id);
                if (device) this.openModal(device);
            });
        });

        grid.querySelectorAll('.device-delete-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const device = this.devices.find(d => d.id === id);
                const name = device?.custom_name || device?.hostname || device?.ip_address || 'este dispositivo';
                showConfirm('Eliminar Dispositivo', `¿Seguro que quieres eliminar "${name}"?`, () => this.deleteDevice(id));
            });
        });

        grid.querySelectorAll('.device-ping-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const ip = btn.dataset.ip;
                btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i>';
                try {
                    const result = await API.ping.single(ip);
                    if (result.is_reachable) {
                        Toast.success(`${ip}: ${result.latency.toFixed(1)} ms`);
                    } else {
                        Toast.warning(`${ip}: No responde`);
                    }
                } catch {
                    // Demo
                    const lat = (Math.random() * 20 + 1).toFixed(1);
                    Toast.success(`${ip}: ${lat} ms (demo)`);
                }
                btn.innerHTML = '<i class="ri-wifi-line"></i>';
            });
        });
    },

    renderDeviceCard(device) {
        const name = device.custom_name || device.hostname || 'Sin nombre';
        const deviceType = device.device_type || 'other';
        const icon = Utils.getDeviceIcon(deviceType);
        const typeName = Utils.getDeviceTypeName(deviceType);
        const onlineClass = device.is_online ? 'online' : 'offline';
        const statusBadge = device.status === 'new' ? 'badge-new'
            : device.status === 'manual' ? 'badge-manual'
            : 'badge-saved';
        const statusText = device.status === 'new' ? 'Nuevo'
            : device.status === 'manual' ? 'Manual'
            : 'Guardado';

        return `
            <div class="device-card ${onlineClass} ${device.status === 'new' ? 'new-device' : ''}">
                <span class="device-status-dot ${onlineClass}"></span>
                <div class="device-icon">
                    <i class="${icon}"></i>
                </div>
                <div class="device-name-col col-name">
                    <div class="device-name">${this.escapeHtml(name)}</div>
                    ${device.description ? `<div class="device-description">${this.escapeHtml(device.description)}</div>` : ''}
                    ${deviceType !== 'other' ? `<span class="device-type-badge"><i class="${icon}"></i> ${typeName}</span>` : ''}
                </div>
                <div class="device-detail-col col-ip">
                    ${device.ip_address || '-'}
                    ${device.ip_address ? `<span class="ip-type-badge ${device.ip_type === 'static' ? 'ip-static' : 'ip-dhcp'}">${device.ip_type === 'static' ? 'Estatica' : 'DHCP'}</span>` : ''}
                </div>
                <div class="device-detail-col col-mac">${device.mac_address || '-'}</div>
                <div class="device-detail-col brand-col col-brand">${device.brand ? this.escapeHtml(device.brand) : '-'}</div>
                <div class="device-detail-col location-col col-location">${device.location ? this.escapeHtml(device.location) : '-'}</div>
                <span class="device-badge col-state ${statusBadge}">${statusText}</span>
                <div class="device-actions col-actions">
                    ${device.ip_address ? `
                        <button class="device-action-btn device-ping-btn" data-ip="${device.ip_address}" title="Ping">
                            <i class="ri-wifi-line"></i>
                        </button>
                    ` : ''}
                    <button class="device-action-btn device-edit-btn" data-id="${device.id}" title="Editar">
                        <i class="ri-pencil-line"></i>
                    </button>
                    <button class="device-action-btn delete device-delete-btn" data-id="${device.id}" title="Eliminar">
                        <i class="ri-delete-bin-line"></i>
                    </button>
                </div>
            </div>
        `;
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    // --- Scan Network ---
    async scanNetwork() {
        const progress = document.getElementById('scanProgress');
        const fill = document.getElementById('scanFill');
        const text = document.getElementById('scanText');
        const btn = document.getElementById('scanNetworkBtn');

        progress.classList.remove('hidden');
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Escaneando...';

        let pct = 0;
        const progressInterval = setInterval(() => {
            pct = Math.min(pct + Math.random() * 8, 95);
            fill.style.width = `${pct}%`;
            text.textContent = `Escaneando red... ${Math.round(pct)}%`;
        }, 500);

        try {
            const result = await API.devices.scan();
            clearInterval(progressInterval);
            fill.style.width = '100%';
            text.textContent = `Escaneo completado - ${result.found || 0} dispositivos encontrados`;

            Toast.success(`Escaneo completado: ${result.found || 0} dispositivos encontrados`);
            this.loadDevices();
            this.loadDeviceHistory();
        } catch {
            clearInterval(progressInterval);
            // Demo scan
            fill.style.width = '100%';
            text.textContent = 'Escaneo completado (Demo)';
            this.devices = this.getDemoDevices();
            this.updateStats();
            this.renderDevices();
            this.loadDeviceHistory();
            Toast.info('Escaneo demo completado');
        }

        setTimeout(() => {
            progress.classList.add('hidden');
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-radar-line"></i> Escanear Red';
        }, 2000);
    },

    // --- Modal ---
    openModal(device = null) {
        const modal = document.getElementById('deviceModal');
        const title = document.getElementById('modalTitle');

        if (device) {
            title.textContent = 'Editar Dispositivo';
            document.getElementById('deviceId').value = device.id;
            document.getElementById('deviceName').value = device.custom_name || '';
            document.getElementById('deviceIP').value = device.ip_address || '';
            document.getElementById('deviceMAC').value = device.mac_address || '';
            document.getElementById('deviceBrand').value = device.brand || '';
            document.getElementById('deviceDescription').value = device.description || '';
            document.getElementById('deviceLocation').value = device.location || '';
            document.getElementById('deviceType').value = device.device_type || 'other';
            document.getElementById('deviceIpType').value = device.ip_type || 'dhcp';
        } else {
            title.textContent = 'Nuevo Dispositivo';
            document.getElementById('deviceId').value = '';
            document.getElementById('deviceName').value = '';
            document.getElementById('deviceIP').value = '';
            document.getElementById('deviceMAC').value = '';
            document.getElementById('deviceBrand').value = '';
            document.getElementById('deviceDescription').value = '';
            document.getElementById('deviceLocation').value = '';
            document.getElementById('deviceType').value = 'other';
            document.getElementById('deviceIpType').value = 'dhcp';
        }

        modal.classList.add('visible');
        document.getElementById('deviceName').focus();
    },

    closeModal() {
        document.getElementById('deviceModal').classList.remove('visible');
    },

    async saveDevice() {
        const id = document.getElementById('deviceId').value;
        const data = {
            custom_name: document.getElementById('deviceName').value.trim(),
            ip_address: document.getElementById('deviceIP').value.trim(),
            mac_address: document.getElementById('deviceMAC').value.trim(),
            brand: document.getElementById('deviceBrand').value.trim(),
            description: document.getElementById('deviceDescription').value.trim(),
            location: document.getElementById('deviceLocation').value.trim(),
            device_type: document.getElementById('deviceType').value,
            ip_type: document.getElementById('deviceIpType').value,
            status: id ? undefined : 'manual',
        };

        // Basic validation
        if (!data.custom_name && !data.ip_address) {
            Toast.warning('Introduce al menos un nombre o una IP');
            return;
        }

        try {
            if (id) {
                await API.devices.update(parseInt(id), data);
                Toast.success('Dispositivo actualizado');
            } else {
                await API.devices.create(data);
                Toast.success('Dispositivo registrado');
            }
            this.closeModal();
            this.loadDevices();
        } catch (err) {
            // Demo mode - update locally
            if (id) {
                const idx = this.devices.findIndex(d => d.id === parseInt(id));
                if (idx >= 0) {
                    Object.assign(this.devices[idx], data);
                    if (data.status === undefined) this.devices[idx].status = 'saved';
                }
                Toast.success('Dispositivo actualizado (demo)');
            } else {
                this.devices.push({
                    id: Date.now(),
                    ...data,
                    hostname: '',
                    is_online: false,
                    status: 'manual',
                    first_seen: new Date().toISOString(),
                    last_seen: new Date().toISOString(),
                });
                Toast.success('Dispositivo registrado (demo)');
            }
            this.closeModal();
            this.updateStats();
            this.renderDevices();
        }
    },

    async deleteDevice(id) {
        try {
            await API.devices.delete(id);
            Toast.success('Dispositivo eliminado');
            this.loadDevices();
        } catch {
            // Demo
            this.devices = this.devices.filter(d => d.id !== id);
            this.updateStats();
            this.renderDevices();
            Toast.success('Dispositivo eliminado (demo)');
        }
    },

    // --- Demo Data ---
    getDemoDevices() {
        return [
            {
                id: 1, custom_name: 'Router Principal', hostname: 'router.local',
                ip_address: '192.168.1.1', mac_address: 'AA:BB:CC:11:22:33',
                brand: 'TP-Link', description: 'Router WiFi del salon',
                location: 'Salon', device_type: 'router',
                is_online: true, status: 'saved',
                first_seen: '2025-01-15T10:30:00Z', last_seen: new Date().toISOString(),
            },
            {
                id: 2, custom_name: 'NAS Synology', hostname: 'nas.local',
                ip_address: '192.168.1.10', mac_address: 'DD:EE:FF:44:55:66',
                brand: 'Synology', description: 'Almacenamiento de red',
                location: 'Oficina', device_type: 'nas',
                is_online: true, status: 'saved',
                first_seen: '2025-01-15T10:30:00Z', last_seen: new Date().toISOString(),
            },
            {
                id: 3, custom_name: 'Smart TV Samsung', hostname: '',
                ip_address: '192.168.1.50', mac_address: '11:22:33:AA:BB:CC',
                brand: 'Samsung', description: 'Television del salon',
                location: 'Salon', device_type: 'tv',
                is_online: true, status: 'saved',
                first_seen: '2025-02-01T08:00:00Z', last_seen: new Date().toISOString(),
            },
            {
                id: 4, custom_name: '', hostname: 'unknown-device',
                ip_address: '192.168.1.105', mac_address: '99:88:77:66:55:44',
                brand: '', description: '',
                location: '', device_type: 'other',
                is_online: true, status: 'new',
                first_seen: new Date().toISOString(), last_seen: new Date().toISOString(),
            },
            {
                id: 5, custom_name: 'Impresora HP', hostname: 'printer.local',
                ip_address: '192.168.1.30', mac_address: 'CC:DD:EE:FF:11:22',
                brand: 'HP', description: 'Impresora laser de la oficina',
                location: 'Oficina', device_type: 'printer',
                is_online: false, status: 'saved',
                first_seen: '2025-01-20T14:00:00Z', last_seen: '2025-06-10T09:00:00Z',
            },
            {
                id: 6, custom_name: 'Camara Jardin', hostname: '',
                ip_address: '192.168.1.80', mac_address: 'FF:AA:BB:CC:DD:EE',
                brand: 'Reolink', description: 'Camara IP exterior',
                location: 'Jardin', device_type: 'camera',
                is_online: true, status: 'saved',
                first_seen: '2025-03-05T11:00:00Z', last_seen: new Date().toISOString(),
            },
            {
                id: 7, custom_name: 'Switch TP-Link', hostname: '',
                ip_address: '192.168.1.2', mac_address: 'AB:CD:EF:12:34:56',
                brand: 'TP-Link', description: 'Switch 8 puertos rack',
                location: 'Rack A', device_type: 'switch',
                is_online: false, status: 'manual',
                first_seen: '2025-01-10T09:00:00Z', last_seen: '2025-01-10T09:00:00Z',
            },
        ];
    },

    // ==========================================
    //  DEVICE HISTORY CHART
    // ==========================================
    async loadDeviceHistory() {
        try {
            const data = await API.devices.getHistory({ range: this.historyRange });
            if (data && data.length > 0) {
                this.renderHistoryChart(data);
            } else {
                // Backend connected but no snapshots yet — generate from current devices
                this.renderHistoryChart(this.generateSnapshotsFromDevices());
            }
        } catch {
            // No backend — generate demo history from loaded devices
            this.renderHistoryChart(this.generateSnapshotsFromDevices());
        }
    },

    /**
     * Build synthetic history snapshots from the current device list so the
     * chart always has something meaningful to show, even without backend
     * snapshot data.  Generates one point per hour for the last 24 h with
     * slight random variation, ending with the real current counts.
     */
    generateSnapshotsFromDevices() {
        if (!this.devices || this.devices.length === 0) return [];

        const total = this.devices.length;
        const online = this.devices.filter(d => d.is_online).length;
        const offline = total - online;
        const newDev = this.devices.filter(d => d.status === 'new').length;

        const now = Date.now();
        const snapshots = [];
        const hours = 24;

        for (let i = hours; i >= 0; i--) {
            // Small random variation for earlier points so the chart is not flat
            const factor = i === 0 ? 1 : 0.7 + Math.random() * 0.35;
            const jitter = (v) => Math.max(0, Math.round(v * factor + (Math.random() * 2 - 1)));

            snapshots.push({
                timestamp: new Date(now - i * 3600000).toISOString(),
                total_devices: i === 0 ? total : jitter(total),
                online_devices: i === 0 ? online : jitter(online),
                offline_devices: i === 0 ? offline : jitter(offline),
                new_devices: i === 0 ? newDev : jitter(newDev),
            });
        }
        return snapshots;
    },

    renderHistoryChart(snapshots) {
        const container = document.getElementById('deviceHistoryChart');
        if (!container) return;

        // Always destroy previous chart instance to avoid stale references
        if (this.historyChart) {
            try { this.historyChart.destroy(); } catch (e) { /* ignore */ }
            this.historyChart = null;
        }

        // If no data, show empty state
        if (!snapshots || snapshots.length === 0) {
            container.innerHTML = `
                <div class="empty-state small" style="padding:30px 0;">
                    <i class="ri-line-chart-line"></i>
                    <p>Sin datos de historial. Los datos se recopilarán automáticamente con cada escaneo de red.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = '';

        const categories = snapshots.map(s => s.timestamp);
        const totalData = snapshots.map(s => s.total_devices);
        const onlineData = snapshots.map(s => s.online_devices);
        const offlineData = snapshots.map(s => s.offline_devices);
        const newData = snapshots.map(s => s.new_devices);

        // Read CSS variables for theming
        const style = getComputedStyle(document.documentElement);
        const textPrimary = style.getPropertyValue('--text-primary').trim() || '#0f172a';
        const textSecondary = style.getPropertyValue('--text-secondary').trim() || '#64748b';
        const bgSecondary = style.getPropertyValue('--bg-secondary').trim() || '#ffffff';
        const borderColor = style.getPropertyValue('--border').trim() || '#e2e8f0';

        const options = {
            series: [
                { name: 'Total', data: totalData },
                { name: 'En Línea', data: onlineData },
                { name: 'Desconectados', data: offlineData },
                { name: 'Nuevos', data: newData },
            ],
            chart: {
                type: 'area',
                height: 260,
                fontFamily: 'Inter, sans-serif',
                background: 'transparent',
                zoom: { enabled: false },
                toolbar: {
                    show: true,
                    tools: {
                        download: true,
                        selection: false,
                        zoom: false,
                        zoomin: false,
                        zoomout: false,
                        pan: false,
                        reset: false,
                    },
                },
            },
            colors: ['#6366f1', '#10b981', '#ef4444', '#f59e0b'],
            dataLabels: { enabled: false },
            stroke: {
                curve: 'smooth',
                width: [2.5, 2, 2, 1.5],
            },
            fill: {
                type: 'gradient',
                gradient: {
                    shadeIntensity: 1,
                    opacityFrom: 0.3,
                    opacityTo: 0.05,
                    stops: [0, 95, 100],
                },
            },
            xaxis: {
                type: 'datetime',
                categories: categories,
                labels: {
                    style: { colors: textSecondary, fontSize: '11px' },
                    datetimeUTC: false,
                },
                axisBorder: { color: borderColor },
                axisTicks: { color: borderColor },
            },
            yaxis: {
                min: 0,
                forceNiceScale: true,
                labels: {
                    style: { colors: textSecondary, fontSize: '11px' },
                    formatter: (val) => Math.round(val),
                },
            },
            grid: {
                borderColor: borderColor,
                strokeDashArray: 4,
                xaxis: { lines: { show: false } },
            },
            legend: {
                position: 'top',
                horizontalAlign: 'left',
                labels: { colors: textPrimary },
                fontSize: '12px',
                markers: { radius: 3 },
                itemMargin: { horizontal: 12 },
            },
            tooltip: {
                theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
                x: {
                    format: 'dd MMM HH:mm',
                },
                style: { fontSize: '12px' },
            },
        };

        this.historyChart = new ApexCharts(container, options);
        this.historyChart.render();
    },
};
