/**
 * output.js — Output page: department tabs, table rendering, CSV export.
 */

(function () {
    'use strict';

    let currentDept = 'all';
    let currentRows = [];

    const tabs = document.querySelectorAll('.dept-tab');
    const tbody = document.getElementById('output-tbody');
    const tableEl = document.getElementById('output-table');
    const emptyEl = document.getElementById('output-empty');
    const footerEl = document.getElementById('output-footer');
    const exportBtn = document.getElementById('btn-export-csv');

    // ---------------------------------------------------------------------------
    // Load output data
    // ---------------------------------------------------------------------------

    async function loadOutput(dept) {
        showLoading();
        try {
            const data = await apiFetch(`/api/output?dept=${encodeURIComponent(dept)}`);
            currentRows = data.rows || [];
            renderTable();
            updateFooter();
        } catch (e) {
            showToast('Failed to load output: ' + e.message, 'error');
        }
    }

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

        if (currentRows.length === 0) {
            tableEl.style.display = 'none';
            emptyEl.classList.remove('hidden');
            return;
        }

        tableEl.style.display = '';
        emptyEl.classList.add('hidden');

        let lastDay = null;

        for (const row of currentRows) {
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

    function updateFooter() {
        if (!footerEl) return;
        footerEl.textContent = `${currentRows.length} event slot${currentRows.length !== 1 ? 's' : ''} · Department: ${currentDept === 'all' ? 'All' : currentDept}`;
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

})();
