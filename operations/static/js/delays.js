/**
 * delays.js — Delays & Changes page.
 *
 * Left column: upcoming events feed (running + starting within 4 h),
 *   each card shows event info in the same style as usage-event-card.
 *   "Add Delay" / "Change Delay" buttons open a modal to set minutes + comment.
 *
 * Right column: Changes — placeholder (not yet implemented).
 *
 * Auto-refreshes every 30 s (paused while the modal is open).
 */

(function () {
    'use strict';

    const AUTO_REFRESH_MS = 30_000;

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    let currentSlots   = [];
    let currentChanges = [];
    let autoTimer      = null;
    let modalSlot      = null;   // slot being edited in modal

    // -------------------------------------------------------------------------
    // DOM refs
    // -------------------------------------------------------------------------

    const list        = document.getElementById('del-list');
    const placeholder = document.getElementById('del-placeholder');
    const changesList = document.getElementById('del-changes-list');
    const countLabel  = document.getElementById('del-count-label');
    const liveDot     = document.getElementById('del-live-dot');
    const refreshBtn  = document.getElementById('del-refresh-btn');
    const testModeChk = document.getElementById('del-test-mode');
    const testAtInput = document.getElementById('del-test-at');
    const testBadge   = document.getElementById('del-test-badge');

    const modalOverlay  = document.getElementById('del-modal-overlay');
    const modalTitle    = document.getElementById('del-modal-title');
    const modalEventInfo= document.getElementById('del-modal-event-info');
    const modalForm     = document.getElementById('del-modal-form');
    const minutesInput  = document.getElementById('del-minutes-input');
    const commentInput  = document.getElementById('del-comment-input');
    const saveBtn       = document.getElementById('del-modal-save');
    const cancelBtn     = document.getElementById('del-modal-cancel');
    const clearBtn      = document.getElementById('del-modal-clear');
    const closeBtn      = document.getElementById('del-modal-close');

    // -------------------------------------------------------------------------
    // Load data
    /**
     * Loads the delay and pending-change feeds and updates their displays.
     * Displays an error state when either feed fails to load.
     */

    async function load() {
        if (liveDot) liveDot.className = 'status-dot loading';

        const params = new URLSearchParams();
        if (testModeChk?.checked && testAtInput?.value) {
            params.set('at', testAtInput.value);
        }

        try {
            // Fetch both feeds in parallel
            const [delayData, changesData] = await Promise.all([
                apiFetch('/api/delays?' + params),
                apiFetch('/api/changes'),
            ]);

            currentSlots   = delayData.slots   || [];
            currentChanges = changesData.changes || [];
            render();
            renderChanges();

            if (countLabel) {
                const n      = currentSlots.length;
                const isTest = delayData.is_test_mode || false;
                let refLabel = '';
                if (isTest && delayData.reference_time) {
                    try {
                        const d = new Date(delayData.reference_time);
                        refLabel = ' · ref: ' + d.toLocaleString('en-GB', {
                            weekday: 'short', day: 'numeric', month: 'short',
                            hour: '2-digit', minute: '2-digit',
                        });
                    } catch (_) {}
                }
                const suffix = isTest ? '' : ' — auto-refreshes every 30 s';
                countLabel.textContent = n + ' event' + (n !== 1 ? 's' : '') + ' in window' + refLabel + suffix;
            }
            if (liveDot) liveDot.className = 'status-dot ok';
        } catch (e) {
            showToast('Failed to load delays feed: ' + e.message, 'error');
            if (liveDot) liveDot.className = 'status-dot error';
            list.textContent = '';
            const errEl = el('p', { cls: 'delays-status-msg' });
            errEl.textContent = '⚠ Error loading events — ' + e.message;
            list.appendChild(errEl);
        }
    }

    // -------------------------------------------------------------------------
    // Render event list
    /**
     * Renders the current event slots in the event list.
     */

    function render() {
        list.textContent = '';

        if (currentSlots.length === 0) {
            const msg = el('p', { cls: 'delays-status-msg' });
            msg.textContent = 'No events in the next 4 hours.';
            list.appendChild(msg);
            return;
        }

        for (const slot of currentSlots) {
            list.appendChild(makeCard(slot));
        }
    }

    // -------------------------------------------------------------------------
    // Build one event card  (usage-event-card style + delay badge + action btn)
    /**
     * Builds a display card for an event slot, including its schedule, speakers, delay details, and available actions.
     * @param {Object} slot - Event slot data used to populate the card.
     * @return {HTMLElement} The rendered event card.
     */

    function makeCard(slot) {
        const hasDelay  = slot.delay_minutes != null;
        const isRunning = slot.is_running;

        const card = el('div', { cls: 'usage-event-card delays-event-card'
            + (hasDelay  ? ' delays-card-delayed'  : '')
            + (isRunning ? ' delays-card-running'  : '') });

        // Track colour bar
        const bar = el('div', { cls: 'delays-track-bar' });
        bar.style.background = slot.track?.color || 'var(--accent-primary)';
        card.appendChild(bar);

        const inner = el('div', { cls: 'delays-card-inner' });

        // ── Title row ──
        const titleRow = el('div', { cls: 'usage-event-title-row' });

        const codeEl = el('span', { cls: 'usage-event-code' });
        codeEl.textContent = slot.code;
        titleRow.appendChild(codeEl);

        if (isRunning) {
            const nowBadge = el('span', { cls: 'delays-running-badge' });
            nowBadge.textContent = '● Now';
            titleRow.appendChild(nowBadge);
        }

        const titleEl = el('span', { cls: 'usage-event-title' });
        titleEl.textContent = slot.title;
        titleRow.appendChild(titleEl);

        inner.appendChild(titleRow);

        // ── Slot time + room ──
        const slotRow = el('div', { cls: 'usage-event-slots' });
        const slotEl  = el('div', { cls: 'usage-slot' });

        const timeEl = el('span', { cls: 'usage-slot-time' });
        timeEl.textContent = fmtDate(slot.start) + ' · ' + fmtTimeRange(slot.start, slot.end);
        slotEl.appendChild(timeEl);

        if (slot.room_name) {
            const roomEl = el('span', { cls: 'usage-slot-room' });
            roomEl.textContent = ' @ ' + slot.room_name;
            slotEl.appendChild(roomEl);
        }
        slotRow.appendChild(slotEl);
        inner.appendChild(slotRow);

        // ── Speakers ──
        if ((slot.speakers || []).length > 0) {
            const spEl = el('div', { cls: 'usage-event-speakers' });
            spEl.textContent = slot.speakers.map(s => s.name).join(', ');
            inner.appendChild(spEl);
        }

        // ── Active delay badge ──
        if (hasDelay) {
            const delayBadge = el('div', { cls: 'delays-badge' });

            const icon = el('span', { cls: 'delays-badge-icon' });
            icon.textContent = '⏱';
            delayBadge.appendChild(icon);

            const minEl = el('span', { cls: 'delays-badge-minutes' });
            minEl.textContent = '+' + slot.delay_minutes + ' min';
            delayBadge.appendChild(minEl);

            if (slot.delay_comment) {
                const sep = document.createTextNode(' · ');
                delayBadge.appendChild(sep);
                const cmtEl = el('span', { cls: 'delays-badge-comment' });
                cmtEl.textContent = slot.delay_comment;
                delayBadge.appendChild(cmtEl);
            }

            if (slot.delay_set_by) {
                const byEl = el('span', { cls: 'delays-badge-by' });
                byEl.textContent = ' set by ' + slot.delay_set_by;
                delayBadge.appendChild(byEl);
            }

            inner.appendChild(delayBadge);
        }

        // ── Action button ──
        if (CAN_WRITE) {
            const actionRow = el('div', { cls: 'delays-card-actions' });
            const actionBtn = el('button', {
                type: 'button',
                cls: hasDelay ? 'btn btn-sm btn-warning' : 'btn btn-sm btn-primary',
                id: 'delay-btn-' + slot.code + '-' + slot.slot_index,
            });
            actionBtn.textContent = hasDelay ? '✏ Change Delay' : '+ Add Delay';
            actionBtn.addEventListener('click', () => openModal(slot));
            actionRow.appendChild(actionBtn);
            inner.appendChild(actionRow);
        }

        card.appendChild(inner);
        return card;
    }

    // -------------------------------------------------------------------------
    // Modal — open / close / submit
    /**
     * Opens the delay modal for an event slot and populates its current delay details.
     * @param {Object} slot - The event slot to edit.
     */

    function openModal(slot) {
        modalSlot = slot;
        const hasDelay = slot.delay_minutes != null;

        if (modalTitle) modalTitle.textContent = hasDelay ? 'Change Delay' : 'Add Delay';

        // Event info summary inside modal
        if (modalEventInfo) {
            modalEventInfo.textContent = '';

            const titleEl = el('div', { cls: 'delays-modal-event-title' });
            titleEl.textContent = slot.title;
            modalEventInfo.appendChild(titleEl);

            const metaEl = el('div', { cls: 'delays-modal-event-meta' });
            metaEl.textContent = fmtTimeRange(slot.start, slot.end)
                + (slot.room_name ? ' @ ' + slot.room_name : '');
            modalEventInfo.appendChild(metaEl);
        }

        // Pre-fill fields if there's an existing delay
        if (minutesInput) minutesInput.value = hasDelay ? slot.delay_minutes : '';
        if (commentInput) commentInput.value = hasDelay ? (slot.delay_comment || '') : '';

        // Show/hide Clear button
        if (clearBtn) clearBtn.classList.toggle('hidden', !hasDelay);

        if (saveBtn) saveBtn.textContent = hasDelay ? 'Update Delay' : 'Save Delay';

        clearTimeout(autoTimer);
        modalOverlay?.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        minutesInput?.focus();
    }

    /**
     * Closes the delay modal and resumes automatic refresh scheduling.
     */
    function closeModal() {
        modalOverlay?.classList.add('hidden');
        document.body.style.overflow = '';
        modalSlot = null;
        scheduleRefresh();
    }

    /**
     * Saves the delay entered for the active event slot.
     * @param {SubmitEvent} e - The form submission event.
     */
    async function submitDelay(e) {
        e.preventDefault();
        if (!modalSlot) return;

        const minutes = parseInt(minutesInput?.value || '0', 10);
        if (!minutes || minutes < 1 || minutes > 1440) {
            showToast('Please enter a delay between 1 and 1440 minutes.', 'error');
            minutesInput?.focus();
            return;
        }

        const comment = (commentInput?.value || '').trim();

        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }

        try {
            await apiFetch(
                `/api/slots/${encodeURIComponent(modalSlot.code)}/${modalSlot.slot_index}/delay`,
                { method: 'POST', body: JSON.stringify({ minutes, comment }) }
            );
            showToast('Delay saved — ' + modalSlot.title, 'success');
            closeModal();
            await load();
        } catch (err) {
            showToast('Failed to save delay: ' + err.message, 'error');
        } finally {
            if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save Delay'; }
        }
    }

    /**
     * Clears the delay for the active event slot.
     */
    async function clearDelay() {
        if (!modalSlot) return;

        if (clearBtn) { clearBtn.disabled = true; clearBtn.textContent = 'Clearing…'; }

        try {
            await apiFetch(
                `/api/slots/${encodeURIComponent(modalSlot.code)}/${modalSlot.slot_index}/delay`,
                { method: 'DELETE' }
            );
            showToast('Delay cleared — ' + modalSlot.title, 'success');
            closeModal();
            await load();
        } catch (err) {
            showToast('Failed to clear delay: ' + err.message, 'error');
        } finally {
            if (clearBtn) { clearBtn.disabled = false; clearBtn.textContent = 'Clear Delay'; }
        }
    }

    // -------------------------------------------------------------------------
    // Event listeners
    // -------------------------------------------------------------------------

    modalForm?.addEventListener('submit', submitDelay);
    saveBtn?.addEventListener('click', submitDelay);
    cancelBtn?.addEventListener('click', closeModal);
    closeBtn?.addEventListener('click', closeModal);
    clearBtn?.addEventListener('click', clearDelay);

    modalOverlay?.addEventListener('click', (ev) => {
        if (ev.target === modalOverlay) closeModal();
    });

    document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && !modalOverlay?.classList.contains('hidden')) closeModal();
    });

    refreshBtn?.addEventListener('click', async () => {
        refreshBtn.disabled = true;
        await load();
        scheduleRefresh();
        refreshBtn.disabled = false;
    });

    testModeChk?.addEventListener('change', () => {
        const isTest = testModeChk.checked;
        testAtInput?.classList.toggle('hidden', !isTest);
        testBadge?.classList.toggle('hidden', !isTest);
        if (isTest) {
            clearTimeout(autoTimer);
            if (testAtInput && !testAtInput.value) {
                const hint = new Date();
                hint.setDate(hint.getDate() + 7);
                hint.setMinutes(0, 0, 0);
                testAtInput.value = hint.toISOString().slice(0, 16);
            }
        } else {
            scheduleRefresh();
        }
        load();
    });

    testAtInput?.addEventListener('change', debounce(() => {
        if (testModeChk?.checked) load();
    }, 400));

    // -------------------------------------------------------------------------
    // Auto-refresh (paused while modal is open)
    /**
     * Schedules the next automatic data refresh unless test mode is active.
     * Defers the refresh while the delay modal is open.
     */

    function scheduleRefresh() {
        clearTimeout(autoTimer);
        if (testModeChk?.checked) return;   // no auto-refresh in test mode
        autoTimer = setTimeout(async () => {
            if (!modalOverlay?.classList.contains('hidden')) {
                scheduleRefresh();
                return;
            }
            if (liveDot) liveDot.className = 'status-dot loading';
            await load();
            scheduleRefresh();
        }, AUTO_REFRESH_MS);
    }

    // -------------------------------------------------------------------------
    // Boot
    // -------------------------------------------------------------------------

    load().then(() => scheduleRefresh());

    // -------------------------------------------------------------------------
    // Changes column — render + actions
    // -------------------------------------------------------------------------

    const CHANGE_TYPE_LABELS = {
        new:         'New Event',
        cancelled:   'Cancelled',
        unscheduled: 'Unscheduled',
        day:         'Day moved',
        time:        'Time changed',
        room:        'Room changed',
    };
    const CHANGE_TYPE_ICONS = {
        new:         '✨',
        cancelled:   '❌',
        unscheduled: '🗓️',
        day:         '📅',
        time:        '🕒',
        room:        '🚶',
    };

    /**
     * Renders the current pending changes in the changes list.
     */
    function renderChanges() {
        if (!changesList) return;
        changesList.textContent = '';

        if (currentChanges.length === 0) {
            const msg = el('div', { cls: 'changes-empty' });
            const icon = el('div', { cls: 'changes-empty-icon' });
            icon.textContent = '✅';
            const p = el('p');
            p.textContent = 'No pending changes.';
            msg.appendChild(icon);
            msg.appendChild(p);
            changesList.appendChild(msg);
            return;
        }

        for (const chg of currentChanges) {
            changesList.appendChild(makeChangeCard(chg));
        }
    }

    /**
     * Builds a card displaying a pending event change and its before-and-after details.
     * @param {Object} chg - The pending change data used to populate the card.
     * @returns {HTMLElement} The rendered change card element.
     */
    function makeChangeCard(chg) {
        const isNew          = chg.change_types?.includes('new');
        const isCancelled    = chg.change_types?.includes('cancelled');
        const isUnscheduled  = chg.change_types?.includes('unscheduled');
        const isStatusChange = isNew || isCancelled || isUnscheduled;

        const card = el('div', {
            cls: 'changes-card'
                + (isNew         ? ' changes-card-new'         : '')
                + (isCancelled   ? ' changes-card-cancelled'   : '')
                + (isUnscheduled ? ' changes-card-unscheduled' : ''),
            'data-id': String(chg.id),
        });

        // Track bar
        const bar = el('div', { cls: 'delays-track-bar' });
        bar.style.background = chg.track?.color || 'var(--accent-primary)';
        card.appendChild(bar);

        const inner = el('div', { cls: 'changes-card-inner' });

        // ── Status banner or version row ──
        if (isStatusChange) {
            const banner = el('div', {
                cls: 'changes-status-banner changes-banner-'
                    + (isNew ? 'new' : isCancelled ? 'cancelled' : 'unscheduled'),
            });
            banner.textContent = isNew         ? '✨ New Event'
                                : isCancelled   ? '❌ Cancelled'
                                :                 '🗓️ Unscheduled';
            inner.appendChild(banner);
        } else {
            // Version badge row for reschedules
            const versionRow = el('div', { cls: 'changes-version-row' });
            const fromBadge  = el('span', { cls: 'changes-version-badge changes-version-from' });
            fromBadge.textContent = chg.from_version;
            const arrow = document.createTextNode(' → ');
            const toBadge = el('span', { cls: 'changes-version-badge changes-version-to' });
            toBadge.textContent = chg.to_version;
            versionRow.appendChild(fromBadge);
            versionRow.appendChild(arrow);
            versionRow.appendChild(toBadge);
            inner.appendChild(versionRow);
        }

        // ── Title ──
        const titleRow = el('div', { cls: 'usage-event-title-row' });
        const codeEl   = el('span', { cls: 'usage-event-code' });
        codeEl.textContent = chg.submission_code;
        const titleEl  = el('span', { cls: 'usage-event-title' });
        titleEl.textContent = chg.title || chg.submission_code;
        titleRow.appendChild(codeEl);
        titleRow.appendChild(titleEl);
        inner.appendChild(titleRow);

        // ── Change type pills ──
        const typesRow = el('div', { cls: 'changes-type-pills' });
        for (const t of (chg.change_types || [])) {
            const pill = el('span', { cls: 'changes-type-pill changes-type-' + t });
            pill.textContent = (CHANGE_TYPE_ICONS[t] || '') + ' ' + (CHANGE_TYPE_LABELS[t] || t);
            typesRow.appendChild(pill);
        }
        inner.appendChild(typesRow);

        // ── Before / After diff table ──
        const diff = el('div', { cls: 'changes-diff' });

        function diffRow(label, oldVal, newVal) {
            if (!oldVal && !newVal) return;
            const row = el('div', { cls: 'changes-diff-row' });
            const lbl = el('span', { cls: 'changes-diff-label' });
            lbl.textContent = label;
            const oldEl = el('span', { cls: oldVal && newVal ? 'changes-diff-old' : 'changes-diff-new' });
            oldEl.textContent = oldVal || '—';
            if (oldVal && newVal) {
                const sep = document.createTextNode(' → ');
                const newEl = el('span', { cls: 'changes-diff-new' });
                newEl.textContent = newVal;
                row.appendChild(lbl);
                row.appendChild(oldEl);
                row.appendChild(sep);
                row.appendChild(newEl);
            } else {
                row.appendChild(lbl);
                row.appendChild(oldEl);
            }
            diff.appendChild(row);
        }

        // Show available slot info (old for cancelled/unscheduled, new for new, both for reschedules)
        const hasOld = chg.old_start || chg.old_room;
        const hasNew = chg.new_start || chg.new_room;

        if ((isCancelled || isUnscheduled) && hasOld) {
            diffRow('Time', fmtDate(chg.old_start) + ' ' + fmtTimeRange(chg.old_start, chg.old_end), null);
            if (chg.old_room) diffRow('Room', chg.old_room, null);
        } else if (isNew && hasNew) {
            diffRow('Time', null, fmtDate(chg.new_start) + ' ' + fmtTimeRange(chg.new_start, chg.new_end));
            if (chg.new_room) diffRow('Room', null, chg.new_room);
        } else {
            if (chg.change_types?.includes('day') || chg.change_types?.includes('time')) {
                diffRow('Time',
                    fmtDate(chg.old_start) + ' ' + fmtTimeRange(chg.old_start, chg.old_end),
                    fmtDate(chg.new_start) + ' ' + fmtTimeRange(chg.new_start, chg.new_end)
                );
            }
            if (chg.change_types?.includes('room')) {
                diffRow('Room', chg.old_room, chg.new_room);
            }
        }

        inner.appendChild(diff);

        // ── Action buttons ──
        if (CAN_WRITE) {
            const actions = el('div', { cls: 'changes-actions' });

            const sendBtn = el('button', { type: 'button', cls: 'btn btn-sm btn-primary' });
            sendBtn.textContent = '📤 Send';
            sendBtn.addEventListener('click', () => actionChange(chg, 'send', card));

            const discardBtn = el('button', { type: 'button', cls: 'btn btn-sm btn-ghost' });
            discardBtn.textContent = '✕ Discard';
            discardBtn.addEventListener('click', () => actionChange(chg, 'discard', card));

            actions.appendChild(sendBtn);
            actions.appendChild(discardBtn);
            inner.appendChild(actions);
        }

        card.appendChild(inner);
        return card;
    }

    /**
     * Sends or discards a pending change and refreshes the changes feed after success.
     * @param {Object} chg - The pending change to process.
     * @param {string} action - The action to apply to the change.
     * @param {HTMLElement} cardEl - The change card whose controls are managed.
     */
    async function actionChange(chg, action, cardEl) {
        const btns = cardEl.querySelectorAll('button');
        btns.forEach(b => { b.disabled = true; });

        try {
            await apiFetch(`/api/changes/${chg.id}/${action}`, { method: 'POST' });
            const msg = action === 'send' ? 'Sent — ' : 'Discarded — ';
            showToast(msg + (chg.title || chg.submission_code), 'success');
            // Animate out then reload
            cardEl.style.transition = 'opacity 0.25s, transform 0.25s';
            cardEl.style.opacity = '0';
            cardEl.style.transform = 'scale(0.97)';
            setTimeout(async () => {
                cardEl.remove();
                // Refresh changes only
                try {
                    const d = await apiFetch('/api/changes');
                    currentChanges = d.changes || [];
                    renderChanges();
                } catch (_) {}
            }, 260);
        } catch (err) {
            showToast('Failed: ' + err.message, 'error');
            btns.forEach(b => { b.disabled = false; });
        }
    }

})();
