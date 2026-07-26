/**
 * events.js — Events page logic.
 *
 * Split-pane layout:
 *   Left:  searchable, filterable submission list
 *   Right: selected submission detail + resource/comment assignment
 *
 * Key UX goal: fast assignment — type resource name → Enter to add instantly.
 */

(function () {
    'use strict';

    // --- State ---
    let allSubmissions = [];   // full list from /api/submissions
    let filteredList = [];   // after search/filter
    let selectedCode = null; // currently selected submission code
    let availResources = [];   // from /api/resources (cached)
    let selectedResource = null; // resource object from autocomplete

    // Restore last selected code from sessionStorage for page reload resilience
    const SESSION_KEY = 'ops-selected-code';

    // --- List elements ---
    const eventSearch = document.getElementById('event-search');
    const searchMeta = document.getElementById('search-meta');
    const filterHasData = document.getElementById('filter-has-data');
    const filterNoData = document.getElementById('filter-no-data');
    const filterHasConflict = document.getElementById('filter-has-conflict');
    const eventsList = document.getElementById('events-list');

    // --- Detail elements ---
    const detailEmpty = document.getElementById('detail-empty');
    const detailPanel = document.getElementById('detail-panel');
    const detailCode = document.getElementById('detail-code');
    const detailTitle = document.getElementById('detail-title');
    const detailMeta = document.getElementById('detail-meta');
    const detailTrack = document.getElementById('detail-track-bar');
    const conflictBanner = document.getElementById('detail-conflict-banner');
    const slotsEl = document.getElementById('detail-slots');
    const speakersEl = document.getElementById('detail-speakers');
    const resListEl = document.getElementById('resources-assignment-list');
    const cmtListEl = document.getElementById('comments-assignment-list');

    // Resource add UI
    const resSearchInput = document.getElementById('resource-search-input');
    const resDropdown = document.getElementById('resource-dropdown');
    const resNoteInput = document.getElementById('resource-note-input');
    const resDeptSel = document.getElementById('resource-dept-override');
    const resAddBtn = document.getElementById('resource-add-btn');

    // Comment add UI
    const cmtTextInput = document.getElementById('comment-text-input');
    const cmtDeptSel = document.getElementById('comment-dept-select');
    const cmtAddBtn = document.getElementById('comment-add-btn');

    // ---------------------------------------------------------------------------
    // Load submissions list
    // ---------------------------------------------------------------------------

    async function loadSubmissions(query = '') {
        try {
            const qs = query ? `?q=${encodeURIComponent(query)}` : '';
            const data = await apiFetch('/api/submissions' + qs);
            allSubmissions = data.submissions || [];
            applyFilters();
        } catch (e) {
            showToast('Failed to load submissions: ' + e.message, 'error');
        }
    }

    async function loadResources() {
        try {
            const data = await apiFetch('/api/resources');
            availResources = data.resources || [];
        } catch (e) {
            // non-fatal
        }
    }

    // ---------------------------------------------------------------------------
    // Filter & render list
    // ---------------------------------------------------------------------------

    function applyFilters() {
        const onlyData = filterHasData?.checked;
        const onlyTodo = filterNoData?.checked;
        const onlyConflict = filterHasConflict?.checked;
        filteredList = allSubmissions.filter(s => {
            if (onlyData && !s.has_data) return false;
            if (onlyTodo && s.has_data) return false;
            if (onlyConflict && !s.has_conflict) return false;
            return true;
        });
        renderList();
    }

    function renderList() {
        eventsList.innerHTML = '';
        const count = filteredList.length;
        searchMeta.textContent = `${count} event${count !== 1 ? 's' : ''}`;

        if (count === 0) {
            const li = el('li', { cls: 'list-placeholder' });
            li.textContent = 'No events match your search.';
            eventsList.appendChild(li);
            return;
        }

        for (const sub of filteredList) {
            const li = el('li', {
                cls: `event-list-item${sub.code === selectedCode ? ' selected' : ''}${sub.has_conflict ? ' has-conflict' : ''}`,
                role: 'option',
                'aria-selected': sub.code === selectedCode ? 'true' : 'false',
                'data-code': sub.code,
            });
            li.addEventListener('click', () => selectSubmission(sub.code));

            // Header row: code + dots
            const header = el('div', { cls: 'event-item-header' });
            const codeEl = el('span', { cls: 'event-item-code' });
            codeEl.textContent = sub.code;
            header.appendChild(codeEl);

            const dots = el('div', { cls: 'event-item-dots' });
            if (sub.has_data) dots.appendChild(el('span', { cls: 'event-dot data', title: 'Has resources/comments' }));
            if (sub.has_conflict) dots.appendChild(el('span', { cls: 'event-dot conflict', title: 'Resource conflict' }));

            li.appendChild(header);

            // Title
            const titleEl = el('div', { cls: 'event-item-title' });
            titleEl.textContent = sub.title;
            li.appendChild(titleEl);

            // Meta: track · speakers · first slot time
            const meta = el('div', { cls: 'event-item-meta' });
            if (sub.track?.name) {
                const t = el('span');
                t.textContent = sub.track.name;
                meta.appendChild(t);
            }
            if (sub.slots?.length) {
                const slot0 = sub.slots[0];
                const tSpan = el('span');
                tSpan.textContent = `${fmtDate(slot0.start)} ${fmtTimeRange(slot0.start, slot0.end)}`;
                meta.appendChild(tSpan);
                if (sub.slots.length > 1) {
                    const more = el('span');
                    more.textContent = `+${sub.slots.length - 1} more slot${sub.slots.length > 2 ? 's' : ''}`;
                    meta.appendChild(more);
                }
            }
            if (sub.speakers?.length) {
                const sp = el('span');
                sp.textContent = sub.speakers.map(s => s.name).join(', ');
                meta.appendChild(sp);
            }
            li.appendChild(meta);
            li.appendChild(dots);

            eventsList.appendChild(li);
        }

        // Restore selection if still in list
        if (selectedCode && filteredList.some(s => s.code === selectedCode)) {
            scrollItemIntoView(selectedCode);
        }
    }

    function scrollItemIntoView(code) {
        const item = eventsList.querySelector(`[data-code="${code}"]`);
        item?.scrollIntoView({ block: 'nearest' });
    }

    // ---------------------------------------------------------------------------
    // Select a submission
    // ---------------------------------------------------------------------------

    async function selectSubmission(code) {
        if (selectedCode === code) return;

        // Update selection state in list
        eventsList.querySelectorAll('.event-list-item').forEach(li => {
            const isThis = li.dataset.code === code;
            li.classList.toggle('selected', isThis);
            li.setAttribute('aria-selected', isThis ? 'true' : 'false');
        });

        selectedCode = code;
        sessionStorage.setItem(SESSION_KEY, code);

        // Update URL hash so the selection is shareable / direct-linkable
        history.replaceState(null, '', '#' + encodeURIComponent(code));

        // Show panel
        detailEmpty.classList.add('hidden');
        detailPanel.classList.remove('hidden');

        // Fetch full detail
        try {
            const data = await apiFetch(`/api/submission/${encodeURIComponent(code)}`);
            renderDetailPanel(data);
        } catch (e) {
            showToast('Failed to load submission: ' + e.message, 'error');
        }
    }

    // ---------------------------------------------------------------------------
    // Render detail panel
    // ---------------------------------------------------------------------------

    function renderDetailPanel(data) {
        // Track color bar
        const color = data.track?.color || '#3b82f6';
        detailTrack.style.background = color;

        // Code / title / meta
        detailCode.textContent = data.code;
        detailTitle.textContent = data.title;

        detailMeta.innerHTML = '';
        if (data.track?.name) {
            const t = el('span');
            t.textContent = data.track.name;
            detailMeta.appendChild(t);
        }
        if (data.submission_type) {
            const t = el('span');
            t.textContent = data.submission_type;
            detailMeta.appendChild(t);
        }

        // Submitter notes and internal notes
        const notesWrap = el('div', { cls: 'detail-notes' });
        if (data.notes) {
            const block = el('div', { cls: 'detail-note-block detail-note-public' });
            const label = el('span', { cls: 'detail-note-label' });
            label.textContent = 'Submitter Notes';
            const text = el('p', { cls: 'detail-note-text' });
            text.textContent = data.notes;
            block.appendChild(label);
            block.appendChild(text);
            notesWrap.appendChild(block);
        }
        if (data.internal_notes) {
            const block = el('div', { cls: 'detail-note-block detail-note-internal' });
            const label = el('span', { cls: 'detail-note-label' });
            label.textContent = 'Internal Notes';
            const text = el('p', { cls: 'detail-note-text' });
            text.textContent = data.internal_notes;
            block.appendChild(label);
            block.appendChild(text);
            notesWrap.appendChild(block);
        }
        if (notesWrap.children.length) {
            detailMeta.appendChild(notesWrap);
        }

        // Conflict banner
        if (data.has_conflict) {
            conflictBanner.classList.remove('hidden');
        } else {
            conflictBanner.classList.add('hidden');
        }

        // Slots
        slotsEl.innerHTML = '';
        for (const slot of (data.slots || [])) {
            const row = el('div', { cls: 'slot-row' });
            const time = el('span', { cls: 'slot-time' });
            time.textContent = fmtTimeRange(slot.start, slot.end);
            const date = el('span', { cls: 'slot-room' });
            date.textContent = fmtDate(slot.start);
            const room = el('span', { cls: 'slot-room' });
            room.textContent = slot.room_name || '—';
            if (data.slots.length > 1) {
                const badge = el('span', { cls: 'slot-badge' });
                badge.textContent = `Slot ${slot.slot_index + 1}`;
                row.appendChild(time);
                row.appendChild(date);
                row.appendChild(room);
                row.appendChild(badge);
            } else {
                row.appendChild(time);
                row.appendChild(date);
                row.appendChild(room);
            }
            slotsEl.appendChild(row);
        }

        // Speakers
        speakersEl.innerHTML = '';
        for (const sp of (data.speakers || [])) {
            const row = el('div', { cls: 'speaker-row' });
            const name = el('span', { cls: 'speaker-name' });
            name.textContent = sp.name;
            row.appendChild(name);
            if (sp.telegram) {
                const tg = el('span', { cls: 'speaker-telegram' });
                tg.textContent = `${sp.telegram}`;
                row.appendChild(tg);
            }
            speakersEl.appendChild(row);
        }

        // Assignments
        renderAssignments(data.assignments || { resources: [], comments: [] });
    }

    function renderAssignments({ resources, comments }) {
        // Resources
        resListEl.innerHTML = '';
        if (resources.length === 0) {
            const li = el('li', { cls: 'assignment-empty' });
            li.textContent = 'No resources assigned yet.';
            resListEl.appendChild(li);
        } else {
            for (const r of resources) {
                resListEl.appendChild(makeResourceItem(r));
            }
        }

        // Comments
        cmtListEl.innerHTML = '';
        if (comments.length === 0) {
            const li = el('li', { cls: 'assignment-empty' });
            li.textContent = 'No comments yet.';
            cmtListEl.appendChild(li);
        } else {
            for (const c of comments) {
                cmtListEl.appendChild(makeCommentItem(c));
            }
        }
    }

    function makeResourceItem(r) {
        const li = el('li', { cls: 'assignment-item' });
        const nameEl = el('span', { cls: 'assignment-name' });
        nameEl.textContent = r.resource_name;
        li.appendChild(nameEl);

        if (r.note) {
            const noteEl = el('span', { cls: 'assignment-note' });
            noteEl.textContent = `(${r.note})`;
            li.appendChild(noteEl);
        }

        // Effective departments
        const effectiveDepts = r.department_override
            ? [r.department_override]
            : (r.resource_departments || []);
        const deptWrap = el('div', { cls: 'assignment-dept' });
        for (const d of effectiveDepts) deptWrap.appendChild(deptPill(d));
        li.appendChild(deptWrap);

        if (CAN_WRITE) {
            const rmBtn = el('button', {
                cls: 'assignment-remove',
                title: 'Remove resource',
                type: 'button',
            });
            rmBtn.textContent = '×';
            rmBtn.addEventListener('click', () => removeResource(r.id));
            li.appendChild(rmBtn);
        }
        return li;
    }

    function makeCommentItem(c) {
        const li = el('li', { cls: 'assignment-item' });
        li.appendChild(deptPill(c.department));
        const textEl = el('span', { cls: 'assignment-name' });
        textEl.textContent = c.text;
        li.appendChild(textEl);

        if (CAN_WRITE) {
            const rmBtn = el('button', {
                cls: 'assignment-remove',
                title: 'Remove comment',
                type: 'button',
            });
            rmBtn.textContent = '×';
            rmBtn.addEventListener('click', () => removeComment(c.id));
            li.appendChild(rmBtn);
        }
        return li;
    }

    // ---------------------------------------------------------------------------
    // Reload assignments (called after add/remove)
    // ---------------------------------------------------------------------------

    async function reloadAssignments() {
        if (!selectedCode) return;
        try {
            const data = await apiFetch(`/api/submission/${encodeURIComponent(selectedCode)}/assignments`);
            renderAssignments(data);

            // Reload the list to update has_data / has_conflict badges
            await loadSubmissions(eventSearch?.value?.trim() || '');
        } catch (e) {
            showToast('Reload error: ' + e.message, 'error');
        }
    }

    // ---------------------------------------------------------------------------
    // Resource autocomplete
    // ---------------------------------------------------------------------------

    function buildDropdown(query) {
        if (!resDropdown) return;
        const q = query.toLowerCase();
        const matches = availResources.filter(r => r.name.toLowerCase().includes(q));

        resDropdown.innerHTML = '';
        if (matches.length === 0 || !query) {
            resDropdown.classList.add('hidden');
            return;
        }

        for (const res of matches) {
            const li = el('li', {
                cls: 'autocomplete-item',
                role: 'option',
                'data-id': String(res.id),
            });
            const nameSpan = el('span', { cls: 'autocomplete-item-name' });
            nameSpan.textContent = res.name;
            const amtSpan = el('span', { cls: 'autocomplete-item-amount' });
            amtSpan.textContent = res.amount === 0 ? '∞' : `×${res.amount}`;
            li.appendChild(nameSpan);
            if (res.departments?.length) {
                const deptSpan = el('span', { cls: 'autocomplete-item-dept' });
                deptSpan.textContent = res.departments.join(', ');
                li.appendChild(deptSpan);
            }
            li.appendChild(amtSpan);
            li.addEventListener('mousedown', (ev) => {
                ev.preventDefault();  // don't blur the input
                pickResource(res);
            });
            resDropdown.appendChild(li);
        }
        resDropdown.classList.remove('hidden');
    }

    function pickResource(res) {
        selectedResource = res;
        if (resSearchInput) resSearchInput.value = res.name;
        resDropdown?.classList.add('hidden');
        if (resAddBtn) resAddBtn.disabled = false;
        resNoteInput?.focus();
    }

    resSearchInput?.addEventListener('input', () => {
        selectedResource = null;
        if (resAddBtn) resAddBtn.disabled = true;
        buildDropdown(resSearchInput.value);
    });

    resSearchInput?.addEventListener('keydown', (ev) => {
        if (!resDropdown || resDropdown.classList.contains('hidden')) return;
        const items = [...resDropdown.querySelectorAll('.autocomplete-item')];
        const current = resDropdown.querySelector('[aria-selected="true"]');
        let idx = items.indexOf(current);

        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            idx = Math.min(idx + 1, items.length - 1);
            items.forEach((it, i) => it.setAttribute('aria-selected', i === idx ? 'true' : 'false'));
            items[idx]?.scrollIntoView({ block: 'nearest' });
        } else if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            idx = Math.max(idx - 1, 0);
            items.forEach((it, i) => it.setAttribute('aria-selected', i === idx ? 'true' : 'false'));
            items[idx]?.scrollIntoView({ block: 'nearest' });
        } else if (ev.key === 'Enter') {
            ev.preventDefault();
            const selected = resDropdown.querySelector('[aria-selected="true"]');
            if (selected) {
                const res = availResources.find(r => String(r.id) === selected.dataset.id);
                if (res) pickResource(res);
            }
        } else if (ev.key === 'Escape') {
            resDropdown.classList.add('hidden');
        }
    });

    resSearchInput?.addEventListener('blur', () => {
        // Small delay so mousedown on dropdown items can fire first
        setTimeout(() => resDropdown?.classList.add('hidden'), 150);
    });

    resNoteInput?.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
            ev.preventDefault();
            resAddBtn?.click();
        }
    });

    // ---------------------------------------------------------------------------
    // Add resource
    // ---------------------------------------------------------------------------

    resAddBtn?.addEventListener('click', async () => {
        if (!selectedCode || !selectedResource) return;
        const note = resNoteInput?.value?.trim() || null;
        const deptOverride = resDeptSel?.value || null;

        resAddBtn.disabled = true;
        try {
            await apiFetch(`/api/submission/${encodeURIComponent(selectedCode)}/resources`, {
                method: 'POST',
                body: JSON.stringify({
                    resource_id: selectedResource.id,
                    note: note,
                    department_override: deptOverride || null,
                }),
            });
            // Reset form
            if (resSearchInput) resSearchInput.value = '';
            if (resNoteInput) resNoteInput.value = '';
            if (resDeptSel) resDeptSel.value = '';
            selectedResource = null;
            resAddBtn.disabled = true;
            showToast(`Added "${selectedResource?.name || 'resource'}"`, 'success');
            await reloadAssignments();
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
            resAddBtn.disabled = false;
        }
    });

    async function removeResource(assignmentId) {
        if (!selectedCode) return;
        try {
            await apiFetch(
                `/api/submission/${encodeURIComponent(selectedCode)}/resources/${assignmentId}`,
                { method: 'DELETE' },
            );
            showToast('Resource removed', 'info');
            await reloadAssignments();
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
        }
    }

    // ---------------------------------------------------------------------------
    // Add / remove comment
    // ---------------------------------------------------------------------------

    cmtAddBtn?.addEventListener('click', async () => {
        if (!selectedCode) return;
        const text = cmtTextInput?.value?.trim();
        const dept = cmtDeptSel?.value;
        if (!text) { showToast('Comment text is required', 'warn'); cmtTextInput?.focus(); return; }

        cmtAddBtn.disabled = true;
        try {
            await apiFetch(`/api/submission/${encodeURIComponent(selectedCode)}/comments`, {
                method: 'POST',
                body: JSON.stringify({ text, department: dept }),
            });
            if (cmtTextInput) cmtTextInput.value = '';
            showToast('Comment added', 'success');
            await reloadAssignments();
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
        } finally {
            cmtAddBtn.disabled = false;
        }
    });

    cmtTextInput?.addEventListener('keydown', (ev) => {
        // Ctrl+Enter to submit
        if (ev.key === 'Enter' && ev.ctrlKey) {
            ev.preventDefault();
            cmtAddBtn?.click();
        }
    });

    async function removeComment(commentId) {
        if (!selectedCode) return;
        try {
            await apiFetch(
                `/api/submission/${encodeURIComponent(selectedCode)}/comments/${commentId}`,
                { method: 'DELETE' },
            );
            showToast('Comment removed', 'info');
            await reloadAssignments();
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
        }
    }

    // ---------------------------------------------------------------------------
    // Search & filters
    // ---------------------------------------------------------------------------

    const debouncedSearch = debounce(async (q) => {
        await loadSubmissions(q);
    }, 280);

    eventSearch?.addEventListener('input', () => {
        debouncedSearch(eventSearch.value.trim());
    });

    filterHasData?.addEventListener('change', () => {
        if (filterHasData.checked && filterNoData?.checked) filterNoData.checked = false;
        applyFilters();
    });
    filterNoData?.addEventListener('change', () => {
        if (filterNoData.checked && filterHasData?.checked) filterHasData.checked = false;
        applyFilters();
    });
    filterHasConflict?.addEventListener('change', applyFilters);

    // ---------------------------------------------------------------------------
    // Boot
    // ---------------------------------------------------------------------------

    // Resolve the initial code to select: URL hash takes priority over sessionStorage
    function getInitialCode() {
        const hash = location.hash ? decodeURIComponent(location.hash.slice(1)) : null;
        if (hash && allSubmissions.some(s => s.code === hash)) return hash;
        const saved = sessionStorage.getItem(SESSION_KEY);
        if (saved && allSubmissions.some(s => s.code === saved)) return saved;
        return null;
    }

    (async () => {
        await Promise.all([loadSubmissions(), loadResources()]);

        // Restore selection from URL hash or sessionStorage
        const initial = getInitialCode();
        if (initial) {
            await selectSubmission(initial);
            scrollItemIntoView(initial);
        }
    })();

    // Handle browser back/forward and externally-set hash changes
    window.addEventListener('hashchange', async () => {
        const code = location.hash ? decodeURIComponent(location.hash.slice(1)) : null;
        if (code && code !== selectedCode && allSubmissions.some(s => s.code === code)) {
            await selectSubmission(code);
            scrollItemIntoView(code);
        }
    });

})();
