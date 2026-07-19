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

            // Assigned to (count placeholder — we don't have a fast query for this right now)
            const tdAssigned = el('td');
            tdAssigned.textContent = '—';
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

    // Close panel on Escape
    document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && !formPanel.classList.contains('hidden')) closePanel();
    });

    // Boot
    loadResources();
})();
