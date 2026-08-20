/**
 * operations.js — Operations page: upcoming event feed + kanban print.
 * Auto-refreshes every 5 minutes. Print uses browser native print dialog.
 * Clickable cards open a detail modal with Take / Complete / Unassign actions.
 */

(function () {
    'use strict';

    let currentSlots = [];
    let autoRefreshTimer = null;
    const AUTO_REFRESH_MS = 30 * 1000; // 30 s — keeps op-event state in sync across browsers

    const hoursSelect    = document.getElementById('hours-select');
    const showAllCheck   = document.getElementById('ops-show-all');
    const showMineCheck  = document.getElementById('ops-show-mine');
    const showRunningCheck = document.getElementById('ops-show-running');
    const testModeCheck  = document.getElementById('ops-test-mode');
    const testAtInput    = document.getElementById('ops-test-at');
    const testBadge      = document.getElementById('ops-test-badge');
    const refreshBtn     = document.getElementById('ops-refresh-btn');
    const printBtn       = document.getElementById('ops-print-btn');
    const kanbanGrid     = document.getElementById('kanban-grid');
    const placeholder    = document.getElementById('ops-placeholder');
    const countLabel     = document.getElementById('ops-count-label');
    const liveDot        = document.getElementById('ops-live-dot');
    const printArea      = document.getElementById('print-area');
    const printCards     = document.getElementById('print-cards');
    const printTitle     = document.getElementById('print-title');
    const printMeta      = document.getElementById('print-meta');

    // Modal elements
    const modalOverlay       = document.getElementById('ops-modal-overlay');
    const modalEl            = document.getElementById('ops-modal');
    const modalClose         = document.getElementById('ops-modal-close');
    const modalTrackBar      = document.getElementById('ops-modal-track-bar');
    const modalTime          = document.getElementById('ops-modal-time');
    const modalRoom          = document.getElementById('ops-modal-room');
    const modalTitle         = document.getElementById('ops-modal-title');
    const modalSpeakers      = document.getElementById('ops-modal-speakers');
    const modalStatus        = document.getElementById('ops-modal-status');
    const modalActions       = document.getElementById('ops-modal-actions');
    const modalResSection    = document.getElementById('ops-modal-resources-section');
    const modalResList       = document.getElementById('ops-modal-resources');
    const modalCmtSection    = document.getElementById('ops-modal-comments-section');
    const modalCmtList       = document.getElementById('ops-modal-comments');
    const modalConflict      = document.getElementById('ops-modal-conflict');
    const btnTake            = document.getElementById('ops-btn-take');
    const btnComplete        = document.getElementById('ops-btn-complete');
    const btnUnassign        = document.getElementById('ops-btn-unassign');

    // Track which slot is currently shown in the modal
    let activeSlot = null;

    // ---------------------------------------------------------------------------
    // Load upcoming
    // ---------------------------------------------------------------------------

    async function loadUpcoming() {
        const hours   = hoursSelect?.value || 4;
        const showAll = showAllCheck?.checked ? '&all=1' : '';
        const mine    = showMineCheck?.checked ? '&mine=1' : '';
        const running = showRunningCheck?.checked ? '&running=1' : '';

        // Build optional ?at= parameter for test mode
        let atParam = '';
        if (testModeCheck?.checked && testAtInput?.value) {
            atParam = '&at=' + encodeURIComponent(testAtInput.value);
        }

        showLoadingState();

        try {
            const data = await apiFetch(`/api/upcoming?hours=${hours}${showAll}${mine}${running}${atParam}`);
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
        const isCompleted = slot.is_completed;
        const isAssigned  = !!slot.assigned_to;
        const isRunning   = !!slot.is_running;
        let cls = `kanban-card${slot.has_conflict ? ' has-conflict' : ''}`;
        if (isCompleted) cls += ' ops-card-completed';
        else if (isAssigned) cls += ' ops-card-assigned';
        if (isRunning) cls += ' ops-card-running';

        const card = el('div', { cls });
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');
        card.setAttribute('aria-label', `Open details for ${slot.title}`);
        card.dataset.code      = slot.code;
        card.dataset.slotIndex = slot.slot_index;

        // Clickable — open modal
        card.addEventListener('click', () => openModal(slot));
        card.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openModal(slot); }
        });

        // Track color bar
        const colorBar = el('div', { cls: 'kanban-card-track' });
        colorBar.style.background = slot.track?.color || '#3b82f6';
        card.appendChild(colorBar);

        const body = el('div', { cls: 'kanban-card-body' });

        // Status badge row
        if (isRunning || isCompleted || isAssigned) {
            const statusRow = el('div', { cls: 'kanban-card-status-row' });
            if (isRunning) {
                const badge = el('span', { cls: 'ops-status-badge ops-badge-running' });
                badge.textContent = '▶ Now running';
                statusRow.appendChild(badge);
            }
            if (isCompleted) {
                const badge = el('span', { cls: 'ops-status-badge ops-badge-completed' });
                badge.textContent = '✔ Completed';
                statusRow.appendChild(badge);
            } else if (isAssigned) {
                const badge = el('span', { cls: 'ops-status-badge ops-badge-assigned' });
                badge.textContent = `✋ ${slot.assigned_to}`;
                statusRow.appendChild(badge);
            }
            body.appendChild(statusRow);
        }

        // Time + Room (same row)
        const timeRow = el('div', { cls: 'kanban-time-row' });
        const time = el('span', { cls: 'kanban-time' });
        time.textContent = `${fmtWeekday(slot.start)} ${fmtTimeRange(slot.start, slot.end)}`;
        timeRow.appendChild(time);
        const room = el('span', { cls: 'kanban-room' });
        room.textContent = slot.room_name || '—';
        timeRow.appendChild(room);
        body.appendChild(timeRow);

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
    // Modal
    // ---------------------------------------------------------------------------

    function openModal(slot) {
        activeSlot = slot;

        // Header
        if (modalTrackBar) modalTrackBar.style.background = slot.track?.color || '#3b82f6';
        if (modalTime)     modalTime.textContent = fmtTimeRange(slot.start, slot.end);
        if (modalRoom)     modalRoom.textContent = slot.room_name || '—';
        if (modalTitle)    modalTitle.textContent = slot.title;

        if (modalSpeakers) {
            modalSpeakers.textContent = slot.speakers?.length
                ? slot.speakers.map(s => s.telegram ? `${s.name} (@${s.telegram})` : s.name).join(' · ')
                : '';
        }

        // Status + action buttons
        refreshModalStatus(slot);

        // Resources
        if (modalResSection && modalResList) {
            modalResList.textContent = '';
            if (slot.resources?.length) {
                modalResSection.classList.remove('hidden');
                for (const r of slot.resources) {
                    const item = el('div', { cls: 'ops-modal-resource-item' });
                    const nameEl = el('span', { cls: 'ops-modal-resource-name' });
                    nameEl.textContent = r.resource_name;
                    item.appendChild(nameEl);
                    if (r.note) {
                        const noteEl = el('span', { cls: 'ops-modal-resource-note' });
                        noteEl.textContent = ` (${r.note})`;
                        item.appendChild(noteEl);
                    }
                    const depts = r.department_override
                        ? [r.department_override]
                        : (r.resource_departments || []);
                    const dw = el('span');
                    dw.style.marginLeft = '8px';
                    for (const d of depts) dw.appendChild(deptPill(d));
                    item.appendChild(dw);
                    modalResList.appendChild(item);
                }
            } else {
                modalResSection.classList.add('hidden');
            }
        }

        // Comments
        if (modalCmtSection && modalCmtList) {
            modalCmtList.textContent = '';
            if (slot.comments?.length) {
                modalCmtSection.classList.remove('hidden');
                for (const c of slot.comments) {
                    const item = el('div', { cls: 'ops-modal-comment-item' });
                    item.appendChild(deptPill(c.department));
                    const textEl = el('span');
                    textEl.style.marginLeft = '8px';
                    textEl.textContent = c.text;
                    item.appendChild(textEl);
                    modalCmtList.appendChild(item);
                }
            } else {
                modalCmtSection.classList.add('hidden');
            }
        }

        // Conflict
        if (modalConflict) {
            modalConflict.classList.toggle('hidden', !slot.has_conflict);
        }

        // Show modal
        modalOverlay?.classList.remove('hidden');
        modalClose?.focus();
    }

    function closeModal() {
        modalOverlay?.classList.add('hidden');
        activeSlot = null;
    }

    function refreshModalStatus(slot) {
        if (!modalStatus) return;

        modalStatus.textContent = '';
        modalStatus.className = 'ops-modal-status';

        if (slot.is_completed) {
            modalStatus.classList.add('ops-modal-status-completed');
            const icon = el('span');
            icon.textContent = '✔ Completed';
            modalStatus.appendChild(icon);
        } else if (slot.assigned_to) {
            modalStatus.classList.add('ops-modal-status-assigned');
            const icon = el('span');
            icon.textContent = `✋ Taken by ${slot.assigned_to}`;
            modalStatus.appendChild(icon);
        } else {
            modalStatus.classList.add('ops-modal-status-open');
            const icon = el('span');
            icon.textContent = '◯ Not assigned';
            modalStatus.appendChild(icon);
        }

        // Update action button states
        if (btnUnassign) {
            btnUnassign.disabled = !slot.assigned_to && !slot.is_completed;
        }
    }

    function updateSlotState(slot, assigned_to, is_completed) {
        slot.assigned_to  = assigned_to;
        slot.is_completed = is_completed;

        // Refresh modal status
        refreshModalStatus(slot);

        // Refresh the card in the grid
        const card = kanbanGrid.querySelector(
            `.kanban-card[data-code="${CSS.escape(slot.code)}"][data-slot-index="${slot.slot_index}"]`
        );
        if (card) {
            const newCard = makeKanbanCard(slot);
            card.replaceWith(newCard);
        }
    }

    // Modal action buttons
    btnTake?.addEventListener('click', async () => {
        if (!activeSlot) return;
        setActionBusy(true);
        try {
            const res = await apiFetch(
                `/api/slots/${encodeURIComponent(activeSlot.code)}/${activeSlot.slot_index}/take`,
                { method: 'POST' }
            );
            updateSlotState(activeSlot, res.assigned_to, res.is_completed);
            showToast('Event taken — you are now assigned.', 'success');
        } catch (e) {
            showToast('Failed to take event: ' + e.message, 'error');
        } finally {
            setActionBusy(false);
        }
    });

    btnComplete?.addEventListener('click', async () => {
        if (!activeSlot) return;
        setActionBusy(true);
        try {
            const res = await apiFetch(
                `/api/slots/${encodeURIComponent(activeSlot.code)}/${activeSlot.slot_index}/complete`,
                { method: 'POST' }
            );
            updateSlotState(activeSlot, res.assigned_to, res.is_completed);
            showToast('Event marked as completed.', 'success');
        } catch (e) {
            showToast('Failed to complete event: ' + e.message, 'error');
        } finally {
            setActionBusy(false);
        }
    });

    btnUnassign?.addEventListener('click', async () => {
        if (!activeSlot) return;
        setActionBusy(true);
        try {
            const res = await apiFetch(
                `/api/slots/${encodeURIComponent(activeSlot.code)}/${activeSlot.slot_index}/unassign`,
                { method: 'POST' }
            );
            updateSlotState(activeSlot, res.assigned_to, res.is_completed);
            showToast('Event unassigned.', 'success');
        } catch (e) {
            showToast('Failed to unassign event: ' + e.message, 'error');
        } finally {
            setActionBusy(false);
        }
    });

    function setActionBusy(busy) {
        [btnTake, btnComplete, btnUnassign].forEach(b => {
            if (b) b.disabled = busy;
        });
    }

    // Close modal on overlay click / Escape
    modalOverlay?.addEventListener('click', e => {
        if (e.target === modalOverlay) closeModal();
    });
    modalClose?.addEventListener('click', closeModal);
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && activeSlot) closeModal();
    });

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
            const refresh = isTest ? '' : ' — auto-refreshes every 30 s';
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
        time.textContent = `${fmtWeekday(slot.start)} ${fmtTimeRange(slot.start, slot.end)}`;
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

    showMineCheck?.addEventListener('change', () => {
        loadUpcoming();
    });

    showRunningCheck?.addEventListener('change', () => {
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
