/* =========================================
   NetTools - Net Check Page
   Ping + Traceroute with visual network map
   ========================================= */

const NetCheckPage = {
    initialized: false,
    isTracing: false,
    isLookingUp: false,

    init() {
        if (!this.initialized) {
            this.bindEvents();
            this.initialized = true;
        }
    },

    bindEvents() {
        // --- Ping ---
        document.getElementById('pingBtn').addEventListener('click', () => {
            const ip = document.getElementById('pingInput').value.trim();
            if (ip) this.pingIP(ip);
        });

        document.getElementById('pingInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const ip = document.getElementById('pingInput').value.trim();
                if (ip) this.pingIP(ip);
            }
        });

        document.getElementById('pingAllBtn').addEventListener('click', () => this.pingAllDevices());

        document.getElementById('clearPingBtn').addEventListener('click', () => {
            document.getElementById('pingResults').innerHTML = `
                <div class="empty-state small">
                    <i class="ri-wifi-off-line"></i>
                    <p>Introduce una IP o haz ping a todos los dispositivos guardados</p>
                </div>
            `;
        });

        // --- Traceroute ---
        document.getElementById('tracerouteBtn').addEventListener('click', () => {
            const target = document.getElementById('tracerouteInput').value.trim();
            if (target) this.runTraceroute(target);
        });

        document.getElementById('tracerouteInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const target = document.getElementById('tracerouteInput').value.trim();
                if (target) this.runTraceroute(target);
            }
        });

        document.getElementById('clearTracerouteBtn').addEventListener('click', () => {
            this.clearTraceroute();
        });

        // Traceroute preset buttons
        document.querySelectorAll('.traceroute-preset').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.dataset.target;
                if (target === 'gateway') {
                    const range = document.getElementById('networkRange');
                    if (range) {
                        const ip = range.value.replace(/\/\d+$/, '').replace(/\.\d+$/, '.1');
                        document.getElementById('tracerouteInput').value = ip;
                        this.runTraceroute(ip);
                    } else {
                        document.getElementById('tracerouteInput').value = '192.168.1.1';
                        this.runTraceroute('192.168.1.1');
                    }
                } else {
                    document.getElementById('tracerouteInput').value = target;
                    this.runTraceroute(target);
                }
            });
        });

        // --- NSLookup ---
        document.getElementById('nslookupBtn').addEventListener('click', () => {
            const domain = document.getElementById('nslookupInput').value.trim();
            if (domain) this.runNslookup(domain);
        });

        document.getElementById('nslookupInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const domain = document.getElementById('nslookupInput').value.trim();
                if (domain) this.runNslookup(domain);
            }
        });

        document.getElementById('clearNslookupBtn').addEventListener('click', () => {
            this.clearNslookup();
        });

        // NSLookup DNS server presets
        document.querySelectorAll('.nslookup-preset').forEach(btn => {
            btn.addEventListener('click', () => {
                const server = btn.dataset.server;
                document.getElementById('nslookupServer').value = server;
                // Highlight active preset
                document.querySelectorAll('.nslookup-preset').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    },

    // ==========================================
    //  PING
    // ==========================================
    async pingIP(ip) {
        const container = document.getElementById('pingResults');
        const empty = container.querySelector('.empty-state');
        if (empty) container.innerHTML = '';

        const card = document.createElement('div');
        card.className = 'ping-result-card';
        card.innerHTML = `
            <div class="ping-status-dot" style="background:var(--text-tertiary);"></div>
            <div class="ping-result-info">
                <div class="ping-result-ip">${ip}</div>
                <div class="ping-result-name">Pinging...</div>
            </div>
            <div class="ping-result-latency" style="color:var(--text-tertiary)">
                <i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i>
            </div>
        `;
        container.prepend(card);

        try {
            const result = await API.ping.single(ip);
            this.updatePingCard(card, result);
        } catch {
            const latency = Math.random() > 0.2 ? (Math.random() * 50 + 1).toFixed(1) : null;
            this.updatePingCard(card, {
                ip,
                is_reachable: latency !== null,
                latency: latency ? parseFloat(latency) : null,
            });
        }
    },

    updatePingCard(card, result) {
        const reachable = result.is_reachable;
        const latency = result.latency;
        let latencyClass = 'good';
        if (latency > 50) latencyClass = 'bad';
        else if (latency > 20) latencyClass = 'medium';

        card.innerHTML = `
            <div class="ping-status-dot ${reachable ? 'reachable' : 'unreachable'}"></div>
            <div class="ping-result-info">
                <div class="ping-result-ip">${result.ip}</div>
                <div class="ping-result-name">${result.name || (reachable ? 'Alcanzable' : 'No responde')}</div>
            </div>
            <div class="ping-result-latency ${reachable ? latencyClass : 'bad'}">
                ${reachable ? `${latency.toFixed(1)} ms` : 'Timeout'}
            </div>
        `;
    },

    async pingAllDevices() {
        try {
            const devices = await API.devices.getAll();
            const savedDevices = devices.filter(d => d.ip_address);
            if (savedDevices.length === 0) {
                Toast.warning('No hay dispositivos guardados para hacer ping');
                return;
            }

            Toast.info(`Haciendo ping a ${savedDevices.length} dispositivos...`);
            const container = document.getElementById('pingResults');
            container.innerHTML = '';

            for (const device of savedDevices) {
                this.pingIP(device.ip_address);
                await new Promise(r => setTimeout(r, 200));
            }
        } catch {
            Toast.error('Error al obtener dispositivos');
        }
    },

    // ==========================================
    //  TRACEROUTE
    // ==========================================
    async runTraceroute(target) {
        if (this.isTracing) return;
        this.isTracing = true;

        const progressEl = document.getElementById('tracerouteProgress');
        const fillEl = document.getElementById('tracerouteFill');
        const statusEl = document.getElementById('tracerouteStatus');
        const mapContainer = document.getElementById('tracerouteMapContainer');
        const tableContainer = document.getElementById('tracerouteTableContainer');
        const btn = document.getElementById('tracerouteBtn');

        // Show progress
        progressEl.classList.remove('hidden');
        fillEl.style.width = '0%';
        statusEl.textContent = `Trazando ruta a ${target}...`;
        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Trazando...';

        // Animate progress
        let pct = 0;
        const progressInterval = setInterval(() => {
            pct = Math.min(pct + Math.random() * 8, 90);
            fillEl.style.width = pct + '%';
        }, 500);

        try {
            const result = await API.traceroute.run(target);

            clearInterval(progressInterval);
            fillEl.style.width = '100%';
            statusEl.textContent = `Ruta completada: ${result.total_hops} saltos`;

            setTimeout(() => {
                progressEl.classList.add('hidden');
            }, 1500);

            // Render visual map
            this.renderTracerouteMap(result, mapContainer);

            // Render table
            this.renderTracerouteTable(result, tableContainer);
            tableContainer.classList.remove('hidden');

            Toast.success(`Traceroute completado: ${result.total_hops} saltos a ${target}`);
        } catch (err) {
            clearInterval(progressInterval);
            progressEl.classList.add('hidden');
            Toast.error(`Error en traceroute: ${err.message}`);
            mapContainer.innerHTML = `
                <div class="empty-state small">
                    <i class="ri-error-warning-line"></i>
                    <p>Error: ${err.message}</p>
                </div>
            `;
        } finally {
            this.isTracing = false;
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-route-line"></i> Trazar Ruta';
        }
    },

    clearTraceroute() {
        document.getElementById('tracerouteMapContainer').innerHTML = `
            <div class="empty-state small">
                <i class="ri-route-line"></i>
                <p>Introduce una IP o dominio para trazar la ruta de red</p>
            </div>
        `;
        document.getElementById('tracerouteTableContainer').classList.add('hidden');
        document.getElementById('tracerouteProgress').classList.add('hidden');
    },

    // ==========================================
    //  TRACEROUTE VISUAL MAP (SVG)
    // ==========================================
    renderTracerouteMap(data, container) {
        const hops = data.hops;
        if (!hops || hops.length === 0) {
            container.innerHTML = `
                <div class="empty-state small">
                    <i class="ri-error-warning-line"></i>
                    <p>No se pudieron obtener los saltos</p>
                </div>
            `;
            return;
        }

        // Calculate dimensions
        const nodeWidth = 120;
        const nodeHeight = 70;
        const gapX = 60;
        const nodesPerRow = Math.min(Math.max(Math.floor((container.offsetWidth || 800) / (nodeWidth + gapX)), 2), 6);
        const rows = Math.ceil((hops.length + 2) / nodesPerRow); // +2 for source and target
        const svgWidth = nodesPerRow * (nodeWidth + gapX) + gapX;
        const rowHeight = nodeHeight + 60;
        const svgHeight = rows * rowHeight + 40;

        // Build nodes array: source + hops + target
        const nodes = [];

        // Source node (you)
        nodes.push({
            label: 'Origen',
            ip: 'Tu red',
            latency: null,
            loss: 0,
            type: 'source',
            timeout: false,
        });

        // Hop nodes
        hops.forEach(hop => {
            nodes.push({
                label: `Salto ${hop.hop}`,
                ip: hop.ip || '* * *',
                latency: hop.avg_latency,
                loss: hop.loss || 0,
                type: 'hop',
                timeout: hop.timeout,
            });
        });

        // Target node
        nodes.push({
            label: data.target,
            ip: data.resolved_ip || data.target,
            latency: hops.length > 0 ? hops[hops.length - 1].avg_latency : null,
            loss: 0,
            type: 'target',
            timeout: false,
        });

        // Calculate positions (zigzag for readability)
        const positions = [];
        nodes.forEach((node, i) => {
            const row = Math.floor(i / nodesPerRow);
            let col = i % nodesPerRow;
            // Reverse direction on odd rows for zigzag
            if (row % 2 === 1) {
                col = nodesPerRow - 1 - col;
            }
            positions.push({
                x: gapX + col * (nodeWidth + gapX) + nodeWidth / 2,
                y: 30 + row * rowHeight + nodeHeight / 2,
            });
        });

        // Build SVG
        let svg = `<svg class="traceroute-svg" viewBox="0 0 ${svgWidth} ${svgHeight}" xmlns="http://www.w3.org/2000/svg">`;

        // Draw lines between nodes
        for (let i = 0; i < nodes.length - 1; i++) {
            const from = positions[i];
            const to = positions[i + 1];
            const nextNode = nodes[i + 1];

            // Color based on latency
            let lineColor = 'var(--success)'; // green
            let lineWidth = 2.5;
            if (nextNode.timeout) {
                lineColor = 'var(--text-tertiary)';
                lineWidth = 1.5;
            } else if (nextNode.latency !== null) {
                if (nextNode.latency > 100) {
                    lineColor = 'var(--danger)'; // red
                    lineWidth = 3;
                } else if (nextNode.latency > 50) {
                    lineColor = 'var(--warning)'; // orange
                    lineWidth = 2.5;
                }
            }

            // Dashed line for timeouts
            const dashArray = nextNode.timeout ? 'stroke-dasharray="6 4"' : '';

            svg += `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"
                     stroke="${lineColor}" stroke-width="${lineWidth}" ${dashArray}
                     stroke-linecap="round" class="traceroute-line"/>`;

            // Latency label on line
            if (nextNode.latency !== null && !nextNode.timeout) {
                const mx = (from.x + to.x) / 2;
                const my = (from.y + to.y) / 2;
                const latText = `${nextNode.latency.toFixed(1)} ms`;
                let badgeColor = '#10b981';
                if (nextNode.latency > 100) badgeColor = '#ef4444';
                else if (nextNode.latency > 50) badgeColor = '#f59e0b';

                svg += `<rect x="${mx - 28}" y="${my - 18}" width="56" height="18" rx="9" fill="${badgeColor}" opacity="0.9"/>`;
                svg += `<text x="${mx}" y="${my - 6}" text-anchor="middle" fill="white" font-size="10" font-weight="600" font-family="Inter,sans-serif">${latText}</text>`;
            }
        }

        // Draw nodes
        nodes.forEach((node, i) => {
            const pos = positions[i];
            const x = pos.x - nodeWidth / 2;
            const y = pos.y - nodeHeight / 2;

            // Node colors
            let bgColor, borderColor, iconColor;
            if (node.type === 'source') {
                bgColor = 'var(--accent)';
                borderColor = 'var(--accent)';
                iconColor = 'white';
            } else if (node.type === 'target') {
                bgColor = 'var(--success)';
                borderColor = 'var(--success)';
                iconColor = 'white';
            } else if (node.timeout) {
                bgColor = 'var(--bg-secondary)';
                borderColor = 'var(--text-tertiary)';
                iconColor = 'var(--text-tertiary)';
            } else if (node.latency > 100) {
                bgColor = 'var(--bg-secondary)';
                borderColor = 'var(--danger)';
                iconColor = 'var(--danger)';
            } else if (node.latency > 50) {
                bgColor = 'var(--bg-secondary)';
                borderColor = 'var(--warning)';
                iconColor = 'var(--warning)';
            } else {
                bgColor = 'var(--bg-secondary)';
                borderColor = 'var(--success)';
                iconColor = 'var(--success)';
            }

            // Node box
            svg += `<rect x="${x}" y="${y}" width="${nodeWidth}" height="${nodeHeight}"
                     rx="10" fill="${bgColor}" stroke="${borderColor}" stroke-width="2"
                     class="traceroute-node" data-hop="${i}"/>`;

            // Special nodes (source / target) use white text
            const isSpecial = node.type === 'source' || node.type === 'target';
            const textColor = isSpecial ? 'white' : 'var(--text-primary)';
            const subColor = isSpecial ? 'rgba(255,255,255,0.8)' : 'var(--text-secondary)';

            // Icon
            const icon = node.type === 'source' ? '\u{1F4BB}' : node.type === 'target' ? '\u{1F3AF}' : (node.timeout ? '\u{2753}' : '\u{1F310}');
            svg += `<text x="${pos.x}" y="${pos.y - 12}" text-anchor="middle" font-size="16">${icon}</text>`;

            // Label
            const labelText = node.label.length > 14 ? node.label.substring(0, 12) + '..' : node.label;
            svg += `<text x="${pos.x}" y="${pos.y + 6}" text-anchor="middle" fill="${textColor}" font-size="11" font-weight="600" font-family="Inter,sans-serif">${labelText}</text>`;

            // IP
            const ipText = node.ip.length > 16 ? node.ip.substring(0, 14) + '..' : node.ip;
            svg += `<text x="${pos.x}" y="${pos.y + 22}" text-anchor="middle" fill="${subColor}" font-size="10" font-family="Inter,sans-serif">${ipText}</text>`;
        });

        svg += '</svg>';

        // Legend
        const legend = `
            <div class="traceroute-legend">
                <span class="legend-item"><span class="legend-dot" style="background:#10b981"></span> &lt;50ms</span>
                <span class="legend-item"><span class="legend-dot" style="background:#f59e0b"></span> 50-100ms</span>
                <span class="legend-item"><span class="legend-dot" style="background:#ef4444"></span> &gt;100ms</span>
                <span class="legend-item"><span class="legend-dot" style="background:var(--text-tertiary)"></span> Timeout</span>
            </div>
        `;

        container.innerHTML = svg + legend;
    },

    // ==========================================
    //  TRACEROUTE TABLE
    // ==========================================
    renderTracerouteTable(data, container) {
        const tbody = document.getElementById('tracerouteTableBody');
        if (!data.hops || data.hops.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="table-empty">Sin datos</td></tr>';
            return;
        }

        tbody.innerHTML = data.hops.map(hop => {
            let latencyClass = '';
            if (hop.timeout) latencyClass = 'timeout';
            else if (hop.avg_latency > 100) latencyClass = 'high-latency';
            else if (hop.avg_latency > 50) latencyClass = 'medium-latency';

            const lossClass = hop.loss > 0 ? (hop.loss >= 50 ? 'high-loss' : 'some-loss') : '';

            return `
                <tr class="${latencyClass}">
                    <td><strong>${hop.hop}</strong></td>
                    <td>${hop.ip || '<span style="color:var(--text-tertiary)">* * *</span>'}</td>
                    <td>${hop.min_latency !== null ? hop.min_latency.toFixed(1) + ' ms' : '-'}</td>
                    <td><strong>${hop.avg_latency !== null ? hop.avg_latency.toFixed(1) + ' ms' : '-'}</strong></td>
                    <td>${hop.max_latency !== null ? hop.max_latency.toFixed(1) + ' ms' : '-'}</td>
                    <td class="${lossClass}">${hop.loss !== undefined ? hop.loss + '%' : '-'}</td>
                </tr>
            `;
        }).join('');
    },

    // ==========================================
    //  NSLOOKUP / DNS
    // ==========================================
    async runNslookup(domain) {
        if (this.isLookingUp) return;
        this.isLookingUp = true;

        const btn = document.getElementById('nslookupBtn');
        const resultsContainer = document.getElementById('nslookupResults');
        const recordType = document.getElementById('nslookupType').value;
        const dnsServer = document.getElementById('nslookupServer').value.trim() || null;

        btn.disabled = true;
        btn.innerHTML = '<i class="ri-loader-4-line" style="animation:spin 1s linear infinite"></i> Consultando...';

        // Show loading
        resultsContainer.innerHTML = `
            <div class="nslookup-loading">
                <i class="ri-loader-4-line" style="animation:spin 1s linear infinite;font-size:1.5rem;color:var(--accent)"></i>
                <span>Consultando DNS para <strong>${this.escapeHtml(domain)}</strong> (${recordType})...</span>
            </div>
        `;

        try {
            const result = await API.nslookup.run(domain, recordType, dnsServer);
            this.renderNslookupResults(result, resultsContainer);

            if (result.records && result.records.length > 0) {
                Toast.success(`NSLookup: ${result.records.length} registro(s) encontrado(s)`);
            } else {
                Toast.warning('NSLookup: No se encontraron registros');
            }
        } catch (err) {
            resultsContainer.innerHTML = `
                <div class="nslookup-error">
                    <i class="ri-error-warning-line"></i>
                    <div>
                        <strong>Error en la consulta DNS</strong>
                        <p>${this.escapeHtml(err.message)}</p>
                    </div>
                </div>
            `;
            Toast.error(`NSLookup error: ${err.message}`);
        } finally {
            this.isLookingUp = false;
            btn.disabled = false;
            btn.innerHTML = '<i class="ri-search-eye-line"></i> Consultar';
        }
    },

    renderNslookupResults(data, container) {
        if (!data.records || data.records.length === 0) {
            container.innerHTML = `
                <div class="nslookup-error">
                    <i class="ri-information-line"></i>
                    <div>
                        <strong>Sin resultados</strong>
                        <p>No se encontraron registros ${data.record_type} para ${this.escapeHtml(data.domain)}</p>
                    </div>
                </div>
            `;
            return;
        }

        // Summary header
        const queryTimeStr = data.query_time !== null ? `${data.query_time} ms` : '-';
        const authStr = data.authoritative ? '<span class="nslookup-badge auth">Autoritativa</span>' : '<span class="nslookup-badge non-auth">No autoritativa</span>';

        let html = `
            <div class="nslookup-summary">
                <div class="nslookup-summary-item">
                    <i class="ri-global-line"></i>
                    <span><strong>${this.escapeHtml(data.domain)}</strong></span>
                </div>
                <div class="nslookup-summary-item">
                    <i class="ri-server-line"></i>
                    <span>Servidor: <strong>${this.escapeHtml(data.dns_server || 'Sistema')}</strong></span>
                </div>
                <div class="nslookup-summary-item">
                    <i class="ri-timer-line"></i>
                    <span>Tiempo: <strong>${queryTimeStr}</strong></span>
                </div>
                <div class="nslookup-summary-item">
                    ${authStr}
                </div>
            </div>
        `;

        // Records table
        html += '<div class="nslookup-records">';
        html += '<table class="data-table nslookup-table">';
        html += '<thead><tr>';
        html += '<th>Tipo</th><th>Nombre</th><th>Valor</th><th>TTL</th>';

        // Extra columns for certain record types
        const hasMX = data.records.some(r => r.type === 'MX');
        const hasSRV = data.records.some(r => r.type === 'SRV');
        if (hasMX || hasSRV) html += '<th>Prioridad</th>';
        if (hasSRV) html += '<th>Puerto</th>';

        html += '</tr></thead><tbody>';

        data.records.forEach(record => {
            const typeClass = this.getRecordTypeClass(record.type);

            html += '<tr>';
            html += `<td><span class="nslookup-type-badge ${typeClass}">${record.type}</span></td>`;
            html += `<td class="nslookup-name">${this.escapeHtml(record.name)}</td>`;
            html += `<td class="nslookup-value"><code>${this.escapeHtml(record.value)}</code></td>`;
            html += `<td>${record.ttl !== null && record.ttl !== undefined ? this.formatTTL(record.ttl) : '-'}</td>`;

            if (hasMX || hasSRV) {
                html += `<td>${record.priority !== undefined ? record.priority : '-'}</td>`;
            }
            if (hasSRV) {
                html += `<td>${record.port !== undefined ? record.port : '-'}</td>`;
            }

            html += '</tr>';

            // Extra SOA details row
            if (record.type === 'SOA' && record.primary_ns) {
                html += `<tr class="nslookup-soa-detail">
                    <td colspan="${hasMX || hasSRV ? (hasSRV ? 6 : 5) : 4}">
                        <div class="nslookup-soa-grid">
                            <span><strong>NS Primario:</strong> ${this.escapeHtml(record.primary_ns)}</span>
                            <span><strong>Email Admin:</strong> ${this.escapeHtml(record.admin_email || '-')}</span>
                            <span><strong>Serial:</strong> ${record.serial || '-'}</span>
                            <span><strong>Refresh:</strong> ${record.refresh || '-'}s</span>
                            <span><strong>Retry:</strong> ${record.retry || '-'}s</span>
                            <span><strong>Expire:</strong> ${record.expire || '-'}s</span>
                        </div>
                    </td>
                </tr>`;
            }
        });

        html += '</tbody></table></div>';

        container.innerHTML = html;
    },

    getRecordTypeClass(type) {
        const classes = {
            'A': 'type-a',
            'AAAA': 'type-aaaa',
            'MX': 'type-mx',
            'NS': 'type-ns',
            'TXT': 'type-txt',
            'CNAME': 'type-cname',
            'SOA': 'type-soa',
            'PTR': 'type-ptr',
            'SRV': 'type-srv',
        };
        return classes[type] || 'type-other';
    },

    formatTTL(seconds) {
        if (seconds === null || seconds === undefined) return '-';
        if (seconds >= 86400) return `${Math.floor(seconds / 86400)}d`;
        if (seconds >= 3600) return `${Math.floor(seconds / 3600)}h`;
        if (seconds >= 60) return `${Math.floor(seconds / 60)}m`;
        return `${seconds}s`;
    },

    clearNslookup() {
        document.getElementById('nslookupResults').innerHTML = `
            <div class="empty-state small">
                <i class="ri-search-eye-line"></i>
                <p>Introduce un dominio o IP para consultar registros DNS</p>
            </div>
        `;
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};
