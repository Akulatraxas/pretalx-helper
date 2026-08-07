/**
 * output.js — Output page: department tabs, table rendering, search & dropdown filters, CSV export.
 */

(function () {
    'use strict';

    let currentDept = 'all';
    let currentRows = [];
    let allResources = [];
    let availableRooms = [];

    let selectedResourceIds = new Set();
    let selectedRoomNames = new Set();
    let searchQuery = '';

    const tabs = document.querySelectorAll('.dept-tab');
    const tbody = document.getElementById('output-tbody');
    const tableEl = document.getElementById('output-table');
    const emptyEl = document.getElementById('output-empty');
    const footerEl = document.getElementById('output-footer');
    const exportBtn = document.getElementById('btn-export-csv');

    const searchInput = document.getElementById('output-filter-search');
    const btnFilterResources = document.getElementById('btn-filter-resources');
    const dropdownResources = document.getElementById('dropdown-resources');
    const btnFilterRooms = document.getElementById('btn-filter-rooms');
    const dropdownRooms = document.getElementById('dropdown-rooms');
    const btnClearFilters = document.getElementById('btn-clear-filters');

    // ---------------------------------------------------------------------------
    // Load output data
    /**
     * Loads output data for a department and refreshes the table and footer.
     * @param {string} dept - The department whose output should be loaded.
     */

    async function loadOutput(dept) {
        showLoading();
        try {
            const data = await apiFetch(`/api/output?dept=${encodeURIComponent(dept)}`);
            currentRows = data.rows || [];
            updateAvailableRooms();
            renderTable();
            updateFooter();
        } catch (e) {
            showToast('Failed to load output: ' + e.message, 'error');
        }
    }

    // ---------------------------------------------------------------------------
    // Filters logic & Dropdowns
    /**
     * Loads available resources and updates the resource filter.
     * On failure, clears the available resources and renders an empty filter.
     */

    async function loadResourceFilter() {
        try {
            const data = await apiFetch('/api/resources');
            allResources = (data.resources || []).sort((a, b) => a.name.localeCompare(b.name));
            renderResourceDropdown();
        } catch (e) {
            allResources = [];
            renderResourceDropdown();
        }
    }

    /**
     * Renders the resource filter dropdown using the available resources and current selections.
     */
    function renderResourceDropdown() {
        const items = allResources.map(r => ({ id: String(r.id), label: r.name }));
        buildDropdown({
            panelEl: dropdownResources,
            btnEl: btnFilterResources,
            items: items,
            selectedSet: selectedResourceIds,
            defaultLabel: 'Resources',
            hasSearch: items.length > 8,
            showBulkActions: items.length > 1,
            onToggle: () => {
                updateClearButton();
                renderTable();
                updateFooter();
            }
        });
    }

    /**
     * Updates the room filter with the unique room names from the current rows.
     */
    function updateAvailableRooms() {
        const roomSet = new Set();
        for (const r of currentRows) {
            if (r.room_name) roomSet.add(r.room_name);
        }
        availableRooms = Array.from(roomSet).sort((a, b) => a.localeCompare(b));
        // Prune selectedRoomNames to only include rooms still available
        for (const roomName of selectedRoomNames) {
            if (!roomSet.has(roomName)) {
                selectedRoomNames.delete(roomName);
            }
        }
        renderRoomDropdown();
    }

    function renderRoomDropdown() {
        const items = availableRooms.map(name => ({ id: name, label: name }));
        buildDropdown({
            panelEl: dropdownRooms,
            btnEl: btnFilterRooms,
            items: items,
            selectedSet: selectedRoomNames,
            defaultLabel: 'Rooms',
            hasSearch: items.length > 8,
            showBulkActions: items.length > 1,
            onToggle: () => {
                updateClearButton();
                renderTable();
                updateFooter();
            }
        });
    }

    /**
     * Builds a selectable dropdown panel and synchronizes its button state.
     * @param {Object} options - Dropdown configuration.
     * @param {HTMLElement} options.panelEl - Element that contains the dropdown contents.
     * @param {HTMLElement} options.btnEl - Button whose label and selection state are updated.
     * @param {Array<Object>} options.items - Items to display, each with an `id` and optional `label`.
     * @param {Set<string>} options.selectedSet - Set of selected item identifiers.
     * @param {string} options.defaultLabel - Label used when no items are selected.
     * @param {boolean} [options.hasSearch=false] - Whether to include an item search field.
     * @param {boolean} [options.showBulkActions=true] - Whether to include select-all and clear actions.
     * @param {Function} [options.onToggle] - Callback invoked after the selection changes.
     */
    function buildDropdown(options) {
        const {
            panelEl,
            btnEl,
            items,
            selectedSet,
            defaultLabel,
            hasSearch = false,
            showBulkActions = true,
            onToggle = () => {}
        } = options;

        if (!panelEl || !btnEl) return;
        panelEl.replaceChildren();

        if (items.length === 0) {
            const empty = el('div', { cls: 'dropdown-placeholder' });
            empty.textContent = `No ${defaultLabel.toLowerCase()} available`;
            panelEl.appendChild(empty);
            updateDropdownButtonState(btnEl, selectedSet, defaultLabel);
            return;
        }

        if (hasSearch) {
            const searchDiv = el('div', { cls: 'dropdown-search' });
            const searchIn = el('input', {
                type: 'text',
                placeholder: 'Filter...',
                'aria-label': `Filter ${defaultLabel.toLowerCase()}`
            });
            searchIn.addEventListener('input', () => {
                const q = searchIn.value.toLowerCase();
                panelEl.querySelectorAll('.dropdown-item').forEach(item => {
                    const label = item.getAttribute('data-label') || '';
                    item.style.display = label.toLowerCase().includes(q) ? '' : 'none';
                });
            });
            searchDiv.appendChild(searchIn);
            panelEl.appendChild(searchDiv);
        }

        if (showBulkActions) {
            const bulkBar = el('div', { cls: 'dropdown-bulk-actions' });
            const btnSelectAll = el('button', { cls: 'dropdown-bulk-btn', type: 'button' });
            btnSelectAll.textContent = 'Select all';
            btnSelectAll.addEventListener('click', (e) => {
                e.stopPropagation();
                items.forEach(item => selectedSet.add(String(item.id)));
                panelEl.querySelectorAll('.dropdown-item').forEach(row => {
                    row.classList.add('selected');
                    row.setAttribute('aria-checked', 'true');
                });
                updateDropdownButtonState(btnEl, selectedSet, defaultLabel);
                onToggle();
            });

            const btnClear = el('button', { cls: 'dropdown-bulk-btn', type: 'button' });
            btnClear.textContent = 'Clear';
            btnClear.addEventListener('click', (e) => {
                e.stopPropagation();
                selectedSet.clear();
                panelEl.querySelectorAll('.dropdown-item').forEach(row => {
                    row.classList.remove('selected');
                    row.setAttribute('aria-checked', 'false');
                });
                updateDropdownButtonState(btnEl, selectedSet, defaultLabel);
                onToggle();
            });

            bulkBar.appendChild(btnSelectAll);
            bulkBar.appendChild(btnClear);
            panelEl.appendChild(bulkBar);
        }

        items.forEach(item => {
            const idStr = String(item.id);
            const label = item.label || idStr;
            const isSelected = selectedSet.has(idStr);

            const row = el('div', {
                cls: `dropdown-item ${isSelected ? 'selected' : ''}`,
                'data-id': idStr,
                'data-label': label,
                role: 'menuitemcheckbox',
                'aria-checked': isSelected ? 'true' : 'false',
                tabindex: '0'
            });

            const checkbox = el('span', { cls: 'checkbox' });
            const labelEl = el('span', { cls: 'item-label' });
            labelEl.textContent = label;

            row.appendChild(checkbox);
            row.appendChild(labelEl);

            const toggleItem = () => {
                if (selectedSet.has(idStr)) {
                    selectedSet.delete(idStr);
                    row.classList.remove('selected');
                    row.setAttribute('aria-checked', 'false');
                } else {
                    selectedSet.add(idStr);
                    row.classList.add('selected');
                    row.setAttribute('aria-checked', 'true');
                }
                updateDropdownButtonState(btnEl, selectedSet, defaultLabel);
                onToggle();
            };

            row.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleItem();
            });

            row.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    e.stopPropagation();
                    toggleItem();
                }
            });

            panelEl.appendChild(row);
        });

        updateDropdownButtonState(btnEl, selectedSet, defaultLabel);
    }

    /**
     * Updates a dropdown button to reflect its current selection count.
     * @param {HTMLElement} btnEl - The dropdown button to update.
     * @param {Set} selectedSet - The selected option values.
     * @param {string} defaultLabel - The button label when no options are selected.
     */
    function updateDropdownButtonState(btnEl, selectedSet, defaultLabel) {
        if (!btnEl) return;
        const span = btnEl.querySelector('span');
        if (selectedSet.size > 0) {
            btnEl.classList.add('has-selection');
            if (span) span.textContent = `${defaultLabel} (${selectedSet.size})`;
        } else {
            btnEl.classList.remove('has-selection');
            if (span) span.textContent = defaultLabel;
        }
    }

    /**
     * Configures a button to toggle its associated dropdown panel.
     * @param {HTMLElement} btnEl - The button that controls the dropdown.
     * @param {HTMLElement} panelEl - The dropdown panel to open or close.
     */
    function setupDropdownToggle(btnEl, panelEl) {
        if (!btnEl || !panelEl) return;
        btnEl.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = panelEl.classList.contains('open');
            closeAllDropdowns();
            if (!isOpen) {
                panelEl.classList.add('open');
                btnEl.setAttribute('aria-expanded', 'true');
                const searchIn = panelEl.querySelector('.dropdown-search input');
                if (searchIn) searchIn.focus();
            }
        });
    }

    /**
     * Closes all filter dropdown panels and updates their expanded accessibility state.
     */
    function closeAllDropdowns() {
        document.querySelectorAll('.dropdown-panel').forEach(p => p.classList.remove('open'));
        document.querySelectorAll('.filter-btn').forEach(b => b.setAttribute('aria-expanded', 'false'));
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.filter-dropdown')) {
            closeAllDropdowns();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const openPanel = document.querySelector('.dropdown-panel.open');
            if (openPanel) {
                const filterDropdown = openPanel.closest('.filter-dropdown');
                const filterBtn = filterDropdown?.querySelector('.filter-btn');
                closeAllDropdowns();
                if (filterBtn) {
                    filterBtn.focus();
                }
            }
        }
    });

    /**
     * Updates the visibility of the clear-filters button based on the active filters.
     */
    function updateClearButton() {
        if (!btnClearFilters) return;
        if (selectedResourceIds.size > 0 || selectedRoomNames.size > 0 || searchQuery.length > 0) {
            btnClearFilters.classList.remove('hidden');
        } else {
            btnClearFilters.classList.add('hidden');
        }
    }

    btnClearFilters?.addEventListener('click', () => {
        selectedResourceIds.clear();
        selectedRoomNames.clear();
        searchQuery = '';
        if (searchInput) searchInput.value = '';

        renderResourceDropdown();
        renderRoomDropdown();
        updateClearButton();
        renderTable();
        updateFooter();
    });

    const handleSearchInput = debounce(() => {
        searchQuery = (searchInput.value || '').trim();
        updateClearButton();
        renderTable();
        updateFooter();
    }, 150);

    searchInput?.addEventListener('input', handleSearchInput);

    setupDropdownToggle(btnFilterResources, dropdownResources);
    setupDropdownToggle(btnFilterRooms, dropdownRooms);

    /**
     * Filters output rows by selected resources, rooms, and search text.
     * @return {Array} The rows matching all active filters.
     */
    function getFilteredRows() {
        let rows = currentRows;

        if (selectedResourceIds.size > 0) {
            rows = rows.filter(row =>
                (row.resources || []).some(r => selectedResourceIds.has(String(r.resource_id)))
            );
        }

        if (selectedRoomNames.size > 0) {
            rows = rows.filter(row =>
                selectedRoomNames.has(row.room_name || '')
            );
        }

        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            rows = rows.filter(row => {
                if ((row.title || '').toLowerCase().includes(q)) return true;
                if ((row.code || '').toLowerCase().includes(q)) return true;
                if ((row.room_name || '').toLowerCase().includes(q)) return true;
                if ((row.submission_type || '').toLowerCase().includes(q)) return true;
                if ((row.day_label || '').toLowerCase().includes(q)) return true;
                if ((row.start_time || '').toLowerCase().includes(q)) return true;
                if ((row.speakers || []).some(s =>
                    (s.name || '').toLowerCase().includes(q) ||
                    (s.telegram || '').toLowerCase().includes(q)
                )) return true;
                if ((row.resources || []).some(r =>
                    (r.resource_name || '').toLowerCase().includes(q) ||
                    (r.note || '').toLowerCase().includes(q)
                )) return true;
                if ((row.comments || []).some(c =>
                    (c.text || '').toLowerCase().includes(q)
                )) return true;
                return false;
            });
        }

        return rows;
    }

    /**
     * Displays a loading placeholder in the output table.
     */
    function showLoading() {
        tbody.innerHTML = '';
        const tr = el('tr', { cls: 'table-placeholder' });
        const td = el('td', { colspan: '8' });
        const spinner = el('div', { cls: 'loading-spinner' });
        td.appendChild(spinner);
        td.appendChild(txt(' Loading…'));
        tr.appendChild(td);
        tbody.appendChild(tr);
        emptyEl.classList.add('hidden');
        tableEl.style.display = '';
    }

    // ---------------------------------------------------------------------------
    // Render table
    // ---------------------------------------------------------------------------

    function renderTable() {
        tbody.innerHTML = '';

        const rows = getFilteredRows();

        if (rows.length === 0) {
            tableEl.style.display = 'none';
            emptyEl.classList.remove('hidden');
            return;
        }

        tableEl.style.display = '';
        emptyEl.classList.add('hidden');

        let lastDay = null;

        for (const row of rows) {
            // Day separator rows
            if (row.day_label !== lastDay) {
                lastDay = row.day_label;
                const sep = el('tr', { cls: 'day-separator-row' });
                const td = el('td', { colspan: '8' });
                td.textContent = row.day_label;
                Object.assign(td.style, {
                    fontFamily: "'Outfit', sans-serif",
                    fontWeight: '600',
                    fontSize: '0.8rem',
                    color: 'var(--text-muted)',
                    background: 'var(--bg-surface)',
                    padding: '8px 14px 4px',
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                });
                sep.appendChild(td);
                tbody.appendChild(sep);
            }

            const tr = el('tr', { cls: row.has_conflict ? 'conflict-row' : '' });

            // Day
            const tdDay = el('td', { cls: 'col-day' });
            tdDay.textContent = row.day_label || '—';
            tr.appendChild(tdDay);

            // Time
            const tdTime = el('td', { cls: 'col-time' });
            tdTime.textContent = row.start_time && row.end_time
                ? `${row.start_time}–${row.end_time}`
                : row.start_time || '—';
            tr.appendChild(tdTime);

            // Room
            const tdRoom = el('td', { cls: 'col-room' });
            tdRoom.textContent = row.room_name || '—';
            tr.appendChild(tdRoom);

            // Code
            const tdCode = el('td', { cls: 'col-code' });
            tdCode.textContent = row.code;
            if (row.has_conflict) {
                const flag = el('span', { cls: 'output-conflict-flag' });
                flag.textContent = '⚠';
                tdCode.appendChild(document.createTextNode(' '));
                tdCode.appendChild(flag);
            }
            tr.appendChild(tdCode);

            // Title
            const tdTitle = el('td', { cls: 'col-title' });
            tdTitle.textContent = row.title;
            if (row.submission_type) {
                const typeEl = el('div');
                Object.assign(typeEl.style, { fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' });
                typeEl.textContent = row.submission_type;
                tdTitle.appendChild(typeEl);
            }
            tr.appendChild(tdTitle);

            // Speakers
            const tdSpeakers = el('td', { cls: 'col-speakers' });
            for (const sp of (row.speakers || [])) {
                const nameEl = el('div');
                nameEl.textContent = sp.name;
                tdSpeakers.appendChild(nameEl);
                if (sp.telegram) {
                    const tgEl = el('div', { cls: 'speaker-telegram-small' });
                    tgEl.textContent = `${sp.telegram}`;
                    tdSpeakers.appendChild(tgEl);
                }
            }
            tr.appendChild(tdSpeakers);

            // Resources
            const tdRes = el('td', { cls: 'col-resources' });
            if ((row.resources || []).length > 0) {
                const list = el('div', { cls: 'output-resource-list' });
                for (const r of row.resources) {
                    const item = el('div', { cls: 'output-resource-item' });
                    const nameEl = el('span', { cls: 'resource-name' });
                    nameEl.textContent = r.resource_name;
                    item.appendChild(nameEl);
                    if (r.note) {
                        const noteEl = el('span', { cls: 'resource-note' });
                        noteEl.textContent = ` (${r.note})`;
                        item.appendChild(noteEl);
                    }
                    // Effective depts
                    const depts = r.department_override
                        ? [r.department_override]
                        : (r.resource_departments || []);
                    const deptWrap = el('span');
                    deptWrap.style.marginLeft = '6px';
                    for (const d of depts) deptWrap.appendChild(deptPill(d));
                    item.appendChild(deptWrap);
                    list.appendChild(item);
                }
                tdRes.appendChild(list);
            } else {
                tdRes.textContent = '—';
                tdRes.style.color = 'var(--text-muted)';
            }
            tr.appendChild(tdRes);

            // Comments
            const tdCmt = el('td', { cls: 'col-comments' });
            if ((row.comments || []).length > 0) {
                const list = el('div', { cls: 'output-comment-list' });
                for (const c of row.comments) {
                    const item = el('div', { cls: 'output-comment-item' });
                    item.appendChild(deptPill(c.department));
                    const textEl = el('span');
                    textEl.style.marginLeft = '6px';
                    textEl.textContent = c.text;
                    item.appendChild(textEl);
                    list.appendChild(item);
                }
                tdCmt.appendChild(list);
            } else {
                tdCmt.textContent = '—';
                tdCmt.style.color = 'var(--text-muted)';
            }
            tr.appendChild(tdCmt);

            tbody.appendChild(tr);
        }
    }

    /**
     * Updates the footer with the filtered event count, current department, and active filter descriptions.
     */
    function updateFooter() {
        if (!footerEl) return;
        const rows = getFilteredRows();
        const notes = [];
        if (selectedResourceIds.size > 0) {
            notes.push(`${selectedResourceIds.size} resource${selectedResourceIds.size !== 1 ? 's' : ''}`);
        }
        if (selectedRoomNames.size > 0) {
            notes.push(`${selectedRoomNames.size} room${selectedRoomNames.size !== 1 ? 's' : ''}`);
        }
        if (searchQuery) {
            notes.push(`search "${searchQuery}"`);
        }
        const filterNote = notes.length > 0
            ? ` · Filtered by ${notes.join(', ')}`
            : '';
        footerEl.textContent = `${rows.length} event slot${rows.length !== 1 ? 's' : ''} · Department: ${currentDept === 'all' ? 'All' : currentDept}${filterNote}`;
    }

    // ---------------------------------------------------------------------------
    // Department tabs
    // ---------------------------------------------------------------------------

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => {
                t.classList.remove('active');
                t.setAttribute('aria-selected', 'false');
            });
            tab.classList.add('active');
            tab.setAttribute('aria-selected', 'true');
            currentDept = tab.dataset.dept;
            loadOutput(currentDept);
        });
    });

    // ---------------------------------------------------------------------------
    // CSV export
    // ---------------------------------------------------------------------------

    exportBtn?.addEventListener('click', () => {
        const url = `${BASE_PATH}/api/output/csv?dept=${encodeURIComponent(currentDept)}`;
        const a = document.createElement('a');
        a.href = url;
        a.download = `operations_${currentDept}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });

    // ---------------------------------------------------------------------------
    // Boot
    // ---------------------------------------------------------------------------

    loadOutput('all');
    loadResourceFilter();

})();
