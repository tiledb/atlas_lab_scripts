/* Shared terminal output controls: compact toolbar inside the terminal shell. */
(function (global) {
    const DEFAULT_MAX_LINES = 5000;
    const MIN_MAX_LINES = 50;
    const MAX_MAX_LINES = 100000;

    function clampMaxLines(value, fallback) {
        const num = Number(value);
        if (!Number.isFinite(num)) return fallback;
        return Math.max(MIN_MAX_LINES, Math.min(MAX_MAX_LINES, Math.floor(num)));
    }

    function readStored(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            if (raw === null || raw === undefined) return fallback;
            return raw;
        } catch (err) {
            return fallback;
        }
    }

    function writeStored(key, value) {
        try {
            localStorage.setItem(key, String(value));
        } catch (err) {
            // ignore
        }
    }

    function ensureStyles() {
        if (document.getElementById('dbq-terminal-styles')) return;
        const style = document.createElement('style');
        style.id = 'dbq-terminal-styles';
        style.textContent = `
            .dbq-terminal-shell {
                display: flex;
                flex-direction: column;
                border: 1px solid #333;
                border-radius: 8px;
                overflow: hidden;
                background: #1e1e1e;
                min-width: 0;
            }
            .dbq-terminal-toolbar {
                display: flex !important;
                flex-wrap: wrap;
                gap: 10px 14px;
                align-items: center;
                padding: 6px 10px;
                background: #2a2a2a;
                border-bottom: 1px solid #3a3a3a;
                color: #d1d5db;
                font-size: 12px;
                line-height: 1.2;
            }
            .dbq-terminal-toolbar label {
                display: inline-flex !important;
                align-items: center;
                gap: 5px;
                margin: 0 !important;
                font-weight: 500;
                color: inherit;
                cursor: pointer;
                user-select: none;
                width: auto !important;
                font-size: 12px;
            }
            .dbq-terminal-toolbar input[type="checkbox"] {
                width: 13px !important;
                height: 13px !important;
                margin: 0 !important;
                accent-color: #8b9cf7;
                flex: none;
            }
            .dbq-terminal-toolbar input[type="number"] {
                width: 64px !important;
                min-width: 64px;
                padding: 2px 6px !important;
                border: 1px solid #555 !important;
                border-radius: 4px;
                font-size: 12px;
                background: #111827;
                color: #e5e7eb;
                height: 22px;
            }
            .dbq-terminal-body {
                margin: 0 !important;
                border: none !important;
                border-radius: 0 !important;
                box-shadow: none !important;
                max-height: inherit;
            }
            /* Light pages (run script / requalify): keep dark terminal body, subtle shell */
            .form-card .dbq-terminal-shell,
            .card .dbq-terminal-shell {
                border-color: #333;
            }
        `;
        document.head.appendChild(style);
    }

    function wrapInShell(outputEl, wrapEl) {
        const target = wrapEl || outputEl;
        let shell = target.closest('.dbq-terminal-shell') || outputEl.closest('.dbq-terminal-shell');
        if (shell) {
            let toolbar = shell.querySelector('.dbq-terminal-toolbar');
            if (!toolbar) {
                toolbar = document.createElement('div');
                toolbar.className = 'dbq-terminal-toolbar';
                shell.insertBefore(toolbar, shell.firstChild);
            }
            target.classList.add('dbq-terminal-body');
            outputEl.classList.add('dbq-terminal-body');
            return { shell, toolbar };
        }

        shell = document.createElement('div');
        shell.className = 'dbq-terminal-shell';
        const toolbar = document.createElement('div');
        toolbar.className = 'dbq-terminal-toolbar';
        const parent = target.parentNode;
        parent.insertBefore(shell, target);

        // Preserve useful sizing from the original scroll/terminal element.
        const maxHeight = window.getComputedStyle(target).maxHeight;
        if (maxHeight && maxHeight !== 'none') {
            shell.style.maxHeight = maxHeight;
            target.style.maxHeight = 'none';
            target.style.flex = '1 1 auto';
            target.style.overflowY = 'auto';
            shell.style.display = 'flex';
            shell.style.flexDirection = 'column';
        }

        shell.appendChild(toolbar);
        shell.appendChild(target);
        target.classList.add('dbq-terminal-body');
        outputEl.classList.add('dbq-terminal-body');
        return { shell, toolbar };
    }

    function attach(options) {
        ensureStyles();
        const outputEl = options.outputEl;
        if (!outputEl) {
            console.warn('DbqTerminal.attach: outputEl is required');
            return null;
        }
        if (outputEl.dataset.dbqTerminalAttached === '1' && outputEl._dbqTerminal) {
            return outputEl._dbqTerminal;
        }

        const storageKey = options.storageKey || 'dbq_terminal';
        const defaultMaxLines = clampMaxLines(options.defaultMaxLines, DEFAULT_MAX_LINES);
        const defaultAutoscroll = options.defaultAutoscroll !== false;
        const autoKey = `${storageKey}:autoscroll`;
        const maxKey = `${storageKey}:max_lines`;

        let autoscroll = readStored(autoKey, defaultAutoscroll ? '1' : '0') !== '0';
        let maxLines = clampMaxLines(readStored(maxKey, defaultMaxLines), defaultMaxLines);
        let stickToBottom = true;

        const scrollEl = options.scrollEl || outputEl;
        const { shell, toolbar } = wrapInShell(outputEl, options.wrapEl || null);

        // Hide legacy external control hosts if present.
        if (options.controlsHost) {
            options.controlsHost.style.display = 'none';
            options.controlsHost.innerHTML = '';
        }

        toolbar.innerHTML = `
            <label title="Follow new output">
                <input type="checkbox" class="dbq-terminal-autoscroll">
                Autoscroll
            </label>
            <label title="Keep only the newest N lines">
                Max
                <input type="number" class="dbq-terminal-max-lines" min="${MIN_MAX_LINES}" max="${MAX_MAX_LINES}" step="50">
                lines
            </label>
        `;

        const autoInput = toolbar.querySelector('.dbq-terminal-autoscroll');
        const maxInput = toolbar.querySelector('.dbq-terminal-max-lines');
        autoInput.checked = autoscroll;
        maxInput.value = String(maxLines);

        function isNearBottom() {
            const threshold = 48;
            return (scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight) < threshold;
        }

        function scrollToBottom() {
            scrollEl.scrollTop = scrollEl.scrollHeight;
        }

        function trimToMaxLines() {
            const text = outputEl.textContent || '';
            if (!text) return;
            const approxLines = (text.match(/\n/g) || []).length + 1;
            if (approxLines <= maxLines) return;
            const lines = text.split('\n');
            if (lines.length <= maxLines) return;
            const kept = lines.slice(lines.length - maxLines);
            const wasAtBottom = stickToBottom;
            outputEl.textContent = kept.join('\n');
            if (autoscroll && wasAtBottom) scrollToBottom();
        }

        function clear(initialText) {
            outputEl.textContent = initialText == null ? '' : String(initialText);
            stickToBottom = true;
            if (autoscroll) scrollToBottom();
        }

        function append(text) {
            if (!text) return;
            outputEl.textContent += text;
            trimToMaxLines();
            if (autoscroll && stickToBottom) scrollToBottom();
        }

        function setText(text) {
            outputEl.textContent = text == null ? '' : String(text);
            trimToMaxLines();
            if (autoscroll && stickToBottom) scrollToBottom();
        }

        function show() {
            shell.style.display = 'flex';
        }

        function hide() {
            shell.style.display = 'none';
        }

        scrollEl.addEventListener('scroll', () => {
            stickToBottom = isNearBottom();
        });

        autoInput.addEventListener('change', () => {
            autoscroll = !!autoInput.checked;
            writeStored(autoKey, autoscroll ? '1' : '0');
            if (autoscroll) {
                stickToBottom = true;
                scrollToBottom();
            }
        });

        function applyMaxLinesFromInput() {
            maxLines = clampMaxLines(maxInput.value, maxLines);
            maxInput.value = String(maxLines);
            writeStored(maxKey, maxLines);
            trimToMaxLines();
        }

        maxInput.addEventListener('change', applyMaxLinesFromInput);
        maxInput.addEventListener('blur', applyMaxLinesFromInput);

        const api = {
            shell,
            controls: toolbar,
            append,
            clear,
            setText,
            trimToMaxLines,
            scrollToBottom,
            show,
            hide,
            getAutoscroll: () => autoscroll,
            getMaxLines: () => maxLines,
        };
        outputEl.dataset.dbqTerminalAttached = '1';
        outputEl._dbqTerminal = api;
        return api;
    }

    global.DbqTerminal = {
        attach,
        DEFAULT_MAX_LINES,
    };
})(window);
