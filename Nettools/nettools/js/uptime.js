/* =========================================
   NetTools - Internet availability card (Net Speed page)
   Data from the outage monitor (/api/connectivity).
   ========================================= */

const UptimeCard = {
    range: '24h',
    initialized: false,

    init() {
        if (!this.initialized) {
            document.querySelectorAll('#uptimeRange button').forEach(btn => {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('#uptimeRange button').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.range = btn.dataset.range;
                    this.load();
                });
            });
            this.initialized = true;
        }
        this.load();
    },

    fmtDuration(seconds) {
        seconds = Math.max(0, Math.round(seconds || 0));
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h) return `${h} h ${m} min`;
        if (m) return `${m} min${m < 10 && s ? ` ${s} s` : ''}`;
        return `${s} s`;
    },

    // Server timestamps are wall-clock times of the NetTools time zone
    // ('YYYY-MM-DD HH:MM:SS'): handle them as UTC on both sides so buckets
    // line up and they are displayed exactly as stored.
    ms(ts) {
        return Date.parse(ts.replace(' ', 'T') + 'Z');
    },

    fmtTime(ts, withDate) {
        if (!ts) return '';
        const v = typeof ts === 'number' ? ts : this.ms(ts);
        if (isNaN(v)) return ts;
        const d = new Date(v);
        return withDate
            ? d.toLocaleString(I18N.locale, { timeZone: 'UTC', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
            : d.toLocaleTimeString(I18N.locale, { timeZone: 'UTC', hour: '2-digit', minute: '2-digit' });
    },

    async load() {
        let data;
        try {
            data = await API.connectivity.get(this.range);
        } catch (e) {
            return;
        }
        this.render(data);
    },

    render(data) {
        const status = document.getElementById('uptimeStatus');
        const dot = status.querySelector('.status-dot');
        const text = status.querySelector('span:last-child');
        const cur = data.current_outage;
        const last = data.last_check;
        if (!last) {
            dot.className = 'status-dot';
            text.textContent = I18N.t('Sin datos todavia (la primera comprobacion tarda un minuto)');
        } else if (cur) {
            dot.className = 'status-dot';
            text.textContent = I18N.t(cur.kind === 'gateway' ? 'Router sin respuesta desde las {t}' : 'Sin Internet desde las {t}',
                { t: this.fmtTime(cur.start) });
        } else if (!last.internet_ok) {
            dot.className = 'status-dot warning';
            text.textContent = I18N.t('Fallo en la ultima comprobacion');
        } else {
            dot.className = 'status-dot online';
            text.textContent = last.latency != null
                ? I18N.t('Internet OK · {ms} ms', { ms: Math.round(last.latency) })
                : I18N.t('Internet OK');
        }

        document.getElementById('uptimePct').textContent = data.uptime == null ? '--' : `${data.uptime.toLocaleString(I18N.locale, { maximumFractionDigits: 2 })}%`;
        document.getElementById('uptimeOutages').textContent = data.outage_count;
        let downtime = data.downtime || 0;
        if (cur) downtime += (this.ms(data.now) - this.ms(cur.start)) / 1000;
        document.getElementById('uptimeDowntime').textContent = this.fmtDuration(downtime);

        // Timeline: one segment per bucket over the whole range (gaps = no data)
        const bucketMs = data.bucket_seconds * 1000;
        const first = Math.floor(this.ms(data.since) / bucketMs);
        const lastKey = Math.floor(this.ms(data.now) / bucketMs);
        const byKey = {};
        (data.buckets || []).forEach(b => { byKey[Math.floor(this.ms(b.time) / bucketMs)] = b; });
        const segs = [];
        for (let key = first; key <= lastKey; key++) {
            const b = byKey[key];
            let cls = 'nodata', tip = I18N.t('Sin datos');
            if (b && b.total) {
                const pct = Math.round(b.internet_ok / b.total * 1000) / 10;
                cls = b.internet_ok === b.total ? 'ok' : (b.gateway_down ? 'router' : 'down');
                tip = `${pct}%` + (b.latency ? ` · ${Math.round(b.latency)} ms` : '');
            }
            segs.push(`<span class="seg ${cls}" title="${this.fmtTime(key * bucketMs, this.range !== '24h')} · ${tip}"></span>`);
        }
        document.getElementById('uptimeBar').innerHTML = segs.join('');
        document.getElementById('uptimeFrom').textContent = this.fmtTime(data.since, true);

        const events = (data.outages || []).slice(0, 6);
        document.getElementById('uptimeEvents').innerHTML = events.length
            ? events.map(o => `
                <div class="uptime-event">
                    <i class="${o.kind === 'gateway' ? 'ri-router-line' : 'ri-global-line'}"></i>
                    <span class="ev-kind">${I18N.t(o.kind === 'gateway' ? 'Router sin respuesta' : 'Sin Internet')}</span>
                    <span class="ev-time">${this.fmtTime(o.start, true)}${o.end ? ' → ' + this.fmtTime(o.end) : ''}</span>
                    <span class="ev-dur">${o.end ? this.fmtDuration(o.duration) : I18N.t('en curso')}</span>
                </div>`).join('')
            : `<div class="uptime-noevents"><i class="ri-checkbox-circle-line"></i> ${I18N.t('Sin cortes en este periodo')}</div>`;
    },
};
