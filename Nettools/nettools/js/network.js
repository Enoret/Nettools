/* =========================================
   NetTools - Network / Net Alert Page
   ========================================= */

const NetworkPage = {
    devices: [],
    currentFilter: 'all',
    searchQuery: '',
    sortField: 'ip',
    sortDirection: 'asc',
    initialized: false,
    historyChart: null,
    historyRange: '24h',
    _refreshInterval: null,
    _lastScanCheck: 0,
    portsDeviceId: null,
    portsScanning: false,
    selected: new Set(),
    lastSelectedId: null,

    async init() {
        if (!this.initialized) {
            this.bindEvents();
            this.initialized = true;
        }
        if (!this.viewConfig) {
            this.viewConfig = await ViewConfig.load('netalert', this.COLUMNS, this.VIEW_DEFAULTS);
            this.sortField = this.viewConfig.sort.field;
            this.sortDirection = this.viewConfig.sort.dir;
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
        this.bindBulkBar();
        document.getElementById('netalertColumnsBtn').addEventListener('click', () => this.openColumnsEditor());
        this._bp = this.breakpoint();
        window.addEventListener('resize', Utils.debounce(() => {
            const bp = this.breakpoint();
            if (bp !== this._bp) {
                this._bp = bp;
                if (Router.currentPage === 'network') this.renderDevices();
            }
        }, 200));
        // Search
        document.getElementById('deviceSearch').addEventListener('input',
            Utils.debounce((e) => {
                this.searchQuery = e.target.value.toLowerCase();
                this.renderDevices();
            })
        );

        // Filters
        document.querySelectorAll('#page-network .filter-group .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setFilter(btn.dataset.filter));
        });
        // The stat cards (Total / En linea / Desconectados / Nuevos) filter too
        document.querySelectorAll('#page-network .stat-filter').forEach(card => {
            card.addEventListener('click', () => {
                // clicking the active card again goes back to "all"
                const f = card.dataset.filter;
                this.setFilter(this.currentFilter === f && f !== 'all' ? 'all' : f);
            });
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    card.click();
                }
            });
        });
        this.syncFilterUI();

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

        // Merge modal
        document.getElementById('modalMerge').addEventListener('click', () => {
            const id = parseInt(document.getElementById('deviceId').value);
            const device = this.devices.find(d => d.id === id);
            if (device) {
                this.closeModal();
                this.openMergeModal(device);
            }
        });
        document.getElementById('mergeModalClose').addEventListener('click', () => this.closeMergeModal());
        document.getElementById('mergeCancel').addEventListener('click', () => this.closeMergeModal());
        document.getElementById('mergeModal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('mergeModal')) this.closeMergeModal();
        });
        document.getElementById('mergeSearch').addEventListener('input', () => this.renderMergeOptions());
        document.getElementById('mergeConfirm').addEventListener('click', () => this.confirmMerge());

        // Ports modal
        document.getElementById('portsModalClose').addEventListener('click', () => this.closePortsModal());
        document.getElementById('portsModal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('portsModal')) this.closePortsModal();
        });
        document.getElementById('portsScanBtn').addEventListener('click', () => this.scanPorts());

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
        } catch (err) {
            console.error('Error loading devices:', err);
            Toast.error(`No se pudieron cargar los dispositivos: ${err.message}`);
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

    // --- Filter (buttons + stat cards) ---
    setFilter(filter) {
        this.currentFilter = filter;
        this.syncFilterUI();
        this.renderDevices();
    },

    syncFilterUI() {
        document.querySelectorAll('#page-network .filter-group .filter-btn').forEach(b =>
            b.classList.toggle('active', b.dataset.filter === this.currentFilter));
        document.querySelectorAll('#page-network .stat-filter').forEach(c =>
            c.classList.toggle('active', c.dataset.filter === this.currentFilter));
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

    sortValue(d, field) {
        const low = (v) => (v || '').toString().toLowerCase();
        switch (field) {
            case 'name': return low(d.custom_name || d.hostname);
            case 'mac': return low(d.mac_address);
            case 'brand': return low(d.brand);
            case 'location': return low(d.location);
            case 'type': return d.device_type && d.device_type !== 'other' ? low(Utils.getDeviceTypeName(d.device_type)) : '';
            case 'network': return low(d.network_name);
            case 'hostname': return low(d.hostname);
            case 'description': return low(d.description);
            case 'last_seen': return d.last_seen || '';
            case 'first_seen': return d.first_seen || '';
            default: return '';
        }
    },

    sortDevices(devices) {
        const dir = this.sortDirection === 'asc' ? 1 : -1;
        const field = this.sortField;
        return [...devices].sort((a, b) => {
            if (field === 'ip') {
                // Numeric IP order; devices without any IP always last
                const ka = Utils.ipSortKey(a.ip_address || a.last_ip);
                const kb = Utils.ipSortKey(b.ip_address || b.last_ip);
                if (ka === null || kb === null) return ka === kb ? 0 : (ka === null ? 1 : -1);
                return (ka - kb) * dir;
            }
            if (field === 'ports') {
                return ((a.open_ports || 0) - (b.open_ports || 0)) * dir;
            }
            if (field === 'status') {
                // Online first, then by status type
                const oa = a.is_online ? 0 : 1, ob = b.is_online ? 0 : 1;
                if (oa !== ob) return (oa - ob) * dir;
                return (a.status || '').localeCompare(b.status || '') * dir;
            }
            const va = this.sortValue(a, field), vb = this.sortValue(b, field);
            // empty values always last
            if (!va && vb) return 1;
            if (va && !vb) return -1;
            return va.localeCompare(vb, 'es') * dir;
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
                    (d.last_ip || '').toLowerCase().includes(search) ||
                    (d.mac_address || '').toLowerCase().includes(search) ||
                    (d.brand || '').toLowerCase().includes(search) ||
                    (d.description || '').toLowerCase().includes(search) ||
                    (d.location || '').toLowerCase().includes(search) ||
                    (d.network_name || '').toLowerCase().includes(search);
                if (!match) return false;
            }

            return true;
        });
    },

    // ==========================================
    //  COLUMNS (configurable, see columns.js)
    // ==========================================
    COLUMNS: [
        { id: 'name', label: 'Nombre', width: 'minmax(140px, 1.6fr)', required: true },
        { id: 'ip', label: 'IP', width: 'minmax(110px, 1fr)' },
        { id: 'mac', label: 'MAC', width: 'minmax(130px, 1fr)' },
        { id: 'brand', label: 'Marca', width: 'minmax(90px, 1fr)' },
        { id: 'location', label: 'Ubicacion', width: 'minmax(80px, 0.8fr)' },
        { id: 'type', label: 'Tipo', width: 'minmax(80px, 0.8fr)' },
        { id: 'network', label: 'Red / VLAN', width: 'minmax(80px, 0.8fr)' },
        { id: 'hostname', label: 'Hostname', width: 'minmax(100px, 1fr)' },
        { id: 'description', label: 'Descripcion', width: 'minmax(120px, 1.3fr)' },
        { id: 'ports', label: 'Puertos', width: '70px' },
        { id: 'last_seen', label: 'Ultima vez visto', width: 'minmax(110px, 0.9fr)' },
        { id: 'first_seen', label: 'Descubierto', width: 'minmax(110px, 0.9fr)' },
        { id: 'status', label: 'Estado', width: '84px' },
    ],
    VIEW_DEFAULTS: { columns: ['name', 'ip', 'mac', 'brand', 'status'], sort: { field: 'ip', dir: 'asc' } },
    viewConfig: null,

    breakpoint() {
        const w = window.innerWidth;
        return w < 768 ? 'mobile' : w < 1100 ? 'tablet' : 'desktop';
    },

    /** Configured columns that fit the screen (status is kept when configured). */
    visibleColumns() {
        const cfg = this.viewConfig || this.VIEW_DEFAULTS;
        const cols = cfg.columns.map(id => this.COLUMNS.find(c => c.id === id)).filter(Boolean);
        const max = { mobile: 2, tablet: 4, desktop: 99 }[this.breakpoint()];
        if (cols.length <= max) return cols;
        const status = cols.find(c => c.id === 'status');
        const rest = cols.filter(c => c.id !== 'status').slice(0, max);
        return status ? rest.concat(status) : rest;
    },

    applyGridColumns(cols) {
        const actions = this.breakpoint() === 'mobile' ? '60px' : '108px';
        document.getElementById('devicesGrid').style.setProperty(
            '--device-grid-cols', `18px 8px 34px ${cols.map(c => c.width).join(' ')} ${actions}`);
    },

    openColumnsEditor() {
        ViewConfig.open({
            title: 'Columnas de Net Alert',
            view: 'netalert',
            available: this.COLUMNS,
            config: this.viewConfig || this.VIEW_DEFAULTS,
            defaults: this.VIEW_DEFAULTS,
            onSave: (cfg) => {
                this.viewConfig = cfg;
                this.sortField = cfg.sort.field;
                this.sortDirection = cfg.sort.dir;
                this.renderDevices();
            },
        });
    },

    colClass(id) {
        return id === 'status' ? 'col-state' : `col-${id}`;
    },

    renderColumnHeaders(cols) {
        const sortIcon = (field) => {
            if (this.sortField !== field) return '<i class="ri-arrow-up-down-line"></i>';
            return this.sortDirection === 'asc'
                ? '<i class="ri-arrow-up-s-line"></i>'
                : '<i class="ri-arrow-down-s-line"></i>';
        };
        return `
            <div class="devices-list-header">
                <span class="col-select"><input type="checkbox" id="selectAllDevices" title="Seleccionar todos los visibles"></span>
                <span class="col-status"></span>
                <span class="col-icon"></span>
                ${cols.map(c => `
                    <span class="col-header ${this.colClass(c.id)} ${this.sortField === c.id ? 'active' : ''}" data-sort="${c.id}">
                        ${c.label} ${sortIcon(c.id)}
                    </span>`).join('')}
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

        // Forget selected devices that no longer exist
        const existing = new Set(this.devices.map(d => d.id));
        this.selected.forEach(id => { if (!existing.has(id)) this.selected.delete(id); });
        this._visibleIds = sorted.map(d => d.id);

        // Render column headers + device cards
        const cols = this.visibleColumns();
        this.applyGridColumns(cols);
        grid.innerHTML = this.renderColumnHeaders(cols) + sorted.map(device => this.renderDeviceCard(device, cols)).join('');
        this.bindSelection(grid);

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

        grid.querySelectorAll('.service-icon').forEach(btn => {
            btn.addEventListener('click', () => {
                const device = this.devices.find(d => d.id === parseInt(btn.dataset.id));
                if (device) this.openPortsModal(device);
            });
        });

        grid.querySelectorAll('.device-ports-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const device = this.devices.find(d => d.id === parseInt(btn.dataset.id));
                if (device) this.openPortsModal(device);
            });
        });

        grid.querySelectorAll('.device-ping-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const ip = btn.dataset.ip;
                btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i>';
                try {
                    const result = await API.ping.single(ip);
                    if (result.is_reachable) {
                        Toast.success(`${ip}: ${result.latency != null ? result.latency.toFixed(1) + ' ms' : 'responde'}`);
                    } else {
                        Toast.warning(`${ip}: No responde`);
                    }
                } catch (err) {
                    Toast.error(`Ping a ${ip} fallido: ${err.message}`);
                }
                btn.innerHTML = '<i class="ri-wifi-line"></i>';
            });
        });
    },

    fmtTimestamp(ts) {
        // 'YYYY-MM-DD HH:MM:SS' -> 'DD/MM/YY HH:MM' (no Date parsing: Safari-safe)
        if (!ts) return '-';
        const [d, t] = ts.split(' ');
        const [y, m, dd] = (d || '').split('-');
        return y && m && dd ? `${dd}/${m}/${y.slice(2)} ${(t || '').slice(0, 5)}` : ts;
    },

    renderDescription(device, tag) {
        const auto = device.description_auto === 1;
        const text = this.escapeHtml(device.description);
        return auto
            ? `<${tag} class="device-description device-hint" title="${text}\n\nPista automatica segun fabricante, nombre y puertos. Editala para poner la tuya."><i class="ri-lightbulb-line"></i> ${text}</${tag}>`
            : `<${tag} class="device-description">${text}</${tag}>`;
    },

    renderCell(device, col, visibleIds) {
        const esc = (v) => this.escapeHtml(v);
        const deviceType = device.device_type || 'other';
        const icon = Utils.getDeviceIcon(deviceType);
        const typeName = Utils.getDeviceTypeName(deviceType);
        const dash = '-';
        switch (col.id) {
            case 'name': {
                const name = device.custom_name || device.hostname || 'Sin nombre';
                return `
                <div class="device-name-col col-name">
                    <div class="device-name">${esc(name)}</div>
                    ${device.description && !visibleIds.includes('description') ? this.renderDescription(device, 'div') : ''}
                    ${deviceType !== 'other' && !visibleIds.includes('type') ? `<span class="device-type-badge"><i class="${icon}"></i> ${typeName}</span>` : ''}
                    ${this.renderServiceIcons(device)}
                </div>`;
            }
            case 'ip':
                return `
                <div class="device-detail-col col-ip">
                    ${device.ip_address
                        ? `${device.ip_address}<span class="ip-type-badge ${device.ip_type === 'static' ? 'ip-static' : 'ip-dhcp'}">${device.ip_type === 'static' ? 'Estatica' : 'DHCP'}</span>`
                        : device.last_ip
                            ? `<span class="last-ip" title="Ultima IP conocida. Ahora la usa otro dispositivo o el equipo esta desconectado.">${esc(device.last_ip)}</span>`
                            : dash}
                    ${device.network_name && !visibleIds.includes('network') ? `<div class="network-name-badge" title="Red / VLAN segun UniFi"><i class="ri-git-branch-line"></i> ${esc(device.network_name)}</div>` : ''}
                </div>`;
            case 'mac':
                return `<div class="device-detail-col col-mac">${device.mac_address || dash}${device.mac_private
                    ? '<span class="mac-private-badge" title="MAC privada / aleatoria: el equipo puede cambiarla. Si aparece duplicado, usa Editar &gt; Fusionar.">privada</span>'
                    : ''}</div>`;
            case 'brand':
                return `<div class="device-detail-col brand-col col-brand">${device.brand ? esc(device.brand) : dash}</div>`;
            case 'location':
                return `<div class="device-detail-col location-col col-location">${device.location ? esc(device.location) : dash}</div>`;
            case 'type':
                return `<div class="device-detail-col location-col col-type">${deviceType !== 'other' ? `<i class="${icon}"></i> ${typeName}` : dash}</div>`;
            case 'network':
                return `<div class="device-detail-col location-col col-network">${device.network_name ? esc(device.network_name) : dash}</div>`;
            case 'hostname':
                return `<div class="device-detail-col location-col col-hostname">${device.hostname ? esc(device.hostname) : dash}</div>`;
            case 'description':
                return `<div class="device-detail-col location-col col-description" title="${esc(device.description || '')}">${device.description ? this.renderDescription(device, 'span') : dash}</div>`;
            case 'ports':
                return `<div class="device-detail-col col-ports">${device.open_ports || (device.last_port_scan ? '0' : dash)}</div>`;
            case 'last_seen':
                return `<div class="device-detail-col location-col col-last_seen">${this.fmtTimestamp(device.last_seen)}</div>`;
            case 'first_seen':
                return `<div class="device-detail-col location-col col-first_seen">${this.fmtTimestamp(device.first_seen)}</div>`;
            case 'status': {
                const badge = device.status === 'new' ? 'badge-new' : device.status === 'manual' ? 'badge-manual' : 'badge-saved';
                const text = device.status === 'new' ? 'Nuevo' : device.status === 'manual' ? 'Manual' : 'Guardado';
                return `<span class="device-badge col-state ${badge}">${text}</span>`;
            }
            default:
                return '<div></div>';
        }
    },

    renderDeviceCard(device, cols) {
        const deviceType = device.device_type || 'other';
        const icon = Utils.getDeviceIcon(deviceType);
        const onlineClass = device.is_online ? 'online' : 'offline';
        const visibleIds = cols.map(c => c.id);

        return `
            <div class="device-card ${onlineClass} ${device.status === 'new' ? 'new-device' : ''} ${this.selected.has(device.id) ? 'selected' : ''}">
                <span class="col-select"><input type="checkbox" class="device-select" data-id="${device.id}" ${this.selected.has(device.id) ? 'checked' : ''} aria-label="Seleccionar"></span>
                <span class="device-status-dot ${onlineClass}"></span>
                ${Utils.logoTile(device.brand, icon, `device-logo ${device.status === 'new' ? 'state-new' : device.is_online ? 'state-online' : 'state-offline'}`)}
                ${cols.map(c => this.renderCell(device, c, visibleIds)).join('')}
                <div class="device-actions col-actions">
                    ${device.ip_address ? `
                        <button class="device-action-btn device-ping-btn" data-ip="${device.ip_address}" title="Ping">
                            <i class="ri-wifi-line"></i>
                        </button>
                    ` : ''}
                    ${device.ip_address || device.open_ports ? `
                        <button class="device-action-btn device-ports-btn" data-id="${device.id}" title="Puertos abiertos">
                            <i class="ri-door-open-line"></i>
                            ${device.open_ports ? `<span class="device-ports-count">${device.open_ports}</span>` : ''}
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
            if (result.unifi && result.unifi.error) {
                Toast.error(`UniFi: ${result.unifi.error}`);
            }
            this.loadDevices();
            this.loadDeviceHistory();
        } catch (err) {
            clearInterval(progressInterval);
            fill.style.width = '0%';
            text.textContent = `Error en el escaneo: ${err.message}`;
            Toast.error(`Error en el escaneo: ${err.message}`);
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
            document.getElementById('deviceDescriptionHint').hidden = device.description_auto !== 1;
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
            document.getElementById('deviceDescriptionHint').hidden = true;
            document.getElementById('deviceLocation').value = '';
            document.getElementById('deviceType').value = 'other';
            document.getElementById('deviceIpType').value = 'dhcp';
        }

        document.getElementById('modalMerge').style.display = device ? '' : 'none';
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
            Toast.error(`No se pudo guardar el dispositivo: ${err.message}`);
        }
    },

    // ==========================================
    //  SERVICE ICONS
    // ==========================================
    SERVICE_CATEGORIES: [
        { key: 'web', label: 'Web', icon: 'ri-global-line',
          services: ['http', 'https', 'http-proxy', 'http-alt', 'https-alt', 'http-mgmt', 'ssl/http'],
          ports: [80, 443, 8080, 8443, 8000, 8008, 8888] },
        { key: 'ssh', label: 'SSH', icon: 'ri-terminal-box-line', services: ['ssh'], ports: [22] },
        { key: 'remote', label: 'Escritorio remoto', icon: 'ri-remote-control-line',
          services: ['ms-wbt-server', 'vnc', 'vnc-http'], ports: [3389, 5900, 5901] },
        { key: 'files', label: 'Archivos', icon: 'ri-folder-shared-line',
          services: ['microsoft-ds', 'netbios-ssn', 'smb', 'afp', 'nfs', 'ftp', 'ftps', 'rsync', 'webdav'],
          ports: [21, 139, 445, 548, 2049, 873] },
        { key: 'printer', label: 'Impresora', icon: 'ri-printer-line',
          services: ['ipp', 'jetdirect', 'printer'], ports: [631, 9100, 515] },
        { key: 'dns', label: 'DNS', icon: 'ri-signpost-line', services: ['domain'], ports: [53] },
        { key: 'db', label: 'Base de datos', icon: 'ri-database-2-line',
          services: ['mysql', 'postgresql', 'redis', 'mongodb', 'ms-sql-s', 'mongod'],
          ports: [3306, 5432, 6379, 27017, 1433] },
        { key: 'mail', label: 'Correo', icon: 'ri-mail-line',
          services: ['smtp', 'submission', 'smtps', 'imap', 'imaps', 'pop3', 'pop3s'],
          ports: [25, 465, 587, 143, 993, 110, 995] },
        { key: 'camera', label: 'Video / camara', icon: 'ri-camera-line', services: ['rtsp'], ports: [554, 8554] },
        { key: 'media', label: 'Multimedia', icon: 'ri-movie-2-line',
          services: ['plex', 'airplay', 'daap', 'raop', 'upnp'], ports: [32400, 8096, 7000, 8009, 1900] },
        { key: 'home', label: 'Domotica', icon: 'ri-home-wifi-line',
          services: ['mqtt', 'secure-mqtt'], ports: [8123, 1883, 8883] },
        { key: 'telnet', label: 'Telnet (inseguro)', icon: 'ri-alert-line', warn: true,
          services: ['telnet'], ports: [23] },
    ],

    parsePortSummary(summary) {
        if (!summary) return [];
        return summary.split(',').map(item => {
            const [port, service, tunnel] = item.split(':');
            return { port: parseInt(port), service: (service || '').toLowerCase(), tunnel: tunnel || '' };
        }).filter(p => !isNaN(p.port));
    },

    renderServiceIcons(device) {
        const ports = this.parsePortSummary(device.port_summary);
        if (!ports.length) return '';
        const found = [];
        for (const cat of this.SERVICE_CATEGORIES) {
            const matched = ports.filter(p =>
                cat.services.includes(p.service) ||
                (p.service === '' || p.service === 'unknown' ? cat.ports.includes(p.port) : false) ||
                (cat.key === 'web' && p.service.includes('http')));
            if (matched.length) found.push({ cat, ports: matched.map(p => p.port) });
        }
        const known = new Set(found.flatMap(f => f.ports));
        const others = ports.filter(p => !known.has(p.port)).map(p => p.port);
        if (others.length) {
            found.push({ cat: { key: 'other', label: 'Otros', icon: 'ri-more-line' }, ports: others });
        }
        return `<span class="device-services">${found.map(f => `
            <button class="service-icon ${f.cat.warn ? 'warn' : ''}" data-id="${device.id}"
                title="${f.cat.label}: ${f.ports.join(', ')}">
                <i class="${f.cat.icon}"></i>
            </button>`).join('')}</span>`;
    },

    // ==========================================
    //  MERGE DEVICES
    // ==========================================
    deviceLabel(d) {
        const name = d.custom_name || d.hostname || 'Sin nombre';
        const ip = d.ip_address || (d.last_ip ? `${d.last_ip} (antes)` : 'sin IP');
        const brand = d.brand ? ` · ${d.brand}` : '';
        return `${name} — ${ip} — ${d.mac_address || 'sin MAC'}${brand}`;
    },

    openMergeModal(device) {
        this.mergeSourceId = device.id;
        document.getElementById('mergeThis').textContent = this.deviceLabel(device);
        document.getElementById('mergeSearch').value = '';
        // If this record has a name and is not 'new', default to keeping its data
        document.getElementById('mergeKeep').value =
            (device.custom_name && device.status !== 'new') ? 'this' : 'other';
        this.renderMergeOptions();
        document.getElementById('mergeModal').classList.add('visible');
        document.getElementById('mergeSearch').focus();
    },

    closeMergeModal() {
        document.getElementById('mergeModal').classList.remove('visible');
        this.mergeSourceId = null;
    },

    renderMergeOptions() {
        const q = document.getElementById('mergeSearch').value.trim().toLowerCase();
        const select = document.getElementById('mergeTarget');
        const previous = select.value;
        const candidates = this.devices
            .filter(d => d.id !== this.mergeSourceId)
            .filter(d => !q || this.deviceLabel(d).toLowerCase().includes(q))
            .sort((a, b) => {
                // Named / saved devices first, then by name
                const ra = (a.custom_name ? 0 : 1) + (a.status === 'new' ? 1 : 0);
                const rb = (b.custom_name ? 0 : 1) + (b.status === 'new' ? 1 : 0);
                if (ra !== rb) return ra - rb;
                return (a.custom_name || a.hostname || '').localeCompare(b.custom_name || b.hostname || '');
            });
        select.innerHTML = candidates.map(d =>
            `<option value="${d.id}">${this.escapeHtml(this.deviceLabel(d))}</option>`).join('');
        if (candidates.some(d => String(d.id) === previous)) select.value = previous;
    },

    async confirmMerge() {
        const otherId = parseInt(document.getElementById('mergeTarget').value);
        if (!otherId) {
            Toast.warning('Selecciona el dispositivo con el que fusionar');
            return;
        }
        const thisId = this.mergeSourceId;
        const keepThis = document.getElementById('mergeKeep').value === 'this';
        // target keeps its name/details and adopts the source's MAC/IP
        const targetId = keepThis ? thisId : otherId;
        const sourceId = keepThis ? otherId : thisId;
        const target = this.devices.find(d => d.id === targetId);
        const source = this.devices.find(d => d.id === sourceId);

        showConfirm(
            'Fusionar dispositivos',
            `Se conservara "${target.custom_name || target.hostname || target.ip_address || target.mac_address}" ` +
            `con la MAC ${source.mac_address || '-'} y se eliminara el otro registro. ¿Continuar?`,
            async () => {
                try {
                    await API.devices.merge(targetId, sourceId);
                    Toast.success('Dispositivos fusionados');
                    this.closeMergeModal();
                    this.loadDevices();
                } catch (err) {
                    Toast.error(`No se pudo fusionar: ${err.message}`);
                }
            }
        );
    },

    // ==========================================
    //  PORT SCAN
    // ==========================================
    async openPortsModal(device) {
        this.portsDeviceId = device.id;
        const name = device.custom_name || device.hostname || device.ip_address;
        document.getElementById('portsModalTitle').textContent = `Puertos - ${name}`;
        document.getElementById('portsModalSubtitle').textContent =
            [device.ip_address, device.mac_address].filter(Boolean).join('  ·  ');
        document.getElementById('portsStatus').textContent = 'Cargando...';
        document.getElementById('portsTableBody').innerHTML = '';
        this.setPortsScanning(this.portsScanning && this._portsScanningId === device.id);
        document.getElementById('portsModal').classList.add('visible');

        try {
            const data = await API.devices.getPorts(device.id);
            if (this.portsDeviceId !== device.id) return;
            this.renderPorts(device, data.ports, new Set());
            if (data.in_progress) {
                document.getElementById('portsStatus').textContent = 'Escaneo en curso...';
            } else {
                document.getElementById('portsStatus').textContent = data.last_port_scan
                    ? `Ultimo escaneo: ${Utils.formatDate(data.last_port_scan)}`
                    : 'Este dispositivo no se ha escaneado todavia.';
            }
        } catch (err) {
            document.getElementById('portsStatus').textContent = `Error: ${err.message}`;
        }
    },

    closePortsModal() {
        document.getElementById('portsModal').classList.remove('visible');
        this.portsDeviceId = null;
    },

    setPortsScanning(scanning) {
        const btn = document.getElementById('portsScanBtn');
        const profile = document.getElementById('portsProfile');
        btn.disabled = scanning;
        profile.disabled = scanning;
        btn.innerHTML = scanning
            ? '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Escaneando...'
            : '<i class="ri-scan-2-line"></i> Escanear';
    },

    async scanPorts() {
        const deviceId = this.portsDeviceId;
        const device = this.devices.find(d => d.id === deviceId);
        if (!device || this.portsScanning) return;

        const profile = document.getElementById('portsProfile').value;
        const status = document.getElementById('portsStatus');
        this.portsScanning = true;
        this._portsScanningId = deviceId;
        this.setPortsScanning(true);
        status.textContent = profile === 'full'
            ? 'Escaneando 1000 puertos con deteccion de versiones (puede tardar hasta 2-3 minutos)...'
            : 'Escaneando los 100 puertos mas comunes...';

        try {
            const result = await API.devices.scanPorts(deviceId, profile);

            // Update the open port counter in the device list
            device.open_ports = result.ports.length;
            device.last_port_scan = result.scanned_at;
            this.renderDevices();

            const name = device.custom_name || device.hostname || device.ip_address;
            if (!result.first_scan && result.new_ports.length) {
                Toast.warning(`${name}: ${result.new_ports.length} puerto(s) nuevo(s) abierto(s)`);
            } else {
                Toast.success(`${name}: ${result.ports.length} puerto(s) abierto(s)`);
            }

            if (this.portsDeviceId !== deviceId) return; // modal closed or switched
            const highlight = result.first_scan
                ? new Set()
                : new Set(result.new_ports.map(p => `${p.port}/${p.protocol}`));
            this.renderPorts(device, result.ports, highlight);
            status.innerHTML = this.portsSummaryHtml(result);
        } catch (err) {
            if (this.portsDeviceId === deviceId) status.textContent = `Error: ${err.message}`;
            Toast.error(`Escaneo de puertos fallido: ${err.message}`);
        } finally {
            this.portsScanning = false;
            this._portsScanningId = null;
            this.setPortsScanning(false);
        }
    },

    portsSummaryHtml(result) {
        const parts = [
            `${result.scanned_count} puertos revisados en ${result.duration}s`,
            `${result.ports.length} abiertos`,
        ];
        if (!result.host_up) parts.push('el equipo no respondio');
        let html = this.escapeHtml(parts.join(' · '));
        if (!result.first_scan && result.new_ports.length) {
            html += ` · <span class="ports-diff-new">Nuevos: ${result.new_ports.map(p => p.port).join(', ')}</span>`;
        }
        if (result.closed_ports.length) {
            html += ` · <span class="ports-diff-closed">Cerrados: ${result.closed_ports.map(p => p.port).join(', ')}</span>`;
        }
        return html;
    },

    renderPorts(device, ports, highlight) {
        const tbody = document.getElementById('portsTableBody');
        if (!ports || ports.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="table-empty">No hay puertos abiertos conocidos</td></tr>';
            return;
        }
        tbody.innerHTML = ports.map(p => {
            const key = `${p.port}/${p.protocol}`;
            const isNew = highlight.has(key);
            const url = this.portUrl(device.ip_address, p);
            const portLabel = url
                ? `<a href="${url}" target="_blank" rel="noopener noreferrer" title="Abrir ${url}">${p.port}</a>`
                : `${p.port}`;
            const productVersion = [p.product, p.version].filter(Boolean).join(' ');
            return `
                <tr class="${isNew ? 'port-new' : ''}">
                    <td class="port-number">${portLabel}<span class="port-proto">/${this.escapeHtml(p.protocol)}</span>
                        ${isNew ? '<span class="device-badge badge-new port-badge-new">Nuevo</span>' : ''}</td>
                    <td>${this.escapeHtml(p.service) || '-'}${p.tunnel ? ` <span class="port-proto">(${this.escapeHtml(p.tunnel)})</span>` : ''}</td>
                    <td>${this.escapeHtml(productVersion) || '-'}</td>
                    <td>${p.first_seen ? Utils.formatDate(p.first_seen) : '-'}</td>
                </tr>
            `;
        }).join('');
    },

    /** Build a clickable URL for web-like services, or null. */
    portUrl(ip, p) {
        if (!ip) return null;
        const svc = (p.service || '').toLowerCase();
        const isTls = p.tunnel === 'ssl' || svc === 'https' || svc.endsWith('-ssl') || [443, 8443].includes(p.port);
        const isWeb = svc.includes('http') || [80, 443, 8080, 8443].includes(p.port);
        if (!isWeb) return null;
        const scheme = isTls ? 'https' : 'http';
        const defaultPort = isTls ? 443 : 80;
        return `${scheme}://${ip}${p.port === defaultPort ? '' : ':' + p.port}/`;
    },

    // ==========================================
    //  BULK SELECTION
    // ==========================================
    bindSelection(grid) {
        grid.querySelectorAll('.device-select').forEach(cb => {
            cb.addEventListener('click', (e) => {
                const id = Number(cb.dataset.id);
                // Shift+click selects the range from the last clicked device
                if (e.shiftKey && this.lastSelectedId !== null) {
                    const a = this._visibleIds.indexOf(this.lastSelectedId);
                    const b = this._visibleIds.indexOf(id);
                    if (a !== -1 && b !== -1) {
                        const [from, to] = a < b ? [a, b] : [b, a];
                        this._visibleIds.slice(from, to + 1).forEach(x => {
                            if (cb.checked) this.selected.add(x); else this.selected.delete(x);
                        });
                    }
                } else if (cb.checked) {
                    this.selected.add(id);
                } else {
                    this.selected.delete(id);
                }
                this.lastSelectedId = id;
                this.refreshSelectionUI();
            });
        });
        const all = document.getElementById('selectAllDevices');
        if (all) {
            all.addEventListener('change', () => {
                this._visibleIds.forEach(id => { if (all.checked) this.selected.add(id); else this.selected.delete(id); });
                this.refreshSelectionUI();
            });
        }
        this.refreshSelectionUI();
    },

    refreshSelectionUI() {
        const grid = document.getElementById('devicesGrid');
        grid.querySelectorAll('.device-select').forEach(cb => {
            const on = this.selected.has(Number(cb.dataset.id));
            cb.checked = on;
            cb.closest('.device-card').classList.toggle('selected', on);
        });
        const all = document.getElementById('selectAllDevices');
        const visible = this._visibleIds || [];
        const selVisible = visible.filter(id => this.selected.has(id)).length;
        if (all) {
            all.checked = visible.length > 0 && selVisible === visible.length;
            all.indeterminate = selVisible > 0 && selVisible < visible.length;
        }
        document.getElementById('bulkCount').textContent = this.selected.size;
        document.getElementById('bulkBar').classList.toggle('hidden', this.selected.size === 0);
        const locations = [...new Set(this.devices.map(d => d.location).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));
        document.getElementById('bulkLocationList').innerHTML =
            locations.map(l => `<option value="${this.escapeHtml(l)}">`).join('');
    },

    clearSelection() {
        this.selected.clear();
        this.lastSelectedId = null;
        this.refreshSelectionUI();
    },

    selectedDevices() {
        return this.devices.filter(d => this.selected.has(d.id));
    },

    async bulkApply(payload, successMsg) {
        const ids = [...this.selected];
        if (!ids.length) return;
        try {
            const r = await API.bulkDevices({ ids, ...payload });
            Toast.success(successMsg(r));
            if (payload.action === 'delete') this.clearSelection();
            await this.loadDevices();
        } catch (err) {
            Toast.error(`No se pudo aplicar el cambio: ${err.message}`);
        }
    },

    bindBulkBar() {
        document.getElementById('bulkClearBtn').addEventListener('click', () => this.clearSelection());

        document.getElementById('bulkDeleteBtn').addEventListener('click', () => {
            const sel = this.selectedDevices();
            if (!sel.length) return;
            const saved = sel.filter(d => d.status !== 'new').length;
            const names = sel.slice(0, 5).map(d => d.custom_name || d.hostname || d.ip_address || d.last_ip || d.mac_address).join(', ');
            const msg = `¿Seguro que quieres eliminar ${sel.length} dispositivo${sel.length > 1 ? 's' : ''}?\n\n` +
                `${names}${sel.length > 5 ? ` y ${sel.length - 5} mas` : ''}` +
                (saved ? `\n\nAtencion: ${saved} ${saved > 1 ? 'estan guardados o son manuales' : 'esta guardado o es manual'}. ` +
                         'Su ficha se conserva en el Inventario.' : '');
            showConfirm('Eliminar dispositivos', msg, () =>
                this.bulkApply({ action: 'delete' }, r => `${r.deleted} dispositivo${r.deleted === 1 ? '' : 's'} eliminado${r.deleted === 1 ? '' : 's'}`));
        });

        document.getElementById('bulkSaveBtn').addEventListener('click', () => {
            const n = this.selectedDevices().filter(d => d.status === 'new').length;
            if (!n) {
                Toast.info('Los seleccionados ya estan guardados');
                return;
            }
            this.bulkApply({ action: 'update', status: 'saved' }, () => `${n} dispositivo${n === 1 ? '' : 's'} guardado${n === 1 ? '' : 's'}`);
        });

        const typeSel = document.getElementById('bulkTypeSelect');
        typeSel.addEventListener('change', () => {
            const type = typeSel.value;
            typeSel.value = '';
            if (!type) return;
            this.bulkApply({ action: 'update', device_type: type },
                r => `Tipo "${Utils.getDeviceTypeName(type)}" aplicado a ${r.updated} dispositivo${r.updated === 1 ? '' : 's'}`);
        });

        const locInput = document.getElementById('bulkLocationInput');
        const applyLocation = () => {
            const loc = locInput.value.trim();
            this.bulkApply({ action: 'update', location: loc },
                r => loc ? `Ubicacion "${loc}" aplicada a ${r.updated} dispositivo${r.updated === 1 ? '' : 's'}`
                         : `Ubicacion borrada en ${r.updated} dispositivo${r.updated === 1 ? '' : 's'}`);
            locInput.value = '';
        };
        document.getElementById('bulkLocationBtn').addEventListener('click', applyLocation);
        locInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') applyLocation(); });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.selected.size && !document.querySelector('.modal-overlay.visible')) {
                this.clearSelection();
            }
        });
    },

    async deleteDevice(id) {
        try {
            await API.devices.delete(id);
            Toast.success('Dispositivo eliminado');
            this.loadDevices();
        } catch (err) {
            Toast.error(`No se pudo eliminar el dispositivo: ${err.message}`);
        }
    },

    // ==========================================
    //  DEVICE HISTORY CHART
    // ==========================================
    async loadDeviceHistory() {
        try {
            const data = await API.devices.getHistory({ range: this.historyRange });
            this.renderHistoryChart(data || []);
        } catch (err) {
            console.error('Error loading device history:', err);
            this.renderHistoryChart([], `No se pudo cargar el historial: ${err.message}`);
        }
    },

    renderHistoryChart(snapshots, errorMessage = null) {
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
                    <i class="${errorMessage ? 'ri-error-warning-line' : 'ri-line-chart-line'}"></i>
                    <p>${errorMessage ? this.escapeHtml(errorMessage) : 'Sin datos de historial en este periodo. Los datos se recopilan automáticamente con cada escaneo de red.'}</p>
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
