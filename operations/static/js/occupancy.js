/**
 * occupancy.js — Occupancy page: rate room fullness for current/upcoming events.
 *
 * Ratings: Empty | Low | Medium | High | Full (colour-coded buttons)
 * Shows events currently running OR starting within the next hour.
 * Mobile-first: large tap targets. Auto-refreshes every 30 s.
 * Rated events disappear unless "Show Rated" is checked.
 */

(function () {
    'use strict';

    const AUTO_REFRESH_MS = 30_000;

    // -------------------------------------------------------------------------
    // Rating config — colour + icon per level
    // -------------------------------------------------------------------------

    const RATING_CONFIG = {
        Empty:  { color: '#6b7280', bg: '#f3f4f6', icon: '⬜', label: 'Empty'  },
        Low:    { color: '#15803d', bg: '#dcfce7', icon: '🟢', label: 'Low'    },
        Medium: { color: '#a16207', bg: '#fef9c3', icon: '🟡', label: 'Medium' },
        High:   { color: '#c2410c', bg: '#ffedd5', icon: '🟠', label: 'High'   },
        Full:   { color: '#dc2626', bg: '#fee2e2', icon: '🔴', label: 'Full'   },
    };
    const RATINGS = ['Empty', 'Low', 'Medium', 'High', 'Full'];

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    let currentSlots = [];
    let autoTimer    = null;

    // -------------------------------------------------------------------------
    // DOM refs
    // -------------------------------------------------------------------------

    const grid         = document.getElementById('occ-grid');
    const countLabel   = document.getElementById('occ-count-label');
    const liveDot      = document.getElementById('occ-live-dot');
    const roomSelect   = document.getElementById('occ-room-select');
    const showRatedChk = document.getElementById('occ-show-rated');
    const testModeChk  = document.getElementById('occ-test-mode');
    const testAtInput  = document.getElementById('occ-test-at');
    const testBadge    = document.getElementById('occ-test-badge');
    const refreshBtn   = document.getElementById('occ-refresh-btn');

    // -------------------------------------------------------------------------
    // Load data from API
    // -------------------------------------------------------------------------

    async function load() {
        const params = new URLSearchParams();

        const room = roomSelect?.value || '';
        if (room) params.set('rooms', room);
        if (showRatedChk?.checked) params.set('show_rated', '1');
        if (testModeChk?.checked && testAtInput?.value) {
            params.set('at', testAtInput.value);
        }

        // Show loading state
        grid.textContent = '';
        const loadEl = document.createElement('p');
        loadEl.className = 'occ-status-msg';
        loadEl.textContent = '⏳ Fetching events…';
        grid.appendChild(loadEl);
        if (countLabel) countLabel.textContent = 'Loading…';

        try {
            const data = await apiFetch(`/api/occupancy?${params}`);
            currentSlots = data.slots || [];
            populateRoomFilter(data.all_rooms || []);
            renderGrid();
            updateStatus(data);
        } catch (e) {
            showToast('Failed to load occupancy data: ' + e.message, 'error');
            if (liveDot) liveDot.className = 'status-dot error';
            grid.textContent = '';
            const errEl = document.createElement('p');
            errEl.className = 'occ-status-msg';
            errEl.textContent = '⚠ Error loading events — ' + e.message;
            grid.appendChild(errEl);
        }
    }

    // -------------------------------------------------------------------------
    // Room filter dropdown
    // -------------------------------------------------------------------------

    function populateRoomFilter(rooms) {
        if (!roomSelect) return;
        const current = roomSelect.value;
        while (roomSelect.options.length > 1) roomSelect.remove(1);
        for (const room of rooms) {
            const opt = document.createElement('option');
            opt.value = room;
            opt.textContent = room;
            roomSelect.appendChild(opt);
        }
        if (current && [...roomSelect.options].some(o => o.value === current)) {
            roomSelect.value = current;
        }
    }

    roomSelect?.addEventListener('change', () => load());

    // -------------------------------------------------------------------------
    // Render — flat list, no room grouping (room shown inside each card)
    // -------------------------------------------------------------------------

    function renderGrid() {
        // Clear everything
        grid.textContent = '';

        if (currentSlots.length === 0) {
            const msg = document.createElement('p');
            msg.className = 'occ-status-msg';
            msg.textContent = showRatedChk?.checked
                ? 'No events in the current window.'
                : 'No unrated events right now. Enable "Show Rated" to see rated events, or wait for the next ones.';
            grid.appendChild(msg);
            return;
        }

        for (const slot of currentSlots) {
            grid.appendChild(makeCard(slot));
        }
    }

    // -------------------------------------------------------------------------
    // Build one event card
    // -------------------------------------------------------------------------

    function makeCard(slot) {
        const isRated   = !!slot.rating;
        const cfg       = isRated ? RATING_CONFIG[slot.rating] : null;
        const isRunning = slot.is_running;

        // Outer card wrapper
        const card = document.createElement('div');
        card.className = 'occ-card'
            + (isRated   ? ' occ-card-rated'   : '')
            + (isRunning ? ' occ-card-running'  : '');

        // Coloured track bar
        const bar = document.createElement('div');
        bar.className = 'occ-card-track';
        bar.style.background = slot.track?.color || '#3b82f6';
        card.appendChild(bar);

        // Card body
        const body = document.createElement('div');
        body.className = 'occ-card-body';

        // Top meta row: time + room + optional "Now" badge
        const metaRow = document.createElement('div');
        metaRow.className = 'occ-meta-row';

        const timeEl = document.createElement('span');
        timeEl.className = 'occ-time';
        timeEl.textContent = fmtTimeRange(slot.start, slot.end);
        metaRow.appendChild(timeEl);

        const roomEl = document.createElement('span');
        roomEl.className = 'occ-room';
        roomEl.textContent = slot.room_name || '—';
        metaRow.appendChild(roomEl);

        if (isRunning) {
            const nowBadge = document.createElement('span');
            nowBadge.className = 'occ-running-badge';
            nowBadge.textContent = '● Now';
            metaRow.appendChild(nowBadge);
        }

        body.appendChild(metaRow);

        // Event title
        const titleEl = document.createElement('div');
        titleEl.className = 'occ-title';
        titleEl.textContent = slot.title;
        body.appendChild(titleEl);

        // Current rating chip (shown when "Show Rated" is checked)
        if (isRated && cfg) {
            const chip = document.createElement('div');
            chip.className = 'occ-current-rating';
            chip.style.color      = cfg.color;
            chip.style.background = cfg.bg;
            chip.textContent = cfg.icon + ' ' + cfg.label;
            if (slot.rated_by) {
                const byEl = document.createElement('span');
                byEl.className = 'occ-rated-by';
                byEl.textContent = ' · ' + slot.rated_by;
                chip.appendChild(byEl);
            }
            body.appendChild(chip);
        }

        // Rating buttons — always shown; disabled if no write access
        const btnRow = document.createElement('div');
        btnRow.className = 'occ-rating-btns';

        for (const r of RATINGS) {
            const rc  = RATING_CONFIG[r];
            const btn = document.createElement('button');
            btn.type      = 'button';
            btn.className = 'occ-rating-btn occ-rating-' + r.toLowerCase()
                + (slot.rating === r ? ' occ-rating-btn-active' : '');
            btn.title     = CAN_WRITE ? r : 'Read-only — cannot rate';
            btn.disabled  = !CAN_WRITE;

            const iconEl = document.createElement('span');
            iconEl.className = 'occ-btn-icon';
            iconEl.textContent = rc.icon;
            btn.appendChild(iconEl);

            const lblEl = document.createElement('span');
            lblEl.className = 'occ-btn-label';
            lblEl.textContent = r;
            btn.appendChild(lblEl);

            if (CAN_WRITE) {
                btn.addEventListener('click', () => rateSlot(slot, r, card));
            }
            btnRow.appendChild(btn);
        }
        body.appendChild(btnRow);

        if (!CAN_WRITE) {
            const roNote = document.createElement('p');
            roNote.className = 'occ-ro-note';
            roNote.textContent = '🔒 Read-only access — rating requires write permission';
            body.appendChild(roNote);
        }

        card.appendChild(body);
        return card;
    }

    // -------------------------------------------------------------------------
    // Rate action
    // -------------------------------------------------------------------------

    async function rateSlot(slot, rating, cardEl) {
        const btns = cardEl.querySelectorAll('.occ-rating-btn');
        btns.forEach(b => { b.disabled = true; });

        try {
            await apiFetch(
                `/api/slots/${encodeURIComponent(slot.code)}/${slot.slot_index}/rate`,
                { method: 'POST', body: JSON.stringify({ rating }) }
            );
            showToast(rating + ' — ' + slot.title, 'success');
            slot.rating = rating;

            if (!showRatedChk?.checked) {
                // Animate card out, then remove it
                cardEl.classList.add('occ-card-fade-out');
                setTimeout(() => cardEl.remove(), 320);
            } else {
                // Rebuild card in-place to update the rating chip + active button
                const newCard = makeCard(slot);
                cardEl.replaceWith(newCard);
            }
        } catch (e) {
            showToast('Failed to save rating: ' + e.message, 'error');
            btns.forEach(b => { b.disabled = false; });
        }
    }

    // -------------------------------------------------------------------------
    // Status bar
    // -------------------------------------------------------------------------

    function updateStatus(data) {
        if (countLabel) {
            const n      = currentSlots.length;
            const isTest = data.is_test_mode || false;
            let refLabel = '';
            if (isTest && data.reference_time) {
                try {
                    const d = new Date(data.reference_time);
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
    }

    // -------------------------------------------------------------------------
    // Auto-refresh
    // -------------------------------------------------------------------------

    function scheduleRefresh() {
        clearTimeout(autoTimer);
        if (testModeChk?.checked) return;
        autoTimer = setTimeout(async () => {
            if (liveDot) liveDot.className = 'status-dot loading';
            await load();
            scheduleRefresh();
        }, AUTO_REFRESH_MS);
    }

    // -------------------------------------------------------------------------
    // Control event listeners
    // -------------------------------------------------------------------------

    showRatedChk?.addEventListener('change', () => load());

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

    refreshBtn?.addEventListener('click', async () => {
        refreshBtn.disabled = true;
        if (liveDot) liveDot.className = 'status-dot loading';
        await load();
        scheduleRefresh();
        refreshBtn.disabled = false;
    });

    // -------------------------------------------------------------------------
    // Boot
    // -------------------------------------------------------------------------

    load().then(() => scheduleRefresh());

})();
