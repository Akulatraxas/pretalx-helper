/**
 * operations.js — Operations page: upcoming event feed + kanban print.
 * Auto-refreshes every 5 minutes. Print uses browser native print dialog.
 */

(function () {
    'use strict';

    let currentSlots = [];
    let autoRefreshTimer = null;
    const AUTO_REFRESH_MS = 5 * 60 * 1000;

    const hoursSelect = document.getElementById('hours-select');
    const showAllCheck = document.getElementById('ops-show-all');
    const testModeCheck = document.getElementById('ops-test-mode');
    const testAtInput = document.getElementById('ops-test-at');
    const testBadge = document.getElementById('ops-test-badge');
    const refreshBtn = document.getElementById('ops-refresh-btn');
    const printBtn = document.getElementById('ops-print-btn');
    const kanbanGrid = document.getElementById('kanban-grid');
    const placeholder = document.getElementById('ops-placeholder');
    const countLabel = document.getElementById('ops-count-label');
    const liveDot = document.getElementById('ops-live-dot');
    const printArea = document.getElementById('print-area');
    const printCards = document.getElementById('print-cards');
    const printTitle = document.getElementById('print-title');
    const printMeta = document.getElementById('print-meta');

    // ---------------------------------------------------------------------------
    // Load upcoming
    // ---------------------------------------------------------------------------

    async function loadUpcoming() {
        const hours = hoursSelect?.value || 4;
        const showAll = showAllCheck?.checked ? '&all=1' : '';

        // Build optional ?at= parameter for test mode
        let atParam = '';
        if (testModeCheck?.checked && testAtInput?.value) {
            atParam = '&at=' + encodeURIComponent(testAtInput.value);
        }

        showLoadingState();

        try {
            const data = await apiFetch(`/api/upcoming?hours=${hours}${showAll}${atParam}`);
            currentSlots = data.slots || [];
            renderGrid();
            updateStatus(data);
        } catch (e) {
            showToast('Failed to load upcoming events: ' + e.message, 'error');
            showEmpty();
        }
    }

    function showLoadingState() {
        if (placeholder) placeholder.style.display = 'block';
        // Remove old cards but keep placeholder
        kanbanGrid.querySelectorAll('.kanban-card').forEach(c => c.remove());
        if (countLabel) countLabel.textContent = 'Loading…';
    }

    function showEmpty() {
        if (placeholder) {
            placeholder.style.display = 'block';
            const span = placeholder.querySelector('span') || placeholder;
            span.textContent = 'No upcoming events.';
        }
    }

    // ---------------------------------------------------------------------------
    // Render kanban grid
    // ---------------------------------------------------------------------------

    function renderGrid() {
        kanbanGrid.querySelectorAll('.kanban-card, .ops-empty').forEach(c => c.remove());
        if (placeholder) placeholder.style.display = 'none';

        if (currentSlots.length === 0) {
            const empty = el('div', { cls: 'ops-empty' });
            empty.textContent = 'No events in this time window with assignments.';
            kanbanGrid.appendChild(empty);
            return;
        }

        for (const slot of currentSlots) {
            kanbanGrid.appendChild(makeKanbanCard(slot));
        }
    }

    function makeKanbanCard(slot) {
        const card = el('div', { cls: `kanban-card${slot.has_conflict ? ' has-conflict' : ''}` });

        // Track color bar
        const colorBar = el('div', { cls: 'kanban-card-track' });
        colorBar.style.background = slot.track?.color || '#3b82f6';
        card.appendChild(colorBar);

        const body = el('div', { cls: 'kanban-card-body' });

        // Time + Room (same row)
        const timeRow = el('div', { cls: 'kanban-time-row' });
        const time = el('span', { cls: 'kanban-time' });
        time.textContent = fmtTimeRange(slot.start, slot.end);
        timeRow.appendChild(time);
        const room = el('span', { cls: 'kanban-room' });
        room.textContent = slot.room_name || '—';
        timeRow.appendChild(room);
        body.appendChild(timeRow);

        // Code - Remove for now, just use code for URLs
        //const codeEl = el('div', { cls: 'kanban-code' });
        //codeEl.textContent = slot.code;
        //body.appendChild(codeEl);

        // Title
        const title = el('div', { cls: 'kanban-title' });
        title.textContent = slot.title;
        body.appendChild(title);

        // Speakers
        if (slot.speakers?.length) {
            const spEl = el('div', { cls: 'kanban-speakers' });
            spEl.textContent = slot.speakers.map(s =>
                s.telegram ? `${s.name} (${s.telegram})` : s.name
            ).join(', ');
            body.appendChild(spEl);
        }

        // Resources
        if (slot.resources?.length) {
            const resSection = el('div', { cls: 'kanban-resources' });
            const label = el('div', { cls: 'kanban-section-label' });
            label.textContent = 'Resources';
            resSection.appendChild(label);
            for (const r of slot.resources) {
                const item = el('div', { cls: 'kanban-resource-item' });
                const nameEl = el('span');
                nameEl.textContent = r.resource_name;
                item.appendChild(nameEl);
                if (r.note) {
                    const noteEl = el('span', { cls: 'kanban-resource-note' });
                    noteEl.textContent = ` (${r.note})`;
                    item.appendChild(noteEl);
                }
                const depts = r.department_override
                    ? [r.department_override]
                    : (r.resource_departments || []);
                const dw = el('span');
                dw.style.marginLeft = '6px';
                for (const d of depts) dw.appendChild(deptPill(d));
                item.appendChild(dw);
                resSection.appendChild(item);
            }
            body.appendChild(resSection);
        }

        // Comments
        if (slot.comments?.length) {
            const cmtSection = el('div', { cls: 'kanban-comments' });
            const label = el('div', { cls: 'kanban-section-label' });
            label.textContent = 'Notes';
            cmtSection.appendChild(label);
            for (const c of slot.comments) {
                const item = el('div', { cls: 'kanban-comment-item' });
                item.appendChild(deptPill(c.department));
                const textEl = el('span');
                textEl.style.marginLeft = '6px';
                textEl.textContent = c.text;
                item.appendChild(textEl);
                cmtSection.appendChild(item);
            }
            body.appendChild(cmtSection);
        }

        // Conflict warning
        if (slot.has_conflict) {
            const warn = el('div', { style: { marginTop: '8px' } });
            const badge = el('span', { cls: 'output-conflict-flag' });
            badge.textContent = '⚠ Resource conflict';
            warn.appendChild(badge);
            body.appendChild(warn);
        }

        card.appendChild(body);
        return card;
    }

    // ---------------------------------------------------------------------------
    // Status bar
    // ---------------------------------------------------------------------------

    function updateStatus(data = {}) {
        if (countLabel) {
            const n = currentSlots.length;
            const hours = hoursSelect?.value || 4;
            const isTest = data.is_test_mode || false;
            let refLabel = '';
            if (isTest && data.reference_time) {
                try {
                    const d = new Date(data.reference_time);
                    refLabel = ` · ref: ${d.toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}`;
                } catch (_) { }
            }
            const refresh = isTest ? '' : ' — auto-refreshes every 5 min';
            countLabel.textContent = `${n} slot${n !== 1 ? 's' : ''} in the next ${hours} hour${hours > 1 ? 's' : ''}${refLabel}${refresh}`;
        }
        if (liveDot) liveDot.className = 'status-dot ok';
    }

    // ---------------------------------------------------------------------------
    // Print
    // ---------------------------------------------------------------------------

    printBtn?.addEventListener('click', () => {
        if (!printArea || !printCards) return;
        buildPrintArea();
        printArea.classList.remove('hidden');
        printArea.removeAttribute('aria-hidden');
        window.print();
        // After print dialog closes, hide print area again
        printArea.classList.add('hidden');
        printArea.setAttribute('aria-hidden', 'true');
    });

    function buildPrintArea() {
        printCards.innerHTML = '';
        if (printTitle) {
            printTitle.textContent = `Operations — Next ${hoursSelect?.value || 4} Hours`;
        }
        if (printMeta) {
            printMeta.textContent = `Generated: ${new Date().toLocaleString()}`;
        }

        for (const slot of currentSlots) {
            printCards.appendChild(makePrintCard(slot));
        }
    }

    function makePrintCard(slot) {
        const card = el('div', { cls: 'print-card' });

        // Track color bar
        const bar = el('div', { cls: 'print-card-track-bar' });
        bar.style.background = slot.track?.color || '#3b82f6';
        card.appendChild(bar);

        const body = el('div', { cls: 'print-card-body' });

        const timeRow = el('div', { cls: 'print-card-time-row' });
        const time = el('span', { cls: 'print-card-time' });
        time.textContent = fmtTimeRange(slot.start, slot.end);
        timeRow.appendChild(time);
        const room = el('span', { cls: 'print-card-room' });
        room.textContent = slot.room_name || '—';
        timeRow.appendChild(room);
        body.appendChild(timeRow);

        const code = el('div', { cls: 'print-card-code' });
        code.textContent = slot.code;
        body.appendChild(code);

        const title = el('div', { cls: 'print-card-title' });
        title.textContent = slot.title;
        body.appendChild(title);

        if (slot.speakers?.length) {
            const sp = el('div', { cls: 'print-card-speakers' });
            sp.textContent = slot.speakers.map(s =>
                s.telegram ? `${s.name} (@${s.telegram})` : s.name
            ).join(', ');
            body.appendChild(sp);
        }

        if (slot.resources?.length) {
            const label = el('div', { cls: 'print-card-section-label' });
            label.textContent = 'Resources';
            body.appendChild(label);
            for (const r of slot.resources) {
                const item = el('div', { cls: 'print-card-resource' });
                item.textContent = r.resource_name + (r.note ? ` (${r.note})` : '');
                body.appendChild(item);
            }
        }

        if (slot.comments?.length) {
            const label = el('div', { cls: 'print-card-section-label' });
            label.textContent = 'Notes';
            body.appendChild(label);
            for (const c of slot.comments) {
                const item = el('div', { cls: 'print-card-comment' });
                item.textContent = `[${c.department}] ${c.text}`;
                body.appendChild(item);
            }
        }

        if (slot.has_conflict) {
            const warn = el('div', { cls: 'print-card-conflict' });
            warn.textContent = '⚠ Resource conflict detected';
            body.appendChild(warn);
        }

        card.appendChild(body);
        return card;
    }

    // ---------------------------------------------------------------------------
    // Auto-refresh
    // ---------------------------------------------------------------------------

    function scheduleAutoRefresh() {
        clearTimeout(autoRefreshTimer);
        autoRefreshTimer = setTimeout(async () => {
            if (liveDot) liveDot.className = 'status-dot loading';
            await loadUpcoming();
            scheduleAutoRefresh();
        }, AUTO_REFRESH_MS);
    }

    // ---------------------------------------------------------------------------
    // Controls
    // ---------------------------------------------------------------------------

    hoursSelect?.addEventListener('change', () => {
        loadUpcoming();
        if (!testModeCheck?.checked) scheduleAutoRefresh();
    });

    showAllCheck?.addEventListener('change', () => {
        loadUpcoming();
    });

    // Test mode toggle: show/hide the datetime picker
    testModeCheck?.addEventListener('change', () => {
        const isTest = testModeCheck.checked;
        testAtInput?.classList.toggle('hidden', !isTest);
        testBadge?.classList.toggle('hidden', !isTest);
        if (isTest) {
            // Default to the first event's date in the schedule if we know it,
            // otherwise leave as-is. The user can adjust.
            clearTimeout(autoRefreshTimer);  // pause auto-refresh in test mode
            if (testAtInput && !testAtInput.value) {
                // Pre-fill with a value 1 week from now as a starting hint
                const hint = new Date();
                hint.setDate(hint.getDate() + 7);
                hint.setMinutes(0, 0, 0);
                testAtInput.value = hint.toISOString().slice(0, 16);
            }
        } else {
            scheduleAutoRefresh();  // resume auto-refresh
        }
        loadUpcoming();
    });

    // Re-fetch when the datetime picker changes (debounced so typing doesn't spam)
    testAtInput?.addEventListener('change', debounce(() => {
        if (testModeCheck?.checked) loadUpcoming();
    }, 400));

    refreshBtn?.addEventListener('click', async () => {
        refreshBtn.disabled = true;
        if (liveDot) liveDot.className = 'status-dot loading';
        await loadUpcoming();
        if (!testModeCheck?.checked) scheduleAutoRefresh();
        refreshBtn.disabled = false;
    });

    // ---------------------------------------------------------------------------
    // Boot
    // ---------------------------------------------------------------------------

    loadUpcoming().then(() => scheduleAutoRefresh());

})();
