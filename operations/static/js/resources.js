/**
 * resources.js — Resources page logic.
 * Handles list rendering, add/edit form panel, and delete.
 */

(function () {
    'use strict';

    // --- State ---
    let allResources = [];
    let editingId    = null;   // null = creating new

    // --- Elements ---
    const tbody         = document.getElementById('resources-tbody');
    const btnAdd        = document.getElementById('btn-add-resource');
    const formPanel     = document.getElementById('resource-form-panel');
    const formEl        = document.getElementById('resource-form');
    const panelTitle    = document.getElementById('form-panel-title');
    const inputId       = document.getElementById('form-resource-id');
    const inputName     = document.getElementById('form-resource-name');
    const inputAmount   = document.getElementById('form-resource-amount');
    const deptBoxes     = document.querySelectorAll('.dept-checkbox');
    const btnSubmit     = document.getElementById('form-submit-btn');
    const btnCancel     = document.getElementById('form-cancel-btn');
    const btnDelete     = document.getElementById('form-delete-btn');

    // ---------------------------------------------------------------------------
    // Load & render
    // ---------------------------------------------------------------------------

    async function loadResources() {
        try {
            const data = await apiFetch('/api/resources');
            allResources = data.resources || [];
            renderTable();
        } catch (e) {
            showToast('Failed to load resources: ' + e.message, 'error');
        }
    }

    function renderTable() {
        tbody.innerHTML = '';
        if (allResources.length === 0) {
            const tr = el('tr');
            const td = el('td', { colspan: '5', cls: 'table-placeholder' });
            td.textContent = 'No resources yet. Add one with the button above.';
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
        }

        for (const res of allResources) {
            const tr = el('tr', { cls: 'resource-row' });
            tr.addEventListener('click', () => CAN_WRITE && openEdit(res));

            // Name
            const tdName = el('td');
            tdName.textContent = res.name;
            tr.appendChild(tdName);

            // Amount
            const tdAmt = el('td');
            const amtBadge = el('span', {
                cls: `amount-badge ${res.amount === 0 ? 'infinite' : ''}`,
            });
            amtBadge.textContent = res.amount === 0 ? '∞' : String(res.amount);
            tdAmt.appendChild(amtBadge);
            tr.appendChild(tdAmt);

            // Departments
            const tdDepts = el('td');
            const pillsWrap = el('div', { cls: 'dept-pills-cell' });
            if (res.departments.length === 0) {
                const none = el('span', { cls: 'assignment-empty' });
                none.textContent = '—';
                pillsWrap.appendChild(none);
            } else {
                for (const d of res.departments) pillsWrap.appendChild(deptPill(d));
            }
            tdDepts.appendChild(pillsWrap);
            tr.appendChild(tdDepts);

            // Assigned to: show count link that opens modal
            const tdAssigned = el('td');
            tdAssigned.dataset.resourceId   = res.id;
            tdAssigned.dataset.resourceName = res.name;
            renderAssignedCell(tdAssigned, res);
            tr.appendChild(tdAssigned);

            // Edit button
            const tdActions = el('td');
            if (CAN_WRITE) {
                const btnEdit = el('button', { cls: 'btn btn-ghost btn-sm' });
                btnEdit.textContent = 'Edit';
                btnEdit.addEventListener('click', (ev) => { ev.stopPropagation(); openEdit(res); });
                tdActions.appendChild(btnEdit);
            }
            tr.appendChild(tdActions);

            tbody.appendChild(tr);
        }
    }

    // ---------------------------------------------------------------------------
    // Form panel open / close
    // ---------------------------------------------------------------------------

    function openCreate() {
        editingId = null;
        panelTitle.textContent = 'New Resource';
        inputId.value     = '';
        inputName.value   = '';
        inputAmount.value = '0';
        deptBoxes.forEach(cb => { cb.checked = false; });
        btnSubmit.textContent = 'Create';
        btnDelete.classList.add('hidden');
        showPanel();
        inputName.focus();
    }

    function openEdit(res) {
        editingId = res.id;
        panelTitle.textContent = 'Edit Resource';
        inputId.value     = res.id;
        inputName.value   = res.name;
        inputAmount.value = res.amount;
        deptBoxes.forEach(cb => {
            cb.checked = res.departments.includes(cb.value);
        });
        btnSubmit.textContent = 'Save';
        btnDelete.classList.remove('hidden');
        showPanel();
        inputName.focus();
    }

    function showPanel() {
        formPanel.classList.remove('hidden');
        btnAdd && btnAdd.setAttribute('aria-expanded', 'true');
    }

    function closePanel() {
        formPanel.classList.add('hidden');
        btnAdd && btnAdd.setAttribute('aria-expanded', 'false');
        editingId = null;
    }

    // ---------------------------------------------------------------------------
    // Form submission
    // ---------------------------------------------------------------------------

    formEl && formEl.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const name   = inputName.value.trim();
        const amount = parseInt(inputAmount.value, 10) || 0;
        const depts  = [...deptBoxes].filter(cb => cb.checked).map(cb => cb.value);

        if (!name) {
            inputName.focus();
            showToast('Name is required', 'warn');
            return;
        }

        btnSubmit.disabled = true;
        try {
            if (editingId) {
                await apiFetch(`/api/resources/${editingId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ name, amount, departments: depts }),
                });
                showToast('Resource updated', 'success');
            } else {
                await apiFetch('/api/resources', {
                    method: 'POST',
                    body: JSON.stringify({ name, amount, departments: depts }),
                });
                showToast('Resource created', 'success');
            }
            closePanel();
            await loadResources();
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
        } finally {
            btnSubmit.disabled = false;
        }
    });

    // ---------------------------------------------------------------------------
    // Delete
    // ---------------------------------------------------------------------------

    btnDelete && btnDelete.addEventListener('click', async () => {
        if (!editingId) return;
        const res = allResources.find(r => r.id === editingId);
        if (!confirm(`Delete "${res?.name ?? 'this resource'}"? This will remove all its assignments too.`)) return;

        btnDelete.disabled = true;
        try {
            await apiFetch(`/api/resources/${editingId}`, { method: 'DELETE' });
            showToast('Resource deleted', 'info');
            closePanel();
            await loadResources();
        } catch (e) {
            showToast('Error: ' + e.message, 'error');
        } finally {
            btnDelete.disabled = false;
        }
    });

    // ---------------------------------------------------------------------------
    // Wire UI
    // ---------------------------------------------------------------------------

    btnAdd    && btnAdd.addEventListener('click', openCreate);
    btnCancel && btnCancel.addEventListener('click', closePanel);

    // ---------------------------------------------------------------------------
    // Assigned-to: count and usage modal — element refs
    // ---------------------------------------------------------------------------

    const usageOverlay      = document.getElementById('usage-modal-overlay');
    const usageModalBody    = document.getElementById('usage-modal-body');
    const usageResourceName = document.getElementById('usage-modal-resource-name');
    const usageCloseBtn     = document.getElementById('usage-modal-close');

    // Close panel / modal on Escape
    document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape') {
            if (!formPanel.classList.contains('hidden')) closePanel();
            if (usageOverlay && !usageOverlay.classList.contains('hidden')) closeUsageModal();
        }
    });

    // Boot
    loadResources();

    // ---------------------------------------------------------------------------
    // Assigned-to: count and usage modal — logic
    // ---------------------------------------------------------------------------

    /** Render the Assigned-To cell: shows a clickable count or a muted dash */
    function renderAssignedCell(td, res) {
        apiFetch('/api/resources/' + res.id + '/usages').then(data => {
            const count = data.total || 0;
            td.innerHTML = '';
            if (count === 0) {
                const dash = el('span', { cls: 'assignment-empty' });
                dash.textContent = '—';
                td.appendChild(dash);
            } else {
                const link = el('button', { cls: 'btn-link assigned-count-link' });
                link.textContent = count + ' event' + (count !== 1 ? 's' : '');
                link.addEventListener('click', (ev) => {
                    ev.stopPropagation();
                    openUsageModal(res.id, res.name);
                });
                td.appendChild(link);
            }
        }).catch(() => {
            const dash = el('span', { cls: 'assignment-empty' });
            dash.textContent = '—';
            td.innerHTML = '';
            td.appendChild(dash);
        });
    }

    async function openUsageModal(resourceId, resourceName) {
        if (!usageOverlay) return;
        if (usageResourceName) usageResourceName.textContent = resourceName;
        usageModalBody.innerHTML = '';
        const loadDiv = el('div', { cls: 'usage-modal-loading' });
        const spinner = el('div', { cls: 'loading-spinner' });
        loadDiv.appendChild(spinner);
        loadDiv.appendChild(txt(' Loading…'));
        usageModalBody.appendChild(loadDiv);
        usageOverlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        try {
            const data = await apiFetch('/api/resources/' + resourceId + '/usages');
            renderUsageModal(data);
        } catch (e) {
            usageModalBody.innerHTML = '';
            const errEl = el('p', { cls: 'usage-modal-error' });
            errEl.textContent = 'Failed to load: ' + e.message;
            usageModalBody.appendChild(errEl);
        }
    }

    function renderUsageModal(data) {
        usageModalBody.innerHTML = '';
        const usages = data.usages || [];

        if (usages.length === 0) {
            const empty = el('div', { cls: 'usage-modal-empty' });
            const icon  = el('div', { cls: 'empty-icon' });
            icon.textContent = '📭';
            const msg   = el('p');
            msg.textContent = 'Not assigned to any events.';
            empty.appendChild(icon);
            empty.appendChild(msg);
            usageModalBody.appendChild(empty);
            return;
        }

        const list = el('div', { cls: 'usage-event-list' });

        for (const u of usages) {
            const card = el('div', { cls: 'usage-event-card' });

            // Code + title header
            const titleRow = el('div', { cls: 'usage-event-title-row' });
            const codeEl   = el('span', { cls: 'usage-event-code' });
            codeEl.textContent = u.submission_code;
            const titleEl  = el('span', { cls: 'usage-event-title' });
            titleEl.textContent = u.title;
            titleRow.appendChild(codeEl);
            titleRow.appendChild(titleEl);
            card.appendChild(titleRow);

            // Note / dept override
            if (u.note) {
                const noteEl = el('div', { cls: 'usage-event-note' });
                noteEl.textContent = 'Note: ' + u.note;
                card.appendChild(noteEl);
            }
            if (u.department_override) {
                const deptEl = el('div', { cls: 'usage-event-dept' });
                deptEl.appendChild(txt('Dept override: '));
                deptEl.appendChild(deptPill(u.department_override));
                card.appendChild(deptEl);
            }

            // Slots
            if ((u.slots || []).length > 0) {
                const slotsEl = el('div', { cls: 'usage-event-slots' });
                for (const slot of u.slots) {
                    const slotEl = el('div', { cls: 'usage-slot' });
                    const timeEl = el('span', { cls: 'usage-slot-time' });
                    const start  = fmtTime(slot.start);
                    const end    = fmtTime(slot.end);
                    const date   = fmtDate(slot.start);
                    timeEl.textContent = date + ' · ' + start + '–' + end;
                    slotEl.appendChild(timeEl);
                    if (slot.room_name) {
                        const roomEl = el('span', { cls: 'usage-slot-room' });
                        roomEl.textContent = ' @ ' + slot.room_name;
                        slotEl.appendChild(roomEl);
                    }
                    slotsEl.appendChild(slotEl);
                }
                card.appendChild(slotsEl);
            }

            // Speakers
            if ((u.speakers || []).length > 0) {
                const spEl = el('div', { cls: 'usage-event-speakers' });
                spEl.textContent = u.speakers.map(s => s.name).join(', ');
                card.appendChild(spEl);
            }

            list.appendChild(card);
        }

        usageModalBody.appendChild(list);
    }

    function closeUsageModal() {
        if (!usageOverlay) return;
        usageOverlay.classList.add('hidden');
        document.body.style.overflow = '';
    }

    usageCloseBtn   && usageCloseBtn.addEventListener('click', closeUsageModal);
    usageOverlay    && usageOverlay.addEventListener('click', (ev) => {
        if (ev.target === usageOverlay) closeUsageModal();
    });
})();
