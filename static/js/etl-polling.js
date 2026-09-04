/**
 * etl-polling.js — Dashboard ETL: polling inteligente, toasts y KPIs.
 *
 * Intervalos ajustables:
 *   FAST_MS  — cada 4 s cuando hay jobs queued o running
 *   IDLE_MS  — cada 20 s cuando no hay actividad
 */

const EtlPolling = (function () {
    'use strict';

    // ── Configuración ────────────────────────────────────────────────────────
    const FAST_MS = 4000;
    const IDLE_MS = 20000;
    const RUNS_API = '/api/etl/runs';
    const KPIS_API = '/api/etl/kpis';

    // ── Estado interno ───────────────────────────────────────────────────────
    let pollTimer = null;
    let countdown = 0;
    let countdownTimer = null;
    let prevStates = {};       // { job_id: last_status }
    let pageType = null;       // 'etl' | 'load' | 'runs'
    let jobsApi = null;        // URL de la API de jobs para esta página
    let runApi = null;         // Base URL para POST /run
    let lastParamsApi = null;  // Base URL para GET /last-params
    let useRunModal = false;
    let runsTable = null;      // instancia DataTables para /etl/runs
    let isPolling = false;
    let runParamsModal = null;
    let currentJobMetadata = null;  // Guardar metadatos del job actual

    // ── Definición de parámetros conocidos ────────────────────────────────────
    const PARAM_DEFINITIONS = {
        'curve_paths': {
            label: 'Rutas de curvas Tika',
            placeholder: 'Una ruta por línea',
            type: 'text',
            multiline: true,
            format: (v) => v
                ? String(v)
                    .replace(/\r\n/g, '\n')
                    .replace(/\r/g, '\n')
                    .split(/\n|;/)
                    .map(x => x.trim())
                    .filter(Boolean)
                : [],
        },
        'curve_years': {
            label: 'Años de curvas',
            placeholder: 'Ejemplo: 2026, 2027',
            type: 'text',
            format: (v) => v ? String(v).split(',').map(x => parseInt(x.trim(), 10)).filter(x => !Number.isNaN(x)) : [],
        },
        'modelos_tika': {
            label: 'Modelos Tika (separados por coma)',
            placeholder: 'Ejemplo: 161, 328, 485',
            type: 'text',
            format: (v) => v ? String(v).split(',').map(x => parseInt(x.trim(), 10)).filter(x => !Number.isNaN(x)) : [],
        },
        'muestras': {
            label: 'Número de muestras/lonas',
            placeholder: 'Defecto: 5',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'tallos_min': {
            label: 'Tallos mínimos',
            placeholder: 'Defecto: 1000',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'lonas_semana': {
            label: 'Capacidad de lonas por semana',
            placeholder: 'Defecto: 65',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'modelo_tika': {
            label: 'Modelo Tika',
            placeholder: 'Ejemplo: 485',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'semana_actual': {
            label: 'Semana actual (YYWW)',
            placeholder: 'Ejemplo: 2613',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'semana_inicio': {
            label: 'Semana inicio (YYWW)',
            placeholder: 'Ejemplo: 2527',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'semana_fin': {
            label: 'Semana fin (YYWW)',
            placeholder: 'Ejemplo: 2620',
            type: 'number',
            format: (v) => v ? parseInt(v) : null,
        },
        'fecha_inicio_incremental': {
            label: 'Fecha inicio incremental',
            placeholder: 'Ejemplo: 2025-12-29',
            type: 'date',
            format: (v) => v ? String(v).trim() : null,
        },
        'fecha_inicio_exportacion': {
            label: 'Fecha inicio exportacion',
            placeholder: 'Ejemplo: 2025-12-29',
            type: 'date',
            format: (v) => v ? String(v).trim() : null,
        },
    };

    // ── Helpers de badge ─────────────────────────────────────────────────────
    const BADGE_HTML = {
        success: '<span class="badge bg-success"><i class="fas fa-check me-1"></i>success</span>',
        failed:  '<span class="badge bg-danger"><i class="fas fa-xmark me-1"></i>failed</span>',
        running: '<span class="badge bg-primary"><span class="spinner-grow spinner-grow-sm me-1" role="status"></span>running</span>',
        queued:  '<span class="badge bg-warning text-dark"><i class="fas fa-clock me-1"></i>queued</span>',
        '':      '<span class="badge bg-secondary">sin ejecuciones</span>',
    };

    function badgeHtml(status) {
        return BADGE_HTML[status] || BADGE_HTML[''];
    }

    // ── Toast ────────────────────────────────────────────────────────────────
    function showToast(message, type) {
        // type: 'success' | 'danger' | 'warning' | 'info' | 'primary'
        const container = document.getElementById('toast-container');
        if (!container) return;

        const id = 'toast-' + Date.now();
        const bgClass = {
            success: 'text-bg-success',
            danger:  'text-bg-danger',
            warning: 'text-bg-warning',
            info:    'text-bg-info',
            primary: 'text-bg-primary',
        }[type] || 'text-bg-secondary';

        const icons = {
            success: 'fa-circle-check',
            danger:  'fa-circle-xmark',
            warning: 'fa-triangle-exclamation',
            info:    'fa-circle-info',
            primary: 'fa-circle-info',
        };
        const icon = icons[type] || 'fa-circle-info';

        const html = `
            <div id="${id}" class="toast align-items-center ${bgClass} border-0 shadow" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas ${icon} me-2"></i>${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Cerrar"></button>
                </div>
            </div>`;

        container.insertAdjacentHTML('beforeend', html);
        const el = document.getElementById(id);
        const toast = new bootstrap.Toast(el, { delay: 5000 });
        toast.show();
        el.addEventListener('hidden.bs.toast', () => el.remove());
    }

    // ── Actualizar KPIs ──────────────────────────────────────────────────────
    function updateKPIs(kpis) {
        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        set('kpi-queued',  kpis.queued);
        set('kpi-running', kpis.running);
        set('kpi-success', kpis.success);
        set('kpi-failed',  kpis.failed);

        // Pulsar visualmente la card running si hay jobs en curso
        const runningCard = document.querySelector('.kpi-card.kpi-running');
        if (runningCard) {
            runningCard.classList.toggle('kpi-active', kpis.running > 0);
        }
    }

    function applyDependencyFilter(selectedGroup, searchTerm) {
        const rows = document.querySelectorAll('.job-row');
        const query = (searchTerm || '').trim().toLowerCase();

        rows.forEach(function (row) {
            const group = (row.dataset.dependencyGroup || 'Otros');
            const groupMatches = selectedGroup === 'Todos' || group === selectedGroup;
            const searchableText = (row.textContent || '').toLowerCase();
            const searchMatches = !query || searchableText.includes(query);
            row.style.display = (groupMatches && searchMatches) ? '' : 'none';
        });
    }

    // ── Actualizar filas de la tabla de jobs ──────────────────────────────────
    function updateJobRows(jobs) {
        jobs.forEach(function (job) {
            const row = document.querySelector('tr[data-job-id="' + job.job_id + '"]');
            if (!row) return;

            if (job.dependency_group) {
                row.dataset.dependencyGroup = job.dependency_group;
            }

            const newStatus = job.last_status || '';
            const oldStatus = prevStates[job.job_id];

            // Actualizar badge de estado
            const badge = row.querySelector('.status-badge');
            if (badge && badge.dataset.status !== newStatus) {
                badge.innerHTML = badgeHtml(newStatus);
                badge.dataset.status = newStatus;
            }

            // Actualizar fecha última ejecución
            const lastStarted = row.querySelector('.last-started');
            if (lastStarted && job.last_started_at) {
                lastStarted.textContent = formatDate(job.last_started_at);
            }

            // Detectar cambio de estado → toast
            if (oldStatus !== undefined && oldStatus !== newStatus) {
                const label = job.name || job.job_id;
                if (newStatus === 'success') {
                    showToast('<strong>' + label + '</strong> completó con éxito.', 'success');
                } else if (newStatus === 'failed') {
                    showToast('<strong>' + label + '</strong> falló.', 'danger');
                } else if (newStatus === 'running') {
                    showToast('<strong>' + label + '</strong> está ejecutando.', 'primary');
                }
            }

            prevStates[job.job_id] = newStatus;

            // Rehabilitar botón si ya no está activo
            const btn = document.getElementById('run-btn-' + job.job_id);
            if (btn && (newStatus === 'success' || newStatus === 'failed' || newStatus === '')) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-play me-1"></i>Ejecutar';
            }
        });
    }

    // ── Formatear fecha ISO a local ───────────────────────────────────────────
    function formatDate(iso) {
        if (!iso) return '–';
        try {
            const d = new Date(iso.includes('T') ? iso : iso.replace(' ', 'T'));
            if (isNaN(d)) return iso;
            return d.toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' });
        } catch (_) {
            return iso;
        }
    }

    // ── Actualizar countdown visual ───────────────────────────────────────────
    function startCountdown(ms) {
        clearInterval(countdownTimer);
        countdown = Math.round(ms / 1000);
        const el = document.getElementById('poll-countdown');
        if (!el) return;
        el.textContent = countdown + 's';
        countdownTimer = setInterval(function () {
            countdown--;
            el.textContent = countdown > 0 ? countdown + 's' : '…';
            if (countdown <= 0) clearInterval(countdownTimer);
        }, 1000);
    }

    // ── Ciclo de polling ──────────────────────────────────────────────────────
    function scheduleNext(kpis) {
        clearTimeout(pollTimer);
        const interval = (kpis.queued > 0 || kpis.running > 0) ? FAST_MS : IDLE_MS;
        startCountdown(interval);
        pollTimer = setTimeout(poll, interval);
    }

    // ── Renderizar campos dinámicos de parámetros ─────────────────────────────
    function renderParamFields(jobMetadata, lastParams) {
        const container = document.getElementById('modal-params-container');
        if (!container) return;

        container.innerHTML = '';  // Limpiar contenedor anterior

        // Si el job no soporta parámetros, mostrar mensaje
        if (!jobMetadata || !jobMetadata.supports_params) {
            container.innerHTML = '<p class="text-muted small">Este job no requiere parámetros.</p>';
            return;
        }

        // Extraer nombres de parámetros del default_params
        const defaultParams = jobMetadata.default_params || {};
        const paramNames = Object.keys(defaultParams);
        
        if (paramNames.length === 0) {
            container.innerHTML = '<p class="text-muted small">Este job no requiere parámetros.</p>';
            return;
        }

        // Renderizar un campo input para cada parámetro
        paramNames.forEach(function (paramName) {
            const paramDef = PARAM_DEFINITIONS[paramName] || {
                label: paramName,
                placeholder: 'Ingresar valor',
                type: 'text'
            };
            const hasLast = lastParams && Object.prototype.hasOwnProperty.call(lastParams, paramName);
            const lastValue = hasLast ? lastParams[paramName] : defaultParams[paramName];
            const displayValue = Array.isArray(lastValue) ? lastValue.join(', ') : lastValue;

            const controlHtml = paramDef.multiline
                ? `
                    <textarea
                        id="param-${paramName}"
                        data-param-name="${paramName}"
                        class="form-control"
                        placeholder="${paramDef.placeholder || ''}"
                        rows="3"
                        autocomplete="off"
                    >${displayValue ?? ''}</textarea>
                `
                : `
                    <input
                        id="param-${paramName}"
                        data-param-name="${paramName}"
                        type="${paramDef.type || 'text'}"
                        class="form-control"
                        placeholder="${paramDef.placeholder || ''}"
                        value="${displayValue ?? ''}"
                        autocomplete="off"
                    >
                `;

            const fieldHtml = `
                <div class="mb-3">
                    <label for="param-${paramName}" class="form-label">${paramDef.label}</label>
                    ${controlHtml}
                </div>
            `;
            container.insertAdjacentHTML('beforeend', fieldHtml);
        });
    }

    // ── Construir payload desde modal dinámico ────────────────────────────────
    function buildRunPayloadFromModal() {
        const params = {};
        const container = document.getElementById('modal-params-container');
        if (!container) return { params };

        const inputs = container.querySelectorAll('[data-param-name]');
        inputs.forEach(function (input) {
            const paramName = input.dataset.paramName;
            const paramDef = PARAM_DEFINITIONS[paramName] || {};
            const value = input.value.trim();

            if (value) {
                if (paramDef.format) {
                    try {
                        const formatted = paramDef.format(value);
                        if (formatted !== null && formatted !== undefined) {
                            params[paramName] = formatted;
                        }
                    } catch (e) {
                        console.warn('Error formateando ' + paramName + ':', e);
                    }
                } else {
                    params[paramName] = value;
                }
            }
        });
        return { params };
    }

    // ── Abrir modal de parámetros ─────────────────────────────────────────────
    function openRunModal(jobId, jobName) {
        if (!useRunModal) {
            runJob(jobId, null);
            return;
        }

        const modalEl = document.getElementById('runParamsModal');
        if (!modalEl) {
            runJob(jobId, null);
            return;
        }

        if (!runParamsModal) {
            runParamsModal = new bootstrap.Modal(modalEl);
        }

        const inputJobId = document.getElementById('modal-job-id');
        const labelJobName = document.getElementById('modal-job-name');

        if (inputJobId) inputJobId.value = jobId;
        if (labelJobName) labelJobName.textContent = jobName || jobId;

        // Fetch del catálogo de jobs para obtener metadatos
        return fetch(jobsApi)
            .then(function (res) {
                if (!res.ok) return Promise.resolve([]);
                return res.json();
            })
            .then(function (jobs) {
                const jobMetadata = jobs.find(function (j) { return j.job_id === jobId; });
                currentJobMetadata = jobMetadata;
                
                // Renderizar campos de parámetros
                renderParamFields(jobMetadata, {});

                // Si hay API de parámetros guardados, cargarlos
                if (lastParamsApi && jobMetadata && jobMetadata.supports_params) {
                    return fetch(lastParamsApi + '/' + encodeURIComponent(jobId) + '/last-params');
                }
                return Promise.resolve(null);
            })
            .then(function (res) {
                if (res && res.ok) return res.json();
                return { params: {} };
            })
            .then(function (data) {
                if (data && data.params) {
                    renderParamFields(currentJobMetadata, data.params);
                }
            })
            .catch(function (err) {
                console.warn('Error cargando metadatos del job:', err);
                renderParamFields(currentJobMetadata, {});
            })
            .finally(function () {
                runParamsModal.show();
            });
    }

    // ── Polling ───────────────────────────────────────────────────────────────
    function poll() {
        if (isPolling) return;
        isPolling = true;

        const promises = [fetch(KPIS_API).then(r => r.json())];

        if (pageType === 'etl' || pageType === 'load') {
            promises.push(fetch(jobsApi).then(r => r.json()));
        } else if (pageType === 'runs' && runsTable) {
            runsTable.ajax.reload(null, false);
        }

        Promise.all(promises)
            .then(function (results) {
                const kpis = results[0];
                updateKPIs(kpis);
                if (results[1]) updateJobRows(results[1]);
                scheduleNext(kpis);
            })
            .catch(function (err) {
                console.warn('[EtlPolling] Error en poll:', err);
                scheduleNext({ queued: 0, running: 0, success: 0, failed: 0 });
            })
            .finally(function () {
                isPolling = false;
            });
    }

    // ── Ejecutar un job (llamado desde el botón) ──────────────────────────────
    function runJob(jobId, payload) {
        const btn = document.getElementById('run-btn-' + jobId);
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>En cola…';
        }

        const requestOptions = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || { params: {} }),
        };

        fetch(runApi + '/' + encodeURIComponent(jobId) + '/run', requestOptions)
            .then(function (res) {
                if (!res.ok) return res.json().then(d => Promise.reject(d));
                return res.json();
            })
            .then(function (data) {
                prevStates[jobId] = 'queued';
                showToast('Job <strong>' + jobId + '</strong> enviado a la cola (run #' + data.run_id + ').', 'info');
                const row = document.querySelector('tr[data-job-id="' + jobId + '"]');
                if (row) {
                    const badge = row.querySelector('.status-badge');
                    if (badge) { badge.innerHTML = badgeHtml('queued'); badge.dataset.status = 'queued'; }
                }
                clearTimeout(pollTimer);
                clearInterval(countdownTimer);
                poll();

                if (runParamsModal) {
                    runParamsModal.hide();
                }
            })
            .catch(function (err) {
                const msg = (err && err.detail) ? err.detail : 'Error al encolar el job.';
                showToast(msg, 'danger');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-play me-1"></i>Ejecutar';
                }
            });
    }

    // ── Inicializar tabla de runs ─────────────────────────────────────────────
    function initRunsTable() {
        if (!$.fn.DataTable) return;

        runsTable = $('#runsTable').DataTable({
            ajax: { url: RUNS_API, dataSrc: '' },
            order: [[0, 'desc']],
            language: { url: '//cdn.datatables.net/plug-ins/1.13.8/i18n/es-ES.json' },
            responsive: true,
            paging: true,
            pageLength: 25,
            lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
            dom: '<"row g-2 px-3 pt-2"<"col-md-6"l><"col-md-6"f>>rtip',
            columns: [
                { data: 'run_id', width: '70px' },
                { data: 'job_id', render: d => '<code>' + d + '</code>' },
                { data: 'status', render: function (d) { return badgeHtml(d || ''); } },
                { data: 'started_at',  render: d => formatDate(d) },
                { data: 'finished_at', render: d => formatDate(d) },
                { data: 'duration_seconds', defaultContent: '–' },
                {
                    data: 'output_path',
                    defaultContent: '–',
                    render: function (d) {
                        if (!d) return '–';
                        const parts = d.replace(/\\/g, '/').split('/');
                        return '<span title="' + d + '" data-bs-toggle="tooltip">' + parts[parts.length - 1] + '</span>';
                    }
                },
                {
                    data: 'error_message',
                    defaultContent: '–',
                    render: function (d) {
                        if (!d) return '–';
                        const short = d.length > 60 ? d.slice(0, 60) + '…' : d;
                        return '<span class="text-danger small" title="' + d.replace(/"/g, '&quot;') + '" data-bs-toggle="tooltip">' + short + '</span>';
                    }
                },
            ],
            drawCallback: function () {
                document.querySelectorAll('#runsTable [data-bs-toggle="tooltip"]').forEach(el => {
                    if (!bootstrap.Tooltip.getInstance(el)) new bootstrap.Tooltip(el);
                });
            }
        });
    }

    // ── Inicialización general ────────────────────────────────────────────────
    function renderFlowMap(selectedGroup) {
        const container = document.getElementById('etl-flow-map');
        const empty = document.getElementById('etl-flow-empty');
        if (!container) return;

        const flowApi = '/api/etl/flow?group=' + encodeURIComponent(selectedGroup || 'Todos');
        fetch(flowApi)
            .then(function (res) { return res.ok ? res.json() : Promise.resolve({ nodes: [], edges: [] }); })
            .then(function (payload) {
                const nodes = payload.nodes || [];
                const edges = payload.edges || [];

                if (!nodes.length) {
                    container.innerHTML = '';
                    if (empty) {
                        empty.classList.remove('d-none');
                    }
                    return;
                }

                if (empty) {
                    empty.classList.add('d-none');
                }

                const groupOrder = ['Siembras', 'Producción', 'Planeación', 'Analítica', 'Otros'];
                const groups = {};
                groupOrder.forEach(function (name) { groups[name] = []; });
                groups['Otros'] = [];

                nodes.forEach(function (node) {
                    const g = node.dependency_group || 'Otros';
                    if (!groups[g]) groups[g] = [];
                    groups[g].push(node);
                });

                const html = groupOrder.map(function (groupName) {
                    const items = groups[groupName] || [];
                    if (!items.length) return '';
                    const cards = items.map(function (node) {
                        const ready = node.dependency_status === 'ready' ? 'text-success' : 'text-warning';
                        return '<div class="etl-flow-node ' + ready + '"><strong>' + (node.name || node.job_id) + '</strong><small>' + (node.job_id || '') + '</small></div>';
                    }).join('');
                    return '<div class="etl-flow-column"><div class="etl-flow-title">' + groupName + '</div>' + cards + '</div>';
                }).join('');

                container.innerHTML = '<div class="etl-flow-grid">' + html + '</div>';

                const MapGraph = document.createElement('div');
                MapGraph.className = 'etl-flow-edges';
                const edgeHtml = edges.map(function (edge) {
                    const fromNode = nodes.find(function (node) { return node.job_id === edge.from; });
                    const toNode = nodes.find(function (node) { return node.job_id === edge.to; });
                    if (!fromNode || !toNode) return '';
                    return '<div class="etl-flow-edge"><span>' + (fromNode.name || fromNode.job_id) + '</span><i class="fas fa-arrow-right"></i><span>' + (toNode.name || toNode.job_id) + '</span></div>';
                }).join('');
                if (edgeHtml) {
                    container.insertAdjacentHTML('beforeend', '<div class="etl-flow-edges-wrap">' + edgeHtml + '</div>');
                }
            })
            .catch(function (err) {
                console.warn('[EtlPolling] Error cargando flow map:', err);
                container.innerHTML = '';
                if (empty) {
                    empty.classList.remove('d-none');
                }
            });
    }

    function init() {
        const section = document.querySelector('section[data-page-type]');
        if (!section) return;

        pageType = section.dataset.pageType;
        jobsApi  = section.dataset.jobsApi  || null;
        runApi   = section.dataset.runApi   || '/api/etl/jobs';
        lastParamsApi = section.dataset.lastParamsApi || null;
        useRunModal = section.dataset.useRunModal === '1';

        const searchInput = document.getElementById('etl-job-search');
        let currentGroup = 'Todos';

        document.querySelectorAll('[data-group-filter]').forEach(function (button) {
            button.addEventListener('click', function () {
                const selectedGroup = button.dataset.groupFilter;
                currentGroup = selectedGroup;
                document.querySelectorAll('[data-group-filter]').forEach(function (item) {
                    const isActive = item === button;
                    item.classList.toggle('active', isActive);
                    item.classList.toggle('btn-primary', isActive);
                    item.classList.toggle('btn-outline-primary', !isActive);
                });
                applyDependencyFilter(selectedGroup, searchInput ? searchInput.value : '');
                if (pageType === 'etl') {
                    renderFlowMap(selectedGroup);
                }
            });
        });

        if (searchInput) {
            searchInput.addEventListener('input', function () {
                applyDependencyFilter(currentGroup, this.value);
            });
        }

        if (pageType === 'etl' || pageType === 'load') {
            if (document.getElementById('jobsTable')) {
                document.getElementById('btn-refresh').addEventListener('click', () => {
                    clearTimeout(pollTimer);
                    clearInterval(countdownTimer);
                    poll();
                });

                document.getElementById('btn-confirm-run-modal').addEventListener('click', () => {
                    const jobId = document.getElementById('modal-job-id').value;
                    if (jobId) {
                        const payload = buildRunPayloadFromModal();
                        runJob(jobId, payload);
                    }
                });

                applyDependencyFilter('Todos');
                renderFlowMap('Todos');
                poll();
            }
        } else if (pageType === 'runs') {
            initRunsTable();
            poll();
        }

        // Polling periódico
        scheduleNext({ queued: 0, running: 0, success: 0, failed: 0 });
    }

    return { init, runJob, openRunModal, poll, showToast };
})();

// Inicializar cuando el documento esté listo
document.addEventListener('DOMContentLoaded', EtlPolling.init);
