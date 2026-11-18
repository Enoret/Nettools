/* =========================================
   NetTools - Configurable table columns
   Visible columns, their order (drag & drop) and the default sort of a
   view are stored on the server (settings 'view_<name>'), so they are the
   same in every browser.
   ========================================= */

const ViewConfig = {
    _settings: null,

    /**
     * Load the config of a view.
     * @param {string} view      'netalert' | 'inventory'
     * @param {Array}  available [{id, label, sortable}]
     * @param {Object} defaults  {columns: [ids], sort: {field, dir}}
     */
    async load(view, available, defaults) {
        if (!this._settings) {
            try {
                this._settings = await API.settings.getAll();
            } catch (e) {
                this._settings = {};
            }
        }
        let cfg = null;
        try {
            cfg = JSON.parse(this._settings[`view_${view}`] || 'null');
        } catch (e) {
            cfg = null;
        }
        return this.normalize(cfg, available, defaults);
    },

    normalize(cfg, available, defaults) {
        const ids = new Set(available.map(c => c.id));
        const sortable = new Set(available.filter(c => c.sortable !== false).map(c => c.id));
        const columns = (cfg && Array.isArray(cfg.columns) ? cfg.columns : defaults.columns)
            .filter((id, i, arr) => ids.has(id) && arr.indexOf(id) === i);
        let sort = cfg && cfg.sort ? cfg.sort : defaults.sort;
        if (!sort || !sortable.has(sort.field)) sort = defaults.sort;
        // Required columns (e.g. the name) are always shown
        available.filter(c => c.required && !columns.includes(c.id)).reverse()
            .forEach(c => columns.unshift(c.id));
        return {
            columns: columns.length ? columns : defaults.columns.slice(),
            sort: { field: sort.field, dir: sort.dir === 'desc' ? 'desc' : 'asc' },
        };
    },

    async save(view, cfg) {
        const value = JSON.stringify(cfg);
        await API.settings.update({ [`view_${view}`]: value });
        if (this._settings) this._settings[`view_${view}`] = value;
    },

    // ---------- Editor modal ----------
    _ctx: null,

    /**
     * Open the column editor.
     * opts: {title, view, available, config, defaults, onSave(cfg)}
     */
    open(opts) {
        this._ctx = opts;
        this._bindOnce();
        document.getElementById('colCfgTitle').textContent = opts.title || 'Columnas';
        this._renderList(opts.config.columns);
        this._renderSort(opts.config.sort);
        document.getElementById('columnsModal').classList.add('visible');
    },

    close() {
        document.getElementById('columnsModal').classList.remove('visible');
        this._ctx = null;
    },

    _renderList(visibleIds) {
        const { available } = this._ctx;
        const byId = Object.fromEntries(available.map(c => [c.id, c]));
        // visible columns first (in their order), then the hidden ones
        const order = visibleIds.concat(available.map(c => c.id).filter(id => !visibleIds.includes(id)));
        const list = document.getElementById('colCfgList');
        list.innerHTML = order.map(id => {
            const c = byId[id];
            const on = visibleIds.includes(id);
            return `
                <li class="colcfg-item ${on ? '' : 'off'}" draggable="true" data-id="${id}">
                    <i class="ri-draggable colcfg-handle" title="Arrastra para cambiar el orden"></i>
                    <label class="colcfg-label">
                        <input type="checkbox" ${on ? 'checked' : ''} ${c.required ? 'disabled' : ''}>
                        <span>${NetworkPage.escapeHtml(c.label)}</span>
                        ${c.required ? '<small>(siempre visible)</small>' : ''}
                    </label>
                    <button type="button" class="colcfg-move" data-move="-1" title="Subir"><i class="ri-arrow-up-s-line"></i></button>
                    <button type="button" class="colcfg-move" data-move="1" title="Bajar"><i class="ri-arrow-down-s-line"></i></button>
                </li>`;
        }).join('');
    },

    _renderSort(sort) {
        const sel = document.getElementById('colCfgSortField');
        sel.innerHTML = this._ctx.available
            .filter(c => c.sortable !== false)
            .map(c => `<option value="${c.id}">${NetworkPage.escapeHtml(c.label)}</option>`).join('');
        sel.value = sort.field;
        document.getElementById('colCfgSortDir').value = sort.dir;
    },

    _collect() {
        const items = [...document.querySelectorAll('#colCfgList .colcfg-item')];
        return {
            columns: items.filter(li => li.querySelector('input').checked).map(li => li.dataset.id),
            sort: {
                field: document.getElementById('colCfgSortField').value,
                dir: document.getElementById('colCfgSortDir').value,
            },
        };
    },

    _bound: false,
    _bindOnce() {
        if (this._bound) return;
        this._bound = true;
        const list = document.getElementById('colCfgList');

        list.addEventListener('change', (e) => {
            if (e.target.type === 'checkbox') {
                e.target.closest('.colcfg-item').classList.toggle('off', !e.target.checked);
            }
        });

        list.addEventListener('click', (e) => {
            const btn = e.target.closest('.colcfg-move');
            if (!btn) return;
            const li = btn.closest('.colcfg-item');
            if (btn.dataset.move === '-1' && li.previousElementSibling) {
                list.insertBefore(li, li.previousElementSibling);
            } else if (btn.dataset.move === '1' && li.nextElementSibling) {
                list.insertBefore(li.nextElementSibling, li);
            }
        });

        // Drag & drop
        let dragged = null;
        list.addEventListener('dragstart', (e) => {
            dragged = e.target.closest('.colcfg-item');
            if (!dragged) return;
            dragged.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', dragged.dataset.id); } catch (err) { /* ignore */ }
        });
        list.addEventListener('dragend', () => {
            if (dragged) dragged.classList.remove('dragging');
            dragged = null;
        });
        list.addEventListener('dragover', (e) => {
            if (!dragged) return;
            e.preventDefault();
            const after = [...list.querySelectorAll('.colcfg-item:not(.dragging)')].find(li => {
                const r = li.getBoundingClientRect();
                return e.clientY < r.top + r.height / 2;
            });
            if (after) list.insertBefore(dragged, after);
            else list.appendChild(dragged);
        });
        list.addEventListener('drop', (e) => e.preventDefault());

        document.getElementById('colCfgClose').addEventListener('click', () => this.close());
        document.getElementById('colCfgCancel').addEventListener('click', () => this.close());
        document.getElementById('columnsModal').addEventListener('click', (e) => {
            if (e.target.id === 'columnsModal') this.close();
        });
        document.getElementById('colCfgReset').addEventListener('click', () => {
            if (!this._ctx) return;
            this._renderList(this._ctx.defaults.columns);
            this._renderSort(this._ctx.defaults.sort);
        });
        document.getElementById('colCfgSave').addEventListener('click', async () => {
            if (!this._ctx) return;
            const cfg = this._collect();
            if (!cfg.columns.length) {
                Toast.error('Deja al menos una columna visible');
                return;
            }
            const ctx = this._ctx;
            try {
                await this.save(ctx.view, cfg);
                Toast.success('Columnas guardadas');
                this.close();
                ctx.onSave(cfg);
            } catch (err) {
                Toast.error(`No se pudo guardar: ${err.message}`);
            }
        });
    },
};
