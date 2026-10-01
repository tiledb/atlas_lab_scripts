/* Shared DBQ_Mk6 conflict check + replace / continue-anyway prompt. */
(function (global) {
    function parseIdSpec(value) {
        const text = String(value || '').trim();
        if (!text) return [];
        const ids = [];
        text.replace(/;/g, ',').split(',').forEach((token) => {
            const part = token.trim();
            if (!part) return;
            if (part.includes('-')) {
                const ends = part.split('-', 2);
                let start = Number(ends[0]);
                let end = Number(ends[1]);
                if (!Number.isFinite(start) || !Number.isFinite(end)) return;
                if (end < start) {
                    const tmp = start;
                    start = end;
                    end = tmp;
                }
                for (let i = start; i <= end; i += 1) ids.push(i);
            } else {
                const num = Number(part);
                if (Number.isFinite(num)) ids.push(num);
            }
        });
        return Array.from(new Set(ids));
    }

    function extractFlagValue(command, flags) {
        const tokens = String(command || '').split(/\s+/).filter(Boolean);
        for (let i = 0; i < tokens.length; i += 1) {
            const token = tokens[i];
            if (flags.includes(token)) {
                const next = tokens[i + 1];
                if (!next || next.startsWith('-')) return '';
                return next;
            }
            for (const flag of flags) {
                const prefix = `${flag}=`;
                if (token.startsWith(prefix)) return token.slice(prefix.length);
            }
        }
        return null;
    }

    function parseDbqScope(command) {
        const benchRaw = extractFlagValue(command, ['-b', '--benchtest_id']);
        const boardRaw = extractFlagValue(command, ['-d', '--daughterboard_id']);
        const benchtests = benchRaw ? parseIdSpec(benchRaw) : null;
        const daughterboards = boardRaw ? parseIdSpec(boardRaw) : null;
        return {
            benchtests,
            daughterboards,
            unrestricted: benchtests === null && daughterboards === null,
        };
    }

    function setsIntersect(left, right) {
        if (!left || !right || !left.length || !right.length) return false;
        const rightSet = new Set(right);
        return left.some((item) => rightSet.has(item));
    }

    function scopesOverlap(left, right) {
        if (!left || !right) return true;
        if (left.unrestricted || right.unrestricted) return true;
        if (
            left.benchtests &&
            right.benchtests &&
            setsIntersect(left.benchtests, right.benchtests)
        ) {
            return true;
        }
        if (
            left.daughterboards &&
            right.daughterboards &&
            setsIntersect(left.daughterboards, right.daughterboards)
        ) {
            return true;
        }
        return false;
    }

    function statusOverlapsProposed(status, proposedCommand) {
        if (typeof status.overlaps === 'boolean') return status.overlaps;
        const proposed = parseDbqScope(proposedCommand);
        const scopes = [];
        (status.processes || []).forEach((proc) => {
            scopes.push(proc.scope || parseDbqScope(proc.cmdline));
        });
        (status.jobs || []).forEach((job) => {
            scopes.push(job.scope || parseDbqScope(job.command || job.cmdline));
        });
        if (status.job && !(status.jobs || []).length) {
            scopes.push(status.job.scope || parseDbqScope(status.job.command || status.job.cmdline));
        }
        if (!scopes.length) return true;
        return scopes.some((scope) => scopesOverlap(proposed, scope));
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatResource(proc) {
        const cpu = (proc.cpu_percent == null) ? '—' : `${proc.cpu_percent}%`;
        const memMb = (proc.memory_rss_mb == null) ? '—' : `${proc.memory_rss_mb} MB`;
        const memPct = (proc.memory_percent == null) ? '' : ` (${proc.memory_percent}%)`;
        return { cpu, mem: `${memMb}${memPct}` };
    }

    function renderProcessInfo(status, proposedCommand) {
        const processes = status.processes || [];
        const parts = [];

        if (!processes.length) {
            if (status.job && status.job.active) {
                parts.push(
                    '<div class="dbq-proc-card">'
                    + '<div class="dbq-proc-title">Web UI job active</div>'
                    + '<div class="dbq-proc-meta">Between sequential DBQ processes, or waiting to start.</div>'
                    + (status.job.command
                        ? `<div class="dbq-proc-cmd">${escapeHtml(status.job.command)}</div>`
                        : '')
                    + '</div>'
                );
            } else {
                parts.push('<div class="dbq-proc-empty">No live DBQ_Mk6 process found.</div>');
            }
        }

        processes.forEach((proc, index) => {
            const resources = formatResource(proc);
            const origin = proc.tracked_by_ui ? 'web UI' : 'external/OS';
            parts.push(
                `<div class="dbq-proc-card">`
                + `<div class="dbq-proc-title">#${index + 1} · PID ${escapeHtml(proc.pid)}`
                + `<span class="dbq-proc-tag">${escapeHtml(origin)}</span></div>`
                + `<div class="dbq-proc-grid">`
                + `<div><span>Running</span><strong>${escapeHtml(proc.running_for || 'unknown')}</strong></div>`
                + `<div><span>Started</span><strong>${escapeHtml(proc.started_at || 'unknown')}</strong></div>`
                + `<div><span>CPU</span><strong>${escapeHtml(resources.cpu)}</strong></div>`
                + `<div><span>Memory</span><strong>${escapeHtml(resources.mem)}</strong></div>`
                + `</div>`
                + `<div class="dbq-proc-cmd">${escapeHtml(proc.cmdline || '')}</div>`
                + `</div>`
            );
        });

        if (proposedCommand) {
            const overlaps = statusOverlapsProposed(status, proposedCommand);
            parts.push(
                `<div class="dbq-proc-proposed">`
                + `<div><strong>Proposed:</strong> <code>${escapeHtml(proposedCommand)}</code></div>`
                + `<div class="dbq-proc-overlap ${overlaps ? 'yes' : 'no'}">`
                + (overlaps
                    ? 'Scope overlap: yes'
                    : 'Scope overlap: no — Continue anyway is available')
                + `</div></div>`
            );
        }
        return parts.join('');
    }

    function ensureModal() {
        let modal = document.getElementById('dbq-conflict-modal');
        if (modal) {
            if (!modal.querySelector('.dbq-conflict-processes')) {
                const oldInfo = modal.querySelector('.dbq-conflict-info');
                if (oldInfo) {
                    const host = document.createElement('div');
                    host.className = 'dbq-conflict-processes';
                    oldInfo.replaceWith(host);
                }
            }
            if (!modal.querySelector('.dbq-conflict-finished')) {
                const help = modal.querySelector('.dbq-conflict-help');
                const banner = document.createElement('div');
                banner.className = 'dbq-conflict-finished';
                banner.setAttribute('role', 'status');
                banner.setAttribute('aria-live', 'polite');
                if (help && help.parentNode) {
                    help.parentNode.insertBefore(banner, help.nextSibling);
                }
            }
            if (!modal.querySelector('.dbq-conflict-start')) {
                const actions = modal.querySelector('.dbq-conflict-actions');
                if (actions) {
                    const startBtn = document.createElement('button');
                    startBtn.type = 'button';
                    startBtn.className = 'dbq-conflict-start';
                    startBtn.textContent = 'Start now';
                    actions.appendChild(startBtn);
                }
            }
            if (!modal.querySelector('.dbq-conflict-terminal-shell')) {
                const wrap = modal.querySelector('.dbq-conflict-output-wrap');
                const output = modal.querySelector('.dbq-conflict-output');
                if (wrap && output && !output.closest('.dbq-terminal-shell')) {
                    const shell = document.createElement('div');
                    shell.className = 'dbq-conflict-terminal-shell dbq-terminal-shell';
                    const host = wrap.querySelector('.dbq-conflict-terminal-controls-host');
                    if (host) host.remove();
                    wrap.appendChild(shell);
                    shell.appendChild(output);
                }
            }
            return modal;
        }

        modal = document.createElement('div');
        modal.id = 'dbq-conflict-modal';
        modal.innerHTML = `
            <div class="dbq-conflict-backdrop"></div>
            <div class="dbq-conflict-dialog" role="dialog" aria-modal="true">
                <h3 class="dbq-conflict-title">DBQ_Mk6 is already running</h3>
                <p class="dbq-conflict-help"></p>
                <div class="dbq-conflict-finished" role="status" aria-live="polite"></div>
                <div class="dbq-conflict-processes"></div>
                <div class="dbq-conflict-output-wrap">
                    <div class="dbq-conflict-output-label">Console output</div>
                    <div class="dbq-conflict-terminal-shell dbq-terminal-shell">
                        <pre class="dbq-conflict-output dbq-terminal-body"></pre>
                    </div>
                </div>
                <div class="dbq-conflict-actions">
                    <button type="button" class="dbq-conflict-cancel">Cancel</button>
                    <button type="button" class="dbq-conflict-continue">Continue anyway</button>
                    <button type="button" class="dbq-conflict-kill">Kill running instance and continue</button>
                    <button type="button" class="dbq-conflict-start">Start now</button>
                </div>
            </div>
        `;

        const style = document.createElement('style');
        style.id = 'dbq-conflict-styles';
        style.dataset.version = '2';
        style.textContent = `
            #dbq-conflict-modal {
                display: none;
                position: fixed;
                inset: 0;
                z-index: 10000;
            }
            #dbq-conflict-modal.visible { display: block; }
            .dbq-conflict-backdrop {
                position: absolute;
                inset: 0;
                background: rgba(15, 23, 42, 0.55);
            }
            .dbq-conflict-dialog {
                position: relative;
                max-width: 820px;
                margin: 6vh auto;
                background: #fff;
                border-radius: 12px;
                padding: 22px;
                box-shadow: 0 20px 50px rgba(0,0,0,0.25);
                max-height: 88vh;
                overflow: auto;
            }
            .dbq-conflict-dialog h3 {
                margin: 0 0 8px;
                font-size: 20px;
                color: #111827;
            }
            .dbq-conflict-help {
                margin: 0 0 14px;
                color: #4b5563;
                font-size: 14px;
                line-height: 1.45;
            }
            .dbq-conflict-finished {
                display: none;
                margin: 0 0 14px;
                padding: 10px 12px;
                border-radius: 8px;
                border: 1px solid #a7f3d0;
                background: #ecfdf5;
                color: #065f46;
                font-size: 14px;
                font-weight: 650;
                line-height: 1.4;
            }
            .dbq-conflict-finished.visible {
                display: block;
                animation: dbq-finished-pulse 0.9s ease-out 1;
            }
            @keyframes dbq-finished-pulse {
                0% { transform: scale(0.98); background: #bbf7d0; }
                100% { transform: scale(1); background: #ecfdf5; }
            }
            .dbq-conflict-processes {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-bottom: 14px;
            }
            .dbq-proc-card {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 10px 12px;
                background: #f9fafb;
            }
            .dbq-proc-title {
                font-size: 13px;
                font-weight: 700;
                color: #111827;
                margin-bottom: 8px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .dbq-proc-tag {
                font-size: 11px;
                font-weight: 600;
                color: #4b5563;
                background: #e5e7eb;
                border-radius: 999px;
                padding: 2px 8px;
            }
            .dbq-proc-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 6px 12px;
                margin-bottom: 8px;
            }
            .dbq-proc-grid span {
                display: block;
                font-size: 11px;
                color: #6b7280;
            }
            .dbq-proc-grid strong {
                font-size: 13px;
                color: #111827;
                font-weight: 650;
            }
            .dbq-proc-cmd, .dbq-proc-proposed code {
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                font-size: 11px;
                color: #1f2937;
                word-break: break-word;
                white-space: pre-wrap;
            }
            .dbq-proc-cmd {
                background: #111827;
                color: #e5e7eb;
                border-radius: 6px;
                padding: 8px 10px;
            }
            .dbq-proc-proposed {
                border: 1px dashed #d1d5db;
                border-radius: 8px;
                padding: 8px 10px;
                font-size: 12px;
                color: #374151;
            }
            .dbq-proc-overlap { margin-top: 6px; font-weight: 650; }
            .dbq-proc-overlap.yes { color: #b42318; }
            .dbq-proc-overlap.no { color: #0f766e; }
            .dbq-proc-empty, .dbq-proc-meta {
                font-size: 13px;
                color: #6b7280;
            }
            .dbq-conflict-output-wrap { margin-top: 4px; }
            .dbq-conflict-output-label {
                font-size: 12px;
                color: #6b7280;
                margin-bottom: 6px;
                font-weight: 600;
            }
            .dbq-conflict-terminal-shell {
                max-height: 280px;
            }
            .dbq-conflict-output {
                background: #111827;
                color: #e5e7eb;
                padding: 10px 12px;
                font-size: 12px;
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                white-space: pre-wrap;
                word-break: break-word;
                margin: 0;
                overflow: auto;
                min-height: 120px;
                max-height: 230px;
            }
            .dbq-conflict-actions {
                display: flex;
                justify-content: flex-end;
                gap: 10px;
                margin-top: 18px;
                flex-wrap: wrap;
            }
            .dbq-conflict-cancel,
            .dbq-conflict-continue,
            .dbq-conflict-kill,
            .dbq-conflict-start {
                border: none;
                border-radius: 6px;
                padding: 10px 14px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
            }
            .dbq-conflict-cancel { background: #f3f4f6; color: #374151; }
            .dbq-conflict-cancel:hover { background: #e5e7eb; }
            .dbq-conflict-continue { background: #0f766e; color: #fff; display: none; }
            .dbq-conflict-continue.visible { display: inline-block; }
            .dbq-conflict-continue:hover { background: #0d9488; }
            .dbq-conflict-kill { background: #b42318; color: #fff; }
            .dbq-conflict-kill:hover { background: #912018; }
            .dbq-conflict-start { background: #2563eb; color: #fff; display: none; }
            .dbq-conflict-start.visible { display: inline-block; }
            .dbq-conflict-start:hover { background: #1d4ed8; }
            #dbq-conflict-modal.finished .dbq-conflict-kill,
            #dbq-conflict-modal.finished .dbq-conflict-continue {
                display: none !important;
            }
            @media (max-width: 640px) {
                .dbq-proc-grid { grid-template-columns: 1fr; }
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(modal);
        return modal;
    }

    function statusIsRunning(status) {
        if (!status) return false;
        if (typeof status.running === 'boolean') return status.running;
        const processes = status.processes || [];
        if (processes.length) return true;
        const jobs = status.jobs || [];
        if (jobs.some((job) => job && job.active)) return true;
        return !!(status.job && status.job.active);
    }

    function promptConflict(status, proposedCommand) {
        const modal = ensureModal();
        const title = modal.querySelector('.dbq-conflict-title')
            || modal.querySelector('.dbq-conflict-dialog h3');
        const help = modal.querySelector('.dbq-conflict-help');
        const finishedBanner = modal.querySelector('.dbq-conflict-finished');
        const processesHost = modal.querySelector('.dbq-conflict-processes');
        const output = modal.querySelector('.dbq-conflict-output');
        const cancelBtn = modal.querySelector('.dbq-conflict-cancel');
        const continueBtn = modal.querySelector('.dbq-conflict-continue');
        const killBtn = modal.querySelector('.dbq-conflict-kill');
        const startBtn = modal.querySelector('.dbq-conflict-start');
        const overlaps = statusOverlapsProposed(status, proposedCommand);

        let terminal = null;
        if (global.DbqTerminal && typeof global.DbqTerminal.attach === 'function') {
            terminal = global.DbqTerminal.attach({
                outputEl: output,
                scrollEl: output,
                storageKey: 'dbq_conflict_terminal',
                defaultMaxLines: 2000,
                defaultAutoscroll: true,
            });
        }

        let finishedNotified = false;
        modal.classList.remove('finished');
        if (title) title.textContent = 'DBQ_Mk6 is already running';
        if (finishedBanner) {
            finishedBanner.classList.remove('visible');
            finishedBanner.textContent = '';
        }
        if (startBtn) startBtn.classList.remove('visible');

        help.textContent = overlaps
            ? 'Another instance of DBQ_Mk6.py is running and its benchtest/daughterboard scope overlaps your request. Cancel, or kill it and start yours.'
            : 'Another instance of DBQ_Mk6.py is running, but its benchtest/daughterboard scope does not overlap your request. You can continue in parallel, kill it, or cancel.';

        processesHost.innerHTML = renderProcessInfo(status, proposedCommand);
        const tail = status.output_tail || (status.job && status.job.output_tail) || '';
        const fallbackText = 'Console output is not available for this instance '
            + '(it was not started by this web UI, or no output has been captured yet).';
        if (terminal) {
            terminal.setText(tail || fallbackText);
            terminal.show();
        } else {
            output.textContent = tail || fallbackText;
        }

        continueBtn.classList.toggle('visible', !overlaps);
        killBtn.style.display = '';
        modal.classList.add('visible');

        let pollTimer = null;
        function stopPoll() {
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        }

        function markFinished(nextStatus) {
            if (finishedNotified) return;
            finishedNotified = true;
            modal.classList.add('finished');
            if (title) title.textContent = 'DBQ_Mk6 finished';
            help.textContent = 'The previously running instance has finished. You can start your command now, or cancel.';
            if (finishedBanner) {
                finishedBanner.textContent = 'The already-running DBQ_Mk6 process has finished.';
                finishedBanner.classList.add('visible');
            }
            continueBtn.classList.remove('visible');
            killBtn.style.display = 'none';
            if (startBtn) startBtn.classList.add('visible');
            processesHost.innerHTML = renderProcessInfo(nextStatus || { processes: [] }, proposedCommand);
        }

        function applyOutput(nextStatus) {
            const stillRunning = statusIsRunning(nextStatus);
            if (!stillRunning) {
                markFinished(nextStatus);
            } else {
                processesHost.innerHTML = renderProcessInfo(nextStatus, proposedCommand);
            }
            const nextTail = nextStatus.output_tail
                || (nextStatus.job && nextStatus.job.output_tail)
                || '';
            if (!nextTail) return;
            if (terminal) {
                terminal.setText(nextTail);
            } else {
                output.textContent = nextTail;
                output.scrollTop = output.scrollHeight;
            }
        }
        pollTimer = setInterval(() => {
            fetchDbqStatus(proposedCommand)
                .then(applyOutput)
                .catch(() => {});
        }, 1000);

        return new Promise((resolve) => {
            function finish(result) {
                stopPoll();
                modal.classList.remove('visible');
                modal.classList.remove('finished');
                cancelBtn.removeEventListener('click', onCancel);
                continueBtn.removeEventListener('click', onContinue);
                killBtn.removeEventListener('click', onKill);
                if (startBtn) startBtn.removeEventListener('click', onStartNow);
                modal.querySelector('.dbq-conflict-backdrop').removeEventListener('click', onCancel);
                resolve(result);
            }
            function onCancel() {
                finish({ proceed: false, replace: false, allowParallel: false });
            }
            function onContinue() {
                if (!window.confirm('Are you sure you want to start another DBQ_Mk6 instance in parallel?')) {
                    return;
                }
                finish({ proceed: true, replace: false, allowParallel: true });
            }
            function onKill() {
                if (!window.confirm('Are you sure you want to kill the running DBQ_Mk6 instance and start a new one?')) {
                    return;
                }
                finish({ proceed: true, replace: true, allowParallel: false });
            }
            function onStartNow() {
                finish({ proceed: true, replace: false, allowParallel: false });
            }
            cancelBtn.addEventListener('click', onCancel);
            continueBtn.addEventListener('click', onContinue);
            killBtn.addEventListener('click', onKill);
            if (startBtn) startBtn.addEventListener('click', onStartNow);
            modal.querySelector('.dbq-conflict-backdrop').addEventListener('click', onCancel);
        });
    }

    async function fetchDbqStatus(proposedCommand) {
        const params = new URLSearchParams();
        if (proposedCommand) params.set('command', proposedCommand);
        const url = params.toString() ? `/api/dbq_status?${params}` : '/api/dbq_status';
        const response = await fetch(url);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `Failed to check DBQ status (${response.status})`);
        }
        return data;
    }

    async function killDbqInstances() {
        const response = await fetch('/api/dbq_kill', { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to kill running DBQ_Mk6 instance');
        }
        return data;
    }

    /**
     * Check for a running DBQ_Mk6 instance before starting a new one.
     * proposedCommand should match the CLI that will be launched.
     * Returns { proceed, replace, allowParallel }.
     */
    async function confirmDbqStart(proposedCommand) {
        const status = await fetchDbqStatus(proposedCommand);
        if (!status.running) {
            return { proceed: true, replace: false, allowParallel: false };
        }
        const choice = await promptConflict(status, proposedCommand);
        if (!choice.proceed) {
            return { proceed: false, replace: false, allowParallel: false };
        }
        if (choice.replace) {
            await killDbqInstances();
            return { proceed: true, replace: true, allowParallel: false };
        }
        return { proceed: true, replace: false, allowParallel: true };
    }

    /**
     * Parse a non-OK streaming response that may be JSON conflict or text error.
     */
    async function readDbqLaunchError(response, proposedCommand) {
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            const data = await response.json().catch(() => ({}));
            if (response.status === 409 && data.running) {
                const choice = await promptConflict(data, proposedCommand);
                if (!choice.proceed) {
                    return {
                        retry: false,
                        error: 'Cancelled: another DBQ_Mk6 instance is still running.',
                    };
                }
                if (choice.replace) {
                    await killDbqInstances();
                    return { retry: true, replace: true, allowParallel: false };
                }
                return { retry: true, replace: false, allowParallel: true };
            }
            return { retry: false, error: data.error || `Request failed (${response.status})` };
        }
        const text = await response.text();
        return { retry: false, error: text || `Request failed (${response.status})` };
    }

    global.DbqGuard = {
        fetchDbqStatus,
        killDbqInstances,
        confirmDbqStart,
        readDbqLaunchError,
        promptConflict,
        parseDbqScope,
        scopesOverlap,
    };
})(window);
