/* =========================================
   NetTools - Inventory Page
   Saved / manual devices from Net Alert plus items added by hand.
   ========================================= */

const InventoryPage = {
    items: [],
    filter: 'active',
    search: '',
    sortField: 'ip_address',
    sortDir: 'asc',
    initialized: false,
    WARRANTY_SOON_DAYS: 90,

    async init() {
        if (!this.initialized) {
            this.bindEvents();
            this.initialized = true;
        }
        if (!this.viewConfig) {
            this.viewConfig = await ViewConfig.load('inventory', this.COLUMNS, this.VIEW_DEFAULTS);
            this.sortField = this.viewConfig.sort.field;
            this.sortDir = this.viewConfig.sort.dir;
        }
        await this.load();
    },

    bindEvents() {
        document.getElementById('inventorySearch').addEventListener('input', Utils.debounce((e) => {
            this.search = e.target.value.trim().toLowerCase();
            this.render();
        }, 200));

        document.querySelectorAll('#inventoryFilters .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#inventoryFilters .filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.filter = btn.dataset.filter;
                this.render();
            });
        });

        document.getElementById('inventoryHead').addEventListener('click', (e) => {
            const th = e.target.closest('th[data-sort]');
            if (!th) return;
            const field = th.dataset.sort;
            if (this.sortField === field) {
                this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortField = field;
                this.sortDir = 'asc';
            }
            this.render();
        });
        document.getElementById('inventoryColumnsBtn').addEventListener('click', () => this.openColumnsEditor());

        document.getElementById('inventoryBody').addEventListener('click', (e) => {
            const row = e.target.closest('tr[data-id]');
            if (!row) return;
            const item = this.items.find(i => i.id === Number(row.dataset.id));
            if (item) this.openModal(item);
        });

        document.getElementById('inventoryAddBtn').addEventListener('click', () => this.openModal());
        document.getElementById('inventoryCsvBtn').addEventListener('click', () => this.exportCsv());
        document.getElementById('inventoryPrintBtn').addEventListener('click', () => this.print());

        document.getElementById('inventoryModalClose').addEventListener('click', () => this.closeModal());
        document.getElementById('inventoryCancel').addEventListener('click', () => this.closeModal());
        document.getElementById('inventorySave').addEventListener('click', () => this.save());
        document.getElementById('inventoryDelete').addEventListener('click', () => this.remove());
        document.getElementById('inventoryModal').addEventListener('click', (e) => {
            if (e.target.id === 'inventoryModal') this.closeModal();
        });
        document.getElementById('invLogoUploadBtn').addEventListener('click', () => {
            document.getElementById('invLogoFile').click();
        });
        document.getElementById('invLogoFile').addEventListener('change', (e) => {
            const file = e.target.files[0];
            e.target.value = '';
            if (file) this.uploadLogo(file);
        });
        document.getElementById('invLogoResetBtn').addEventListener('click', () => this.resetLogo());
        document.getElementById('invKind').addEventListener('change', () => this.updateKindFields());
        let brandTimer;
        document.getElementById('invBrand').addEventListener('input', () => {
            clearTimeout(brandTimer);
            brandTimer = setTimeout(() => this.refreshLogoEditor(), 500);
        });
        document.querySelectorAll('.inv-warranty-quick button').forEach(btn => {
            btn.addEventListener('click', () => this.setWarrantyYears(Number(btn.dataset.years)));
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('inventoryModal').classList.contains('visible')) {
                this.closeModal();
            }
        });
    },

    async load() {
        try {
            this.items = await API.inventory.list();
        } catch (err) {
            Toast.error(`No se pudo cargar el inventario: ${err.message}`);
            this.items = [];
        }
        this.updateStats();
        this.render();
    },

    // ---------- Helpers ----------
    esc(v) {
        return NetworkPage.escapeHtml(v == null ? '' : String(v));
    },

    daysUntil(dateStr) {
        if (!dateStr) return null;
        const d = new Date(dateStr + 'T00:00:00');
        if (isNaN(d)) return null;
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return Math.round((d - today) / 86400000);
    },

    warrantyState(item) {
        const days = this.daysUntil(item.warranty_until);
        if (days === null) return null;
        if (days < 0) return 'expired';
        if (days <= this.WARRANTY_SOON_DAYS) return 'soon';
        return 'ok';
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        const [y, m, d] = dateStr.split('-');
        return d && m && y ? `${d}/${m}/${y}` : dateStr;
    },

    formatPrice(v) {
        if (v === null || v === undefined || v === '') return '';
        return Number(v).toLocaleString(I18N.locale, { style: 'currency', currency: 'EUR' });
    },

    isRetired(item) {
        return item.asset_status === 'retired';
    },

    KIND_LABELS: { physical: 'Fisico', vm: 'VM', lxc: 'LXC', docker: 'Docker' },
    KIND_NAMES: { physical: 'Fisico', vm: 'Maquina virtual', lxc: 'Contenedor LXC', docker: 'Contenedor Docker' },

    isVirtual(item) {
        return !!item.asset_kind && item.asset_kind !== 'physical';
    },

    // ---------- Stats / list ----------
    updateStats() {
        const active = this.items.filter(i => !this.isRetired(i));
        const value = active.reduce((sum, i) => sum + (Number(i.purchase_price) || 0), 0);
        document.getElementById('invTotal').textContent = active.length;
        document.getElementById('invValue').textContent = this.formatPrice(value) || '0 €';
        document.getElementById('invWarranty').textContent =
            active.filter(i => this.warrantyState(i) === 'soon').length;
        document.getElementById('invRetired').textContent = this.items.length - active.length;
    },

    getFiltered() {
        return this.items.filter(i => {
            switch (this.filter) {
                case 'active': if (this.isRetired(i)) return false; break;
                case 'retired': if (!this.isRetired(i)) return false; break;
                case 'warranty': if (this.isRetired(i) || this.warrantyState(i) !== 'soon') return false; break;
                case 'offnet': if (i.device_id !== null) return false; break;
                case 'physical': if (this.isRetired(i) || this.isVirtual(i)) return false; break;
                case 'virtual': if (this.isRetired(i) || !this.isVirtual(i)) return false; break;
            }
            if (!this.search) return true;
            return ['name', 'brand', 'model', 'serial_number', 'location', 'ip_address', 'mac_address',
                    'supplier', 'notes', 'description', 'host']
                .some(k => (i[k] || '').toString().toLowerCase().includes(this.search));
        });
    },

    sorted(list) {
        const f = this.sortField;
        const dir = this.sortDir === 'asc' ? 1 : -1;
        return [...list].sort((a, b) => {
            let va = a[f], vb = b[f];
            if (f === 'device_type') {
                va = va && va !== 'other' ? Utils.getDeviceTypeName(va) : '';
                vb = vb && vb !== 'other' ? Utils.getDeviceTypeName(vb) : '';
            }
            if (f === 'asset_kind') {
                va = this.KIND_NAMES[va || 'physical'];
                vb = this.KIND_NAMES[vb || 'physical'];
            }
            if (f === 'ip_address') {
                // Numeric IP order (current IP if on the network); no IP always last
                const ka = Utils.ipSortKey(a.current_ip || a.ip_address);
                const kb = Utils.ipSortKey(b.current_ip || b.ip_address);
                if (ka === null || kb === null) return ka === kb ? 0 : (ka === null ? 1 : -1);
                return (ka - kb) * dir;
            }
            if (f === 'purchase_price') {
                va = va == null ? -1 : Number(va);
                vb = vb == null ? -1 : Number(vb);
                return (va - vb) * dir;
            }
            va = (va || '').toString().toLowerCase();
            vb = (vb || '').toString().toLowerCase();
            // empty values always last
            if (!va && vb) return 1;
            if (va && !vb) return -1;
            return va.localeCompare(vb, 'es') * dir;
        });
    },

    render() {
        const body = document.getElementById('inventoryBody');
        const empty = document.getElementById('inventoryEmpty');
        const list = this.sorted(this.getFiltered());

        const cols = this.visibleColumns();
        document.getElementById('inventoryHead').innerHTML = '<tr>' + cols.map(c =>
            `<th data-sort="${c.id}" class="${c.num ? 'num' : ''} ${this.sortField === c.id ? 'sorted' : ''}"` +
            ` data-dir="${this.sortField === c.id ? this.sortDir : ''}">${c.label}</th>`).join('') +
            '<th class="no-print"></th></tr>';

        empty.classList.toggle('hidden', list.length > 0);
        document.querySelector('.inventory-table-wrap').classList.toggle('hidden', list.length === 0);
        if (!this.items.length) {
            empty.querySelector('h3').textContent = 'Inventario vacio';
            empty.querySelector('p').textContent = 'Guarda dispositivos en Net Alert o anade material manualmente';
        } else {
            empty.querySelector('h3').textContent = 'Sin resultados';
            empty.querySelector('p').textContent = 'Ningun elemento coincide con el filtro o la busqueda';
        }

        body.innerHTML = list.map(i => this.renderRow(i, cols)).join('');
    },

    renderSerial(i) {
        if (!this.isVirtual(i)) {
            return i.serial_number ? `<span translate="no">${this.esc(i.serial_number)}</span>` : '<span class="inv-muted">-</span>';
        }
        const badge = `<span class="inv-kind-badge ${i.asset_kind}" title="${this.KIND_NAMES[i.asset_kind] || ''}: no es un dispositivo fisico">` +
                      `${this.KIND_LABELS[i.asset_kind] || i.asset_kind}</span>`;
        const id = i.serial_number ? ` <span translate="no">${this.esc(i.serial_number)}</span>` : '';
        const host = i.host ? `<div class="inv-sub">${I18N.t('en')} <span translate="no">${this.esc(i.host)}</span></div>` : '';
        return badge + id + host;
    },

    // Proxmox virtual NICs use the Proxmox OUI (BC:24:11)
    guessKind(item) {
        const brand = (item.brand || '').toLowerCase();
        const mac = (item.mac_address || '').toUpperCase();
        return brand.includes('proxmox') || mac.startsWith('BC:24:11') ? 'vm' : 'physical';
    },

    updateKindFields() {
        const kind = document.getElementById('invKind').value;
        const virtual = kind !== 'physical';
        document.getElementById('invSerialLabel').textContent =
            kind === 'vm' ? 'ID de la VM (VMID)' :
            kind === 'lxc' ? 'ID del contenedor (CTID)' :
            kind === 'docker' ? 'Nombre / ID del contenedor' : 'N\u00ba de serie';
        document.querySelectorAll('#inventoryModal .inv-virtual-only').forEach(el => { el.hidden = !virtual; });
        document.querySelectorAll('#inventoryModal .inv-physical-only').forEach(el => { el.hidden = virtual; });
    },

    // ---------- Columns (configurable, see columns.js) ----------
    COLUMNS: [
        { id: 'name', label: 'Equipo', required: true },
        { id: 'brand', label: 'Marca / Modelo' },
        { id: 'serial_number', label: 'Nº Serie / ID' },
        { id: 'location', label: 'Ubicacion' },
        { id: 'ip_address', label: 'IP / Red' },
        { id: 'warranty_until', label: 'Garantia' },
        { id: 'purchase_date', label: 'Compra' },
        { id: 'purchase_price', label: 'Precio', num: true },
        { id: 'supplier', label: 'Tienda / Proveedor' },
        { id: 'asset_kind', label: 'Tipo de activo' },
        { id: 'host', label: 'Anfitrion' },
        { id: 'mac_address', label: 'MAC' },
        { id: 'device_type', label: 'Tipo' },
        { id: 'description', label: 'Descripcion' },
        { id: 'notes', label: 'Notas' },
    ],
    VIEW_DEFAULTS: {
        columns: ['name', 'brand', 'serial_number', 'location', 'ip_address', 'warranty_until'],
        sort: { field: 'ip_address', dir: 'asc' },
    },
    viewConfig: null,

    visibleColumns() {
        const cfg = this.viewConfig || this.VIEW_DEFAULTS;
        return cfg.columns.map(id => this.COLUMNS.find(c => c.id === id)).filter(Boolean);
    },

    openColumnsEditor() {
        ViewConfig.open({
            title: 'Columnas del Inventario',
            view: 'inventory',
            available: this.COLUMNS,
            config: this.viewConfig || this.VIEW_DEFAULTS,
            defaults: this.VIEW_DEFAULTS,
            onSave: (cfg) => {
                this.viewConfig = cfg;
                this.sortField = cfg.sort.field;
                this.sortDir = cfg.sort.dir;
                this.render();
            },
        });
    },

    renderCell(i, col, visibleIds) {
        const muted = '<span class="inv-muted">-</span>';
        const text = (v) => this.esc(v) || muted;
        switch (col.id) {
            case 'name': {
                const icon = Utils.getDeviceIcon(i.device_type || 'other');
                const typeName = (i.device_type && i.device_type !== 'other' && !visibleIds.includes('device_type'))
                    ? Utils.getDeviceTypeName(i.device_type) : '';
                return `<td>
                    <div class="inv-name">
                        ${this.logoTile(i.brand, icon)}
                        <div>
                            <div class="inv-title"><span translate="no">${this.esc(i.name || '')}</span>${i.name ? '' : I18N.t('Sin nombre')}
                                ${this.isRetired(i) ? '<span class="device-badge badge-new">De baja</span>' : ''}</div>
                            ${typeName ? `<div class="inv-sub">${typeName}</div>` : ''}
                        </div>
                    </div>
                </td>`;
            }
            case 'brand': {
                const bm = [i.brand, i.model].filter(Boolean).map(v => this.esc(v)).join(' · ');
                return `<td translate="no">${bm || muted}</td>`;
            }
            case 'serial_number':
                return `<td class="mono">${this.renderSerial(i)}</td>`;
            case 'location':
                return `<td translate="no">${text(i.location)}</td>`;
            case 'ip_address': {
                let net;
                if (i.device_id === null) {
                    net = i.ip_address || i.mac_address
                        ? `<span class="inv-muted">${this.esc(i.ip_address || i.mac_address)}</span>`
                        : muted;
                    net += '<div class="inv-sub">Fuera de Net Alert</div>';
                } else {
                    const online = !!i.is_online;
                    net = `<span class="inv-net"><span class="device-status-dot ${online ? 'online' : 'offline'}"></span>` +
                          `${this.esc(i.current_ip || i.ip_address || '-')}</span>`;
                    net += `<div class="inv-sub">${online ? 'En linea' : 'Desconectado'}` +
                           `${i.network_name ? ' · <span translate="no">' + this.esc(i.network_name) + '</span>' : ''}</div>`;
                }
                return `<td class="mono">${net}</td>`;
            }
            case 'warranty_until': {
                const ws = this.warrantyState(i);
                if (!ws) return `<td>${muted}</td>`;
                const days = this.daysUntil(i.warranty_until);
                const label = ws === 'expired' ? 'Caducada' : ws === 'soon' ? `${days} dias` : '';
                return `<td>${this.formatDate(i.warranty_until)}` +
                    (label ? ` <span class="inv-warranty-badge ${ws}">${label}</span>` : '') + '</td>';
            }
            case 'purchase_date':
                return `<td>${this.formatDate(i.purchase_date) || muted}</td>`;
            case 'purchase_price':
                return `<td class="num">${this.formatPrice(i.purchase_price) || muted}</td>`;
            case 'supplier':
                return `<td translate="no">${text(i.supplier)}</td>`;
            case 'asset_kind':
                return `<td>${this.KIND_NAMES[i.asset_kind || 'physical']}</td>`;
            case 'host':
                return `<td translate="no">${text(i.host)}</td>`;
            case 'mac_address':
                return `<td class="mono">${text(i.mac_address)}</td>`;
            case 'device_type':
                return `<td>${i.device_type && i.device_type !== 'other' ? Utils.getDeviceTypeName(i.device_type) : muted}</td>`;
            case 'description':
                return `<td class="inv-wrap" translate="no">${text(i.description)}</td>`;
            case 'notes':
                return `<td class="inv-wrap" translate="no">${text(i.notes)}</td>`;
            default:
                return '<td></td>';
        }
    },

    renderRow(i, cols) {
        const ids = cols.map(c => c.id);
        return `
            <tr data-id="${i.id}" class="${this.isRetired(i) ? 'retired' : ''}">
                ${cols.map(c => this.renderCell(i, c, ids)).join('')}
                <td class="no-print inv-actions"><i class="ri-pencil-line" title="Editar ficha"></i></td>
            </tr>`;
    },

    // ---------- Logos ----------
    logoTile(brand, icon, extraClass = '') {
        return Utils.logoTile(brand, icon, extraClass);
    },

    async refreshLogoEditor() {
        const brand = document.getElementById('invBrand').value.trim();
        const type = document.getElementById('invType').value || 'other';
        const preview = document.getElementById('invLogoPreview');
        const hint = document.getElementById('invLogoHint');
        const reset = document.getElementById('invLogoResetBtn');
        const upload = document.getElementById('invLogoUploadBtn');
        preview.outerHTML = this.logoTile(brand, Utils.getDeviceIcon(type), 'inv-logo-lg')
            .replace('<span class="inv-logo', '<span id="invLogoPreview" class="inv-logo');
        upload.disabled = !brand;
        reset.hidden = true;
        if (!brand) {
            hint.textContent = 'Escribe la marca para buscar su logo';
            return;
        }
        hint.textContent = 'Se busca automaticamente segun la marca';
        try {
            const info = await API.logos.info(brand);
            if (info.custom) {
                hint.textContent = 'Logo propio (se usa en todos los equipos de esta marca)';
                reset.hidden = false;
            }
        } catch (err) { /* ignore */ }
    },

    readImage(file) {
        // Resize to max 128px and convert to PNG (also rasterizes SVGs)
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error('No se pudo leer el archivo'));
            reader.onload = () => {
                const img = new Image();
                img.onerror = () => reject(new Error('El archivo no es una imagen valida'));
                img.onload = () => {
                    const max = 128;
                    const scale = Math.min(1, max / Math.max(img.width || max, img.height || max));
                    const w = Math.max(1, Math.round((img.width || max) * scale));
                    const h = Math.max(1, Math.round((img.height || max) * scale));
                    const canvas = document.createElement('canvas');
                    canvas.width = w;
                    canvas.height = h;
                    canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                    resolve(canvas.toDataURL('image/png'));
                };
                img.src = reader.result;
            };
            reader.readAsDataURL(file);
        });
    },

    async uploadLogo(file) {
        const brand = document.getElementById('invBrand').value.trim();
        if (!brand) {
            Toast.error('Escribe primero la marca');
            return;
        }
        try {
            const dataUrl = await this.readImage(file);
            await API.logos.upload(brand, dataUrl);
            Utils.logoVersion = Date.now();
            Toast.success(`Logo guardado para ${brand}`);
            this.refreshLogoEditor();
            this.render();
        } catch (err) {
            Toast.error(`No se pudo guardar el logo: ${err.message}`);
        }
    },

    async resetLogo() {
        const brand = document.getElementById('invBrand').value.trim();
        if (!brand) return;
        try {
            await API.logos.remove(brand);
            Utils.logoVersion = Date.now();
            this.refreshLogoEditor();
            this.render();
        } catch (err) {
            Toast.error(`No se pudo quitar el logo: ${err.message}`);
        }
    },

    // ---------- Modal ----------
    openModal(item = null) {
        this.current = item;
        const set = (id, v) => { document.getElementById(id).value = v == null ? '' : v; };
        set('invId', item ? item.id : '');
        set('invName', item ? item.name : '');
        set('invType', item ? (item.device_type || 'other') : 'other');
        set('invStatus', item ? (item.asset_status || 'active') : 'active');
        set('invBrand', item ? item.brand : '');
        set('invModel', item ? item.model : '');
        set('invSerial', item ? item.serial_number : '');
        set('invKind', item ? (item.asset_kind || this.guessKind(item)) : 'physical');
        set('invHost', item ? item.host : '');
        document.getElementById('invHostList').innerHTML = [...new Set(this.items
            .filter(x => !this.isVirtual(x) && x.name).map(x => x.name))]
            .sort((a, b) => a.localeCompare(b, 'es'))
            .map(n => `<option value="${this.esc(n)}">`).join('');
        this.updateKindFields();
        set('invLocation', item ? item.location : '');
        set('invIP', item ? item.ip_address : '');
        set('invMAC', item ? item.mac_address : '');
        set('invPurchaseDate', item ? item.purchase_date : '');
        set('invPrice', item ? item.purchase_price : '');
        set('invWarranty', item ? item.warranty_until : '');
        set('invSupplier', item ? item.supplier : '');
        set('invDescription', item ? item.description : '');
        set('invNotes', item ? item.notes : '');

        const linked = item && item.device_id !== null;
        const info = document.getElementById('invLinkInfo');
        if (linked) {
            info.innerHTML = `<i class="ri-links-line"></i> Vinculado a Net Alert` +
                ` (${this.esc(item.current_ip || item.ip_address || 'sin IP')}` +
                `${item.mac_address ? ' · ' + this.esc(item.mac_address) : ''}).` +
                ` El nombre, tipo, marca, ubicacion y descripcion se comparten con Net Alert.`;
            info.hidden = false;
        } else if (item) {
            info.innerHTML = '<i class="ri-link-unlink"></i> No esta en Net Alert (anadido a mano o borrado de la red). ' +
                'Si vuelve a aparecer con la misma MAC y lo guardas, se vincula de nuevo.';
            info.hidden = false;
        } else {
            info.hidden = true;
        }
        document.querySelector('.inv-net-fields').hidden = !!linked;
        document.getElementById('inventoryDelete').style.display = item ? '' : 'none';
        document.getElementById('inventoryModalTitle').textContent = item ? 'Ficha de inventario' : 'Anadir al inventario';
        this.refreshLogoEditor();
        document.getElementById('inventoryModal').classList.add('visible');
        document.getElementById('invName').focus();
    },

    closeModal() {
        document.getElementById('inventoryModal').classList.remove('visible');
        this.current = null;
    },

    setWarrantyYears(years) {
        const base = document.getElementById('invPurchaseDate').value;
        const d = base ? new Date(base + 'T00:00:00') : new Date();
        d.setFullYear(d.getFullYear() + years);
        const pad = (n) => String(n).padStart(2, '0');
        document.getElementById('invWarranty').value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    },

    collect() {
        const val = (id) => document.getElementById(id).value.trim();
        const price = val('invPrice');
        const data = {
            name: val('invName'),
            device_type: val('invType'),
            asset_status: val('invStatus'),
            brand: val('invBrand'),
            model: val('invModel'),
            serial_number: val('invSerial'),
            asset_kind: val('invKind'),
            host: val('invKind') === 'physical' ? '' : val('invHost'),
            location: val('invLocation'),
            purchase_date: val('invPurchaseDate'),
            purchase_price: price === '' ? null : Number(price.replace(',', '.')),
            warranty_until: val('invWarranty'),
            supplier: val('invSupplier'),
            description: val('invDescription'),
            notes: document.getElementById('invNotes').value.trim(),
        };
        if (!this.current || this.current.device_id === null) {
            data.ip_address = val('invIP');
            data.mac_address = val('invMAC');
        }
        return data;
    },

    async save() {
        const data = this.collect();
        if (!data.name) {
            Toast.error('El nombre es obligatorio');
            return;
        }
        if (data.purchase_price !== null && isNaN(data.purchase_price)) {
            Toast.error('Precio no valido');
            return;
        }
        try {
            if (this.current) {
                await API.inventory.update(this.current.id, data);
            } else {
                if (data.purchase_price === null) delete data.purchase_price;
                await API.inventory.create(data);
            }
            Toast.success('Inventario guardado');
            this.closeModal();
            await this.load();
        } catch (err) {
            Toast.error(`No se pudo guardar: ${err.message}`);
        }
    },

    async remove() {
        if (!this.current) return;
        const linked = this.current.device_id !== null;
        const msg = I18N.t(linked
            ? 'Quitar "{name}" del inventario?\n\nSigue guardado en Net Alert, pero no volvera a aparecer en el inventario. Si prefieres conservar la ficha, marcalo "De baja".'
            : 'Eliminar "{name}" del inventario? Se pierde su ficha.', { name: this.current.name });
        if (!confirm(msg)) return;
        try {
            await API.inventory.remove(this.current.id);
            Toast.success('Eliminado del inventario');
            this.closeModal();
            await this.load();
        } catch (err) {
            Toast.error(`No se pudo eliminar: ${err.message}`);
        }
    },

    // ---------- Export ----------
    exportCsv() {
        const list = this.sorted(this.getFiltered());
        const cols = [
            [I18N.t('Nombre'), i => i.name],
            [I18N.t('Tipo'), i => (i.device_type && i.device_type !== 'other') ? Utils.getDeviceTypeName(i.device_type) : ''],
            [I18N.t('Estado'), i => I18N.t(this.isRetired(i) ? 'De baja' : 'En uso')],
            [I18N.t('Marca'), i => i.brand],
            [I18N.t('Modelo'), i => i.model],
            [I18N.t('Tipo de activo'), i => I18N.t(this.KIND_NAMES[i.asset_kind || 'physical'])],
            [I18N.t('Numero de serie / ID'), i => i.serial_number],
            [I18N.t('Anfitrion'), i => i.host],
            [I18N.t('Ubicacion'), i => i.location],
            [I18N.t('IP'), i => i.current_ip || i.ip_address],
            [I18N.t('MAC'), i => i.mac_address],
            [I18N.t('Red'), i => i.network_name],
            [I18N.t('En Net Alert'), i => i.device_id === null ? I18N.t('No') : I18N.t('Si')],
            [I18N.t('Fecha de compra'), i => this.formatDate(i.purchase_date)],
            [I18N.t('Precio (EUR)'), i => i.purchase_price == null ? '' : String(i.purchase_price).replace('.', I18N.lang === 'es' ? ',' : '.')],
            [I18N.t('Garantia hasta'), i => this.formatDate(i.warranty_until)],
            [I18N.t('Tienda / Proveedor'), i => i.supplier],
            [I18N.t('Descripcion'), i => i.description],
            [I18N.t('Notas'), i => i.notes],
        ];
        const cell = (v) => {
            const s = v == null ? '' : String(v);
            return /[";,\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        };
        // ';' for Spanish Excel, ',' for English
        const sep = I18N.lang === 'es' ? ';' : ',';
        const lines = [cols.map(c => cell(c[0])).join(sep)]
            .concat(list.map(i => cols.map(c => cell(c[1](i))).join(sep)));
        // BOM + ';' so Excel (Spanish locale) opens it with accents and columns
        const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${I18N.lang === 'en' ? 'inventory' : 'inventario'}-nettools-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    },

    print() {
        const filterName = document.querySelector('#inventoryFilters .filter-btn.active').textContent.trim();
        document.getElementById('inventoryPrintDate').textContent =
            I18N.t('{date} · {filter} · {n} elementos', {
                date: new Date().toLocaleDateString(I18N.locale), filter: filterName, n: this.getFiltered().length,
            });
        window.print();
    },
};
