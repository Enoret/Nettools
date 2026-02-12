/* =========================================
   NetTools - Speed Test Page
   ========================================= */

const SpeedTestPage = {
    chartsInitialized: false,
    gaugeDownload: null,
    gaugeUpload: null,
    chartHistory: null,
    chartPing: null,
    chartHourly: null,
    isTesting: false,
    currentRange: '24h',
    _refreshInterval: null,
    _lastResultCount: 0,

    init() {
        if (!this.chartsInitialized) {
            this.initGauges();
            this.initCharts();
            this.bindEvents();
            this.loadServers();
            this.chartsInitialized = true;
        }
        this.loadData();
        this.loadAutoTestStatus();
        this.startAutoRefresh();
    },

    destroy() {
        this.stopAutoRefresh();
    },

    startAutoRefresh() {
        this.stopAutoRefresh();
        // Poll every 30 seconds to detect background speed test results
        this._refreshInterval = setInterval(() => this._autoRefreshTick(), 30000);
    },

    stopAutoRefresh() {
        if (this._refreshInterval) {
            clearInterval(this._refreshInterval);
            this._refreshInterval = null;
        }
    },

    async _autoRefreshTick() {
        // Only refresh if this page is currently visible and not mid-test
        if (typeof Router !== 'undefined' && Router.currentPage !== 'speed') return;
        if (this.isTesting) return;

        try {
            const stats = await API.speedtest.getStats();
            if (stats && stats.total_tests !== this._lastResultCount) {
                this._lastResultCount = stats.total_tests;
                this.loadData();
            }
            this.loadAutoTestStatus();
        } catch {
            // Backend not available, skip
        }
    },

    async loadAutoTestStatus() {
        const indicator = document.getElementById('autoStatusIndicator');
        const text = document.getElementById('autoStatusText');
        if (!indicator || !text) return;

        try {
            const settings = await API.settings.getAll();
            const testStatus = await API.speedtest.getStatus();

            if (testStatus && testStatus.in_progress) {
                indicator.className = 'auto-status-indicator active';
                indicator.querySelector('i').className = 'ri-speed-up-line spinning';
                text.textContent = 'Speed test en curso...';
            } else if (settings.auto_speed_test) {
                const freq = settings.speed_test_frequency || '60';
                indicator.className = 'auto-status-indicator active';
                indicator.querySelector('i').className = 'ri-refresh-line';
                text.textContent = `Auto-test (cada ${freq} min)`;
            } else {
                indicator.className = 'auto-status-indicator disabled';
                indicator.querySelector('i').className = 'ri-stop-circle-line';
                text.textContent = 'Auto-test off';
            }
        } catch {
            indicator.className = 'auto-status-indicator disabled';
            indicator.querySelector('i').className = 'ri-wifi-off-line';
            text.textContent = 'Sin backend';
        }
    },

    bindEvents() {
        document.getElementById('startTestBtn').addEventListener('click', () => {
            if (!this.isTesting) this.runTest();
        });

        document.getElementById('refreshServersBtn').addEventListener('click', () => this.loadServers());

        // Chart filters
        document.querySelectorAll('#page-speed .chart-filters .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#page-speed .chart-filters .filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentRange = btn.dataset.range;
                this.loadData();
            });
        });
    },

    // --- Gauges ---
    initGauges() {
        const colors = Theme.getColors();

        const gaugeOptions = (color, max = 500) => ({
            chart: { type: 'radialBar', height: 120, sparkline: { enabled: true } },
            plotOptions: {
                radialBar: {
                    startAngle: -120,
                    endAngle: 120,
                    hollow: { size: '60%' },
                    track: {
                        background: colors.gaugeTrack,
                        strokeWidth: '100%',
                    },
                    dataLabels: { show: false },
                },
            },
            fill: {
                type: 'gradient',
                gradient: {
                    shade: 'dark',
                    type: 'horizontal',
                    gradientToColors: [color],
                    stops: [0, 100],
                },
            },
            colors: [color],
            series: [0],
            stroke: { lineCap: 'round' },
        });

        this.gaugeDownload = new ApexCharts(
            document.getElementById('gaugeDownload'),
            gaugeOptions(colors.gaugeDownload)
        );
        this.gaugeDownload.render();

        this.gaugeUpload = new ApexCharts(
            document.getElementById('gaugeUpload'),
            gaugeOptions(colors.gaugeUpload)
        );
        this.gaugeUpload.render();
    },

    updateGauge(gauge, value, max = 500) {
        const pct = Math.min((value / max) * 100, 100);
        gauge.updateSeries([Math.round(pct)]);
    },

    // --- Charts ---
    initCharts() {
        const colors = Theme.getColors();

        // Speed History Chart
        this.chartHistory = new ApexCharts(document.getElementById('chartSpeedHistory'), {
            chart: {
                type: 'area',
                height: 280,
                toolbar: { show: false },
                zoom: { enabled: false },
                fontFamily: 'Inter, sans-serif',
                background: 'transparent',
                animations: { enabled: true, easing: 'easeinout', speed: 600 },
            },
            series: [
                { name: 'Descarga', data: [] },
                { name: 'Subida', data: [] },
            ],
            colors: [colors.download, colors.upload],
            fill: {
                type: 'gradient',
                gradient: { opacityFrom: 0.35, opacityTo: 0.05, stops: [0, 95] },
            },
            stroke: { curve: 'smooth', width: 2.5 },
            xaxis: {
                type: 'datetime',
                labels: { style: { colors: colors.chartText, fontSize: '11px' } },
                axisBorder: { show: false },
                axisTicks: { show: false },
            },
            yaxis: {
                labels: {
                    style: { colors: colors.chartText, fontSize: '11px' },
                    formatter: (v) => `${v.toFixed(0)} Mbps`,
                },
            },
            grid: { borderColor: colors.grid, strokeDashArray: 4, padding: { left: 8, right: 8 } },
            legend: {
                position: 'top',
                horizontalAlign: 'right',
                labels: { colors: colors.textSecondary },
                markers: { radius: 3 },
            },
            tooltip: {
                theme: Theme.getCurrent(),
                x: { format: 'dd MMM HH:mm' },
                y: { formatter: (v) => `${v.toFixed(1)} Mbps` },
            },
            dataLabels: { enabled: false },
        });
        this.chartHistory.render();

        // Ping History Chart
        this.chartPing = new ApexCharts(document.getElementById('chartPingHistory'), {
            chart: {
                type: 'line',
                height: 280,
                toolbar: { show: false },
                zoom: { enabled: false },
                fontFamily: 'Inter, sans-serif',
                background: 'transparent',
            },
            series: [
                { name: 'Ping', data: [] },
                { name: 'Jitter', data: [] },
            ],
            colors: [colors.ping, colors.jitter],
            stroke: { curve: 'smooth', width: 2 },
            xaxis: {
                type: 'datetime',
                labels: { style: { colors: colors.chartText, fontSize: '11px' } },
                axisBorder: { show: false },
                axisTicks: { show: false },
            },
            yaxis: {
                labels: {
                    style: { colors: colors.chartText, fontSize: '11px' },
                    formatter: (v) => `${v.toFixed(0)} ms`,
                },
            },
            grid: { borderColor: colors.grid, strokeDashArray: 4 },
            legend: {
                position: 'top',
                horizontalAlign: 'right',
                labels: { colors: colors.textSecondary },
                markers: { radius: 3 },
            },
            tooltip: {
                theme: Theme.getCurrent(),
                x: { format: 'dd MMM HH:mm' },
                y: { formatter: (v) => `${v.toFixed(1)} ms` },
            },
            dataLabels: { enabled: false },
        });
        this.chartPing.render();

        // Hourly Average Chart
        this.chartHourly = new ApexCharts(document.getElementById('chartHourlyAvg'), {
            chart: {
                type: 'bar',
                height: 280,
                toolbar: { show: false },
                zoom: { enabled: false },
                fontFamily: 'Inter, sans-serif',
                background: 'transparent',
            },
            series: [
                { name: 'Descarga', data: [] },
                { name: 'Subida', data: [] },
            ],
            colors: [colors.download, colors.upload],
            plotOptions: {
                bar: { borderRadius: 4, columnWidth: '60%', grouped: true },
            },
            xaxis: {
                categories: [],
                labels: { style: { colors: colors.chartText, fontSize: '11px' } },
                axisBorder: { show: false },
                axisTicks: { show: false },
            },
            yaxis: {
                labels: {
                    style: { colors: colors.chartText, fontSize: '11px' },
                    formatter: (v) => `${Math.round(v)} Mbps`,
                },
            },
            grid: { borderColor: colors.grid, strokeDashArray: 4 },
            legend: {
                position: 'top',
                horizontalAlign: 'right',
                labels: { colors: colors.textSecondary },
                markers: { radius: 3 },
            },
            tooltip: {
                theme: Theme.getCurrent(),
                y: { formatter: (v) => `${Number(v).toFixed(1)} Mbps` },
            },
            dataLabels: { enabled: false },
        });
        this.chartHourly.render();
    },

    updateChartTheme() {
        const colors = Theme.getColors();
        const themeOpts = {
            tooltip: { theme: Theme.getCurrent() },
            xaxis: { labels: { style: { colors: colors.chartText } } },
            yaxis: { labels: { style: { colors: colors.chartText } } },
            grid: { borderColor: colors.grid },
            legend: { labels: { colors: colors.textSecondary } },
        };

        if (this.chartHistory) {
            this.chartHistory.updateOptions({
                ...themeOpts,
                colors: [colors.download, colors.upload],
            });
        }
        if (this.chartPing) {
            this.chartPing.updateOptions({
                ...themeOpts,
                colors: [colors.ping, colors.jitter],
            });
        }
        if (this.chartHourly) {
            this.chartHourly.updateOptions({
                ...themeOpts,
                colors: [colors.download, colors.upload],
            });
        }
    },

    // --- Load Data ---
    async loadData() {
        try {
            const [results, stats] = await Promise.all([
                API.speedtest.getResults({ range: this.currentRange }),
                API.speedtest.getStats(),
            ]);
            this.updateDashboard(results, stats);
        } catch (err) {
            // Use demo data if API not available
            this.loadDemoData();
        }
    },

    updateDashboard(results, stats) {
        // Stats cards
        if (stats) {
            document.getElementById('bestDownload').textContent = `${Utils.formatSpeed(stats.best_download)} Mbps`;
            document.getElementById('bestUpload').textContent = `${Utils.formatSpeed(stats.best_upload)} Mbps`;
            document.getElementById('bestPing').textContent = `${Utils.formatPing(stats.best_ping)} ms`;
            document.getElementById('totalTests').textContent = stats.total_tests || 0;
            this._lastResultCount = stats.total_tests || 0;
        }

        if (results && results.length > 0) {
            // Update gauges with latest
            const latest = results[results.length - 1];
            this.updateGauge(this.gaugeDownload, latest.download_speed);
            this.updateGauge(this.gaugeUpload, latest.upload_speed);
            document.getElementById('downloadValue').textContent = Utils.formatSpeed(latest.download_speed);
            document.getElementById('uploadValue').textContent = Utils.formatSpeed(latest.upload_speed);
            document.getElementById('livePing').textContent = `${Utils.formatPing(latest.ping)} ms`;
            document.getElementById('liveJitter').textContent = `${Utils.formatPing(latest.jitter)} ms`;
            document.getElementById('liveServer').textContent = latest.server_name || '--';
            document.getElementById('liveISP').textContent = latest.isp || '--';

            // Speed history chart
            this.chartHistory.updateSeries([
                { name: 'Descarga', data: results.map(r => ({ x: new Date(r.timestamp).getTime(), y: r.download_speed })) },
                { name: 'Subida', data: results.map(r => ({ x: new Date(r.timestamp).getTime(), y: r.upload_speed })) },
            ]);

            // Ping history chart
            this.chartPing.updateSeries([
                { name: 'Ping', data: results.map(r => ({ x: new Date(r.timestamp).getTime(), y: r.ping })) },
                { name: 'Jitter', data: results.map(r => ({ x: new Date(r.timestamp).getTime(), y: r.jitter || 0 })) },
            ]);

            // Hourly averages
            this.updateHourlyChart(results);

            // Recent tests table
            this.updateRecentTable(results.slice(-20).reverse());
        }
    },

    updateHourlyChart(results) {
        const hourly = {};
        results.forEach(r => {
            const h = new Date(r.timestamp).getHours();
            const label = `${String(h).padStart(2, '0')}:00`;
            if (!hourly[label]) {
                hourly[label] = { dl: [], ul: [] };
            }
            hourly[label].dl.push(r.download_speed);
            hourly[label].ul.push(r.upload_speed);
        });

        const categories = Object.keys(hourly).sort();
        const dlAvg = categories.map(h => Math.round(hourly[h].dl.reduce((a, b) => a + b, 0) / hourly[h].dl.length * 100) / 100);
        const ulAvg = categories.map(h => Math.round(hourly[h].ul.reduce((a, b) => a + b, 0) / hourly[h].ul.length * 100) / 100);

        this.chartHourly.updateOptions({ xaxis: { categories } });
        this.chartHourly.updateSeries([
            { name: 'Descarga', data: dlAvg },
            { name: 'Subida', data: ulAvg },
        ]);
    },

    updateRecentTable(tests) {
        const tbody = document.getElementById('recentTestsBody');
        if (!tests.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No hay tests registrados</td></tr>';
            return;
        }
        tbody.innerHTML = tests.map(t => `
            <tr>
                <td>${Utils.formatDate(t.timestamp)}</td>
                <td><strong style="color:var(--download-color)">${Utils.formatSpeed(t.download_speed)} Mbps</strong></td>
                <td><strong style="color:var(--upload-color)">${Utils.formatSpeed(t.upload_speed)} Mbps</strong></td>
                <td>${Utils.formatPing(t.ping)} ms</td>
                <td>${Utils.formatPing(t.jitter)} ms</td>
                <td>${t.server_name || '--'}</td>
            </tr>
        `).join('');
    },

    // --- Load Servers ---
    async loadServers() {
        const select = document.getElementById('serverSelect');
        const refreshBtn = document.getElementById('refreshServersBtn');
        try {
            refreshBtn.disabled = true;
            refreshBtn.querySelector('i').style.animation = 'spin 1s linear infinite';

            const servers = await API.speedtest.getServers();
            // Keep the default option
            select.innerHTML = '<option value="">Automatico (mejor servidor)</option>';
            if (servers && servers.length > 0) {
                servers.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s.id;
                    opt.textContent = `${s.sponsor} - ${s.name}, ${s.country} (${s.d ? s.d.toFixed(0) + ' km' : ''})`;
                    select.appendChild(opt);
                });
            }
        } catch {
            // If backend unavailable, just keep default option
            select.innerHTML = '<option value="">Automatico (mejor servidor)</option>';
        } finally {
            refreshBtn.disabled = false;
            refreshBtn.querySelector('i').style.animation = '';
        }
    },

    // --- Run Speed Test ---
    async runTest() {
        this.isTesting = true;
        const btn = document.getElementById('startTestBtn');
        const icon = document.getElementById('startTestIcon');
        const text = document.getElementById('startTestText');
        const phase = document.getElementById('testPhase');
        const progress = document.getElementById('testProgress');

        btn.classList.add('testing');
        icon.className = 'ri-loader-4-line';
        icon.style.animation = 'spin 1s linear infinite';
        text.textContent = 'STOP';

        const circumference = 2 * Math.PI * 54;
        progress.style.strokeDasharray = circumference;

        const phases = [
            { text: 'Conectando con servidor...', pct: 5 },
            { text: 'Midiendo latencia...', pct: 15 },
            { text: 'Test de descarga...', pct: 50 },
            { text: 'Test de subida...', pct: 85 },
            { text: 'Finalizando...', pct: 100 },
        ];

        try {
            // Simulate phases for UI while waiting for backend
            let phaseIdx = 0;
            const phaseInterval = setInterval(() => {
                if (phaseIdx < phases.length) {
                    phase.textContent = phases[phaseIdx].text;
                    const offset = circumference - (phases[phaseIdx].pct / 100) * circumference;
                    progress.style.strokeDashoffset = offset;
                    phaseIdx++;
                }
            }, 3000);

            phase.textContent = phases[0].text;

            // Get selected server (if any)
            const serverSelect = document.getElementById('serverSelect');
            const serverId = serverSelect.value || null;

            const result = await API.speedtest.run(serverId);

            clearInterval(phaseInterval);
            progress.style.strokeDashoffset = 0;
            phase.textContent = 'Test completado!';

            // Update values
            document.getElementById('downloadValue').textContent = Utils.formatSpeed(result.download_speed);
            document.getElementById('uploadValue').textContent = Utils.formatSpeed(result.upload_speed);
            this.updateGauge(this.gaugeDownload, result.download_speed);
            this.updateGauge(this.gaugeUpload, result.upload_speed);
            document.getElementById('livePing').textContent = `${Utils.formatPing(result.ping)} ms`;
            document.getElementById('liveJitter').textContent = `${Utils.formatPing(result.jitter)} ms`;
            document.getElementById('liveServer').textContent = result.server_name || '--';
            document.getElementById('liveISP').textContent = result.isp || '--';

            Toast.success(`Test completado: ${Utils.formatSpeed(result.download_speed)} Mbps / ${Utils.formatSpeed(result.upload_speed)} Mbps`);

            // Reload all data
            this.loadData();
        } catch (err) {
            phase.textContent = 'Error en el test';
            Toast.error(`Error: ${err.message}`);
            // Show demo result
            this.simulateTest(phases, circumference, progress, phase);
        } finally {
            setTimeout(() => {
                this.isTesting = false;
                btn.classList.remove('testing');
                icon.className = 'ri-play-fill';
                icon.style.animation = '';
                text.textContent = 'INICIAR';
                progress.style.strokeDashoffset = circumference;
                phase.textContent = 'Listo para iniciar';
            }, 3000);
        }
    },

    // Demo simulation for when backend is not available
    async simulateTest(phases, circumference, progress, phase) {
        for (let i = 0; i < phases.length; i++) {
            phase.textContent = phases[i].text;
            const offset = circumference - (phases[i].pct / 100) * circumference;
            progress.style.strokeDashoffset = offset;

            // Simulate speed values during test
            if (i === 2) {
                const dl = (Math.random() * 200 + 50).toFixed(1);
                document.getElementById('downloadValue').textContent = dl;
                this.updateGauge(this.gaugeDownload, parseFloat(dl));
            }
            if (i === 3) {
                const ul = (Math.random() * 100 + 20).toFixed(1);
                document.getElementById('uploadValue').textContent = ul;
                this.updateGauge(this.gaugeUpload, parseFloat(ul));
            }

            await new Promise(r => setTimeout(r, 2000));
        }

        const ping = (Math.random() * 20 + 5).toFixed(1);
        const jitter = (Math.random() * 5 + 1).toFixed(1);
        document.getElementById('livePing').textContent = `${ping} ms`;
        document.getElementById('liveJitter').textContent = `${jitter} ms`;
        document.getElementById('liveServer').textContent = 'Demo Server';
        document.getElementById('liveISP').textContent = 'Local ISP';

        phase.textContent = 'Test completado! (Demo)';
    },

    // --- Demo Data ---
    loadDemoData() {
        const now = Date.now();
        const results = [];
        for (let i = 23; i >= 0; i--) {
            results.push({
                timestamp: new Date(now - i * 3600000).toISOString(),
                download_speed: 80 + Math.random() * 120,
                upload_speed: 30 + Math.random() * 60,
                ping: 8 + Math.random() * 25,
                jitter: 1 + Math.random() * 8,
                server_name: 'Servidor Local',
                isp: 'ISP Demo',
            });
        }

        const stats = {
            best_download: Math.max(...results.map(r => r.download_speed)),
            best_upload: Math.max(...results.map(r => r.upload_speed)),
            best_ping: Math.min(...results.map(r => r.ping)),
            total_tests: results.length,
        };

        this.updateDashboard(results, stats);
    },

};

// CSS animation for spinner
const styleEl = document.createElement('style');
styleEl.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
document.head.appendChild(styleEl);
