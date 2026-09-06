/**
 * occupancies.js — Dedicated Room Occupancies Viewer for Eurofurence Conventions.
 *
 * Provides:
 *   - Multi-convention selection (EF 30, EF 29, EF 28, ...)
 *   - Visual overview: Stats metrics and interactive multi-segment distribution bar
 *   - Filter toolbar: search (title/code/room/track), level, room, track, day, sort
 *   - Visual 5-segment occupancy level gauges per card
 *   - Cross-links to convention attendee feedback
 *   - Shareable URL parameters (?con=...&q=...&level=...&room=...&track=...&day=...&sort=...&item=...)
 *   - Safe DOM manipulation (no unsanitized innerHTML)
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    let conventions = [];
    let currentConId = null;
    let currentData = null;
    let conventionRequestSequence = 0;

    const filters = {
        q: '',
        level: '',
        room: '',
        track: '',
        day: '',
        sort: 'level_desc',
        targetItem: null,
    };

    const LEVEL_CONFIG = [
        { key: 'Full',   minLevel: 4, label: 'Full (4–5)',   dotColor: '#dc2626', cssSegment: 'segment-full',   cssPip: 'pip-full',   cssBadge: 'occ-lvl-full' },
        { key: 'High',   minLevel: 3, label: 'High (3)',     dotColor: '#ea580c', cssSegment: 'segment-high',   cssPip: 'pip-high',   cssBadge: 'occ-lvl-high' },
        { key: 'Medium', minLevel: 2, label: 'Medium (2)',   dotColor: '#ca8a04', cssSegment: 'segment-medium', cssPip: 'pip-medium', cssBadge: 'occ-lvl-medium' },
        { key: 'Low',    minLevel: 1, label: 'Low (1)',      dotColor: '#16a34a', cssSegment: 'segment-low',    cssPip: 'pip-low',    cssBadge: 'occ-lvl-low' },
        { key: 'Empty',  minLevel: 0, label: 'Empty (0)',    dotColor: '#6b7280', cssSegment: 'segment-empty',  cssPip: 'pip-empty',  cssBadge: 'occ-lvl-empty' },
    ];

    // -----------------------------------------------------------------------
    // DOM References
    // -----------------------------------------------------------------------
    const conPillGroup         = document.getElementById('con-pill-group');
    const conSelectDropdown    = document.getElementById('con-select');

    // Visual section
    const occVisualSection     = document.getElementById('occ-visual-section');
    const statTotalRated       = document.getElementById('stat-total-rated');
    const statAvgLevel         = document.getElementById('stat-avg-level');
    const statAvgPercent       = document.getElementById('stat-avg-percent');
    const statCountFull        = document.getElementById('stat-count-full');
    const statCountHigh        = document.getElementById('stat-count-high');
    const statTotalRooms       = document.getElementById('stat-total-rooms');
    const distributionBarTrack = document.getElementById('distribution-bar-track');
    const distributionLegend   = document.getElementById('distribution-legend');

    // Toolbar & Filters
    const toolbarCard          = document.getElementById('toolbar-card');
    const searchInput          = document.getElementById('filter-search');
    const btnClearSearch       = document.getElementById('btn-clear-search');
    const filterLevel          = document.getElementById('filter-level');
    const groupFilterRoom      = document.getElementById('group-filter-room');
    const filterRoom           = document.getElementById('filter-room');
    const groupFilterTrack     = document.getElementById('group-filter-track');
    const filterTrack          = document.getElementById('filter-track');
    const groupFilterDay       = document.getElementById('group-filter-day');
    const filterDay            = document.getElementById('filter-day');
    const filterSort           = document.getElementById('filter-sort');
    const btnResetFilters      = document.getElementById('btn-reset-filters');
    const activeFilterBadge    = document.getElementById('active-filter-badge');

    // Results & Grid
    const resultsCount         = document.getElementById('results-count');
    const occMetaInfo          = document.getElementById('occ-meta-info');
    const loadingState         = document.getElementById('loading-state');
    const occGrid              = document.getElementById('occ-grid');
    const emptyState           = document.getElementById('empty-state');
    const emptyTitle           = document.getElementById('empty-title');
    const emptyDesc            = document.getElementById('empty-desc');
    const btnEmptyReset        = document.getElementById('btn-empty-reset');

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function getLevelInfo(level, ratingStr) {
        const lvl = level != null ? Number(level) : 0;
        if (lvl >= 4 || ratingStr === 'Full') {
            return { label: 'Full', levelNum: lvl, badgeText: `🔴 Full (${lvl}/5)`, cssBadge: 'occ-lvl-full', cssPip: 'pip-full' };
        }
        if (lvl === 3 || ratingStr === 'High') {
            return { label: 'High', levelNum: 3, badgeText: '🟠 High (3/5)', cssBadge: 'occ-lvl-high', cssPip: 'pip-high' };
        }
        if (lvl === 2 || ratingStr === 'Medium') {
            return { label: 'Medium', levelNum: 2, badgeText: '🟡 Medium (2/5)', cssBadge: 'occ-lvl-medium', cssPip: 'pip-medium' };
        }
        if (lvl === 1 || ratingStr === 'Low') {
            return { label: 'Low', levelNum: 1, badgeText: '🟢 Low (1/5)', cssBadge: 'occ-lvl-low', cssPip: 'pip-low' };
        }
        return { label: 'Empty', levelNum: 0, badgeText: '⬜ Empty (0/5)', cssBadge: 'occ-lvl-empty', cssPip: 'pip-empty' };
    }

    // -----------------------------------------------------------------------
    // URL Parameter Synchronization
    // -----------------------------------------------------------------------
    function readUrlParams() {
        const params = new URLSearchParams(window.location.search);
        return {
            con:   params.get('con') || '',
            q:     params.get('q') || '',
            level: params.get('level') || '',
            room:  params.get('room') || '',
            track: params.get('track') || '',
            day:   params.get('day') || '',
            sort:  params.get('sort') || 'level_desc',
            item:  params.get('item') || (window.location.hash ? window.location.hash.substring(1) : ''),
        };
    }

    function updateUrlParams() {
        const url = new URL(window.location.href);
        const params = url.searchParams;

        if (currentConId) params.set('con', currentConId);
        else params.delete('con');

        if (filters.q) params.set('q', filters.q);
        else params.delete('q');

        if (filters.level) params.set('level', filters.level);
        else params.delete('level');

        if (filters.room) params.set('room', filters.room);
        else params.delete('room');

        if (filters.track) params.set('track', filters.track);
        else params.delete('track');

        if (filters.day) params.set('day', filters.day);
        else params.delete('day');

        if (filters.sort && filters.sort !== 'level_desc') params.set('sort', filters.sort);
        else params.delete('sort');

        if (filters.targetItem) params.set('item', filters.targetItem);
        else params.delete('item');

        window.history.replaceState(null, '', url.pathname + (params.toString() ? '?' + params.toString() : ''));
    }

    // -----------------------------------------------------------------------
    // Initialization
    // -----------------------------------------------------------------------
    async function init() {
        const initialParams = readUrlParams();
        filters.q = initialParams.q;
        filters.level = initialParams.level;
        filters.room = initialParams.room;
        filters.track = initialParams.track;
        filters.day = initialParams.day;
        filters.sort = initialParams.sort;
        filters.targetItem = initialParams.item;

        // Populate controls from URL
        searchInput.value = filters.q;
        btnClearSearch.classList.toggle('hidden', !filters.q);
        filterLevel.value = filters.level;
        filterSort.value = filters.sort;

        try {
            const resp = await apiFetch('/api/conventions');
            conventions = (resp && resp.conventions) || [];
            if (!conventions.length) {
                showError('No convention data available.');
                return;
            }

            renderConventionSelectors();

            let selectedId = initialParams.con;
            if (!selectedId || !conventions.some(c => c.id === selectedId)) {
                // Default to first convention (newest, e.g. ef_30)
                selectedId = conventions[0].id;
            }

            selectConvention(selectedId);
        } catch (err) {
            showError('Failed to load conventions: ' + err.message);
        }

        bindEvents();
    }

    // -----------------------------------------------------------------------
    // Convention Selection
    // -----------------------------------------------------------------------
    function renderConventionSelectors() {
        conPillGroup.replaceChildren();
        conSelectDropdown.replaceChildren();

        conventions.forEach(con => {
            const pill = el('button', {
                cls: 'con-pill',
                type: 'button',
                title: con.title || con.name,
                onclick: () => selectConvention(con.id),
            }, con.name);
            pill.dataset.conId = con.id;
            conPillGroup.appendChild(pill);

            const opt = el('option', { value: con.id }, con.title || con.name);
            conSelectDropdown.appendChild(opt);
        });
    }

    async function selectConvention(conId) {
        if (currentConId === conId && currentData) return;
        const requestSequence = ++conventionRequestSequence;
        currentConId = conId;
        currentData = null;

        document.querySelectorAll('.con-pill').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.conId === conId);
        });
        conSelectDropdown.value = conId;

        updateUrlParams();

        loadingState.style.display = 'flex';
        occGrid.style.display = 'none';
        emptyState.classList.add('hidden');
        occVisualSection.style.display = 'none';
        toolbarCard.style.display = 'block';

        try {
            const data = await apiFetch(`/api/occupancies/${encodeURIComponent(conId)}`);
            if (requestSequence !== conventionRequestSequence || currentConId !== conId) return;
            currentData = data;

            if (!data.convention || !data.convention.has_occupancy || !data.items || data.items.length === 0) {
                renderNoOccupancyConvention(data.convention);
                return;
            }

            // Populate filters and visualization
            setupFilterOptions(data.convention);
            renderVisualOverview(data.stats, data.convention);
            applyFiltersAndRender();

            if (filters.targetItem) {
                setTimeout(() => scrollToItem(filters.targetItem), 150);
            }
        } catch (err) {
            if (requestSequence !== conventionRequestSequence || currentConId !== conId) return;
            showError('Failed to load room occupancies: ' + err.message);
        } finally {
            if (requestSequence === conventionRequestSequence && currentConId === conId) {
                loadingState.style.display = 'none';
            }
        }
    }

    function renderNoOccupancyConvention(con) {
        occVisualSection.style.display = 'none';
        toolbarCard.style.display = 'none';
        occGrid.style.display = 'none';
        emptyState.classList.remove('hidden');

        const conName = (con && con.name) || currentConId.toUpperCase();
        emptyTitle.textContent = `No room occupancy data for ${conName}`;
        emptyDesc.textContent = 'Room crowd & occupancy monitoring was introduced for Eurofurence starting with EF 30. You can browse attendee reviews in the Feedback tab, or switch to EF 30.';

        btnEmptyReset.textContent = 'Switch to EF 30';
        btnEmptyReset.onclick = () => selectConvention('ef_30');
    }

    // -----------------------------------------------------------------------
    // Filter Populating & Dynamic Selects
    // -----------------------------------------------------------------------
    function setupFilterOptions(con) {
        // Room Filter
        filterRoom.replaceChildren(el('option', { value: '' }, 'All Rooms'));
        if (con.rooms && con.rooms.length > 0) {
            groupFilterRoom.style.display = 'flex';
            con.rooms.forEach(r => {
                filterRoom.appendChild(el('option', { value: r }, r));
            });
            filterRoom.value = filters.room;
        } else {
            groupFilterRoom.style.display = 'none';
            filterRoom.value = '';
            filters.room = '';
        }

        // Track Filter
        filterTrack.replaceChildren(el('option', { value: '' }, 'All Tracks'));
        if (con.tracks && con.tracks.length > 0) {
            groupFilterTrack.style.display = 'flex';
            con.tracks.forEach(tr => {
                filterTrack.appendChild(el('option', { value: tr.name }, tr.name));
            });
            filterTrack.value = filters.track;
        } else {
            groupFilterTrack.style.display = 'none';
            filterTrack.value = '';
            filters.track = '';
        }

        // Day Filter
        filterDay.replaceChildren(el('option', { value: '' }, 'All Days'));
        if (con.days && con.days.length > 0) {
            groupFilterDay.style.display = 'flex';
            con.days.forEach(d => {
                filterDay.appendChild(el('option', { value: d }, d));
            });
            filterDay.value = filters.day;
        } else {
            groupFilterDay.style.display = 'none';
            filterDay.value = '';
            filters.day = '';
        }
    }

    // -----------------------------------------------------------------------
    // Visual Overview & Interactive Distribution Bar
    // -----------------------------------------------------------------------
    function renderVisualOverview(stats, con) {
        statTotalRated.textContent = (stats.total_rated || 0).toLocaleString();
        statAvgLevel.textContent = stats.avg_level != null ? `${stats.avg_level.toFixed(1)} / 5.0` : '—';
        if (stats.avg_level != null) {
            const pct = Math.round((stats.avg_level / 5.0) * 100);
            statAvgPercent.textContent = `(${pct}% cap)`;
        } else {
            statAvgPercent.textContent = '';
        }

        const dist = stats.distribution || {};
        const fullCount = dist.Full || 0;
        const highCount = dist.High || 0;
        statCountFull.textContent = fullCount.toLocaleString();
        statCountHigh.textContent = highCount.toLocaleString();
        statTotalRooms.textContent = (con.rooms ? con.rooms.length : stats.total_rooms || 0).toLocaleString();

        renderDistributionBar(dist, stats.total_rated || 1);
        renderDistributionLegend(dist, stats.total_rated || 1);

        occVisualSection.style.display = 'flex';
    }

    function renderDistributionBar(dist, total) {
        distributionBarTrack.replaceChildren();

        LEVEL_CONFIG.forEach(cfg => {
            const count = dist[cfg.key] || 0;
            if (count === 0) return;

            const pct = (count / total) * 100;
            const segment = el('div', {
                cls: `distribution-segment ${cfg.cssSegment}`,
                style: { width: `${pct.toFixed(2)}%` },
                title: `${cfg.key}: ${count} slots (${pct.toFixed(1)}%) — Click to filter`,
                onclick: () => toggleLevelFilter(cfg.key),
            });

            // If width is generous, show text
            if (pct >= 14) {
                segment.textContent = `${cfg.key} (${count})`;
            } else if (pct >= 6) {
                segment.textContent = `${count}`;
            }

            // Dim or highlight if level is active
            if (filters.level) {
                if (filters.level === cfg.key) {
                    segment.classList.add('active-segment');
                } else {
                    segment.classList.add('dimmed');
                }
            }

            distributionBarTrack.appendChild(segment);
        });
    }

    function renderDistributionLegend(dist, total) {
        distributionLegend.replaceChildren();

        LEVEL_CONFIG.forEach(cfg => {
            const count = dist[cfg.key] || 0;
            const pct = total > 0 ? Math.round((count / total) * 100) : 0;
            const isActive = filters.level === cfg.key;

            const pill = el('button', {
                cls: `legend-pill ${isActive ? 'active' : ''}`,
                type: 'button',
                title: `Filter by ${cfg.label}`,
                onclick: () => toggleLevelFilter(cfg.key),
            },
                el('span', { cls: 'legend-dot', style: { background: cfg.dotColor } }),
                cfg.label,
                el('span', { cls: 'legend-count' }, `${count} (${pct}%)`)
            );

            distributionLegend.appendChild(pill);
        });
    }

    function toggleLevelFilter(lvlKey) {
        if (filters.level === lvlKey) {
            filters.level = '';
        } else {
            filters.level = lvlKey;
        }
        filterLevel.value = filters.level;
        updateUrlParams();

        if (currentData && currentData.stats) {
            renderDistributionBar(currentData.stats.distribution, currentData.stats.total_rated || 1);
            renderDistributionLegend(currentData.stats.distribution, currentData.stats.total_rated || 1);
        }

        applyFiltersAndRender();
    }

    // -----------------------------------------------------------------------
    // Filtering and Sorting
    // -----------------------------------------------------------------------
    function getFilteredItems() {
        if (!currentData || !currentData.items) return [];
        const qLower = (filters.q || '').trim().toLowerCase();

        return currentData.items.filter(item => {
            // Text search (matches title, code, key, room, track name)
            if (qLower) {
                const matchCode  = item.code.toLowerCase().includes(qLower);
                const matchKey   = item.key.toLowerCase().includes(qLower);
                const matchTitle = (item.title || '').toLowerCase().includes(qLower);
                const matchRoom  = (item.room || '').toLowerCase().includes(qLower);
                const matchTrack = item.track && item.track.name.toLowerCase().includes(qLower);

                if (!matchCode && !matchKey && !matchTitle && !matchRoom && !matchTrack) {
                    return false;
                }
            }

            // Level filter
            if (filters.level) {
                if (item.rating !== filters.level) {
                    return false;
                }
            }

            // Room filter
            if (filters.room) {
                if (item.room !== filters.room) {
                    return false;
                }
            }

            // Track filter
            if (filters.track) {
                if (!item.track || item.track.name !== filters.track) {
                    return false;
                }
            }

            // Day filter
            if (filters.day) {
                if (item.day !== filters.day) {
                    return false;
                }
            }

            return true;
        }).sort((a, b) => {
            switch (filters.sort) {
                case 'level_asc':
                    return (a.level - b.level) || a.title.localeCompare(b.title);
                case 'time': {
                    const dayCmp = (a.day || '9999').localeCompare(b.day || '9999');
                    if (dayCmp !== 0) return dayCmp;
                    const timeCmp = (a.start_time || '9999').localeCompare(b.start_time || '9999');
                    if (timeCmp !== 0) return timeCmp;
                    return a.title.localeCompare(b.title);
                }
                case 'title':
                    return a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });
                case 'room': {
                    const roomCmp = (a.room || '').localeCompare(b.room || '');
                    if (roomCmp !== 0) return roomCmp;
                    return - (a.level - b.level);
                }
                case 'level_desc':
                default:
                    return (b.level - a.level) ||
                        (a.day || '9999').localeCompare(b.day || '9999') ||
                        (a.start_time || '9999').localeCompare(b.start_time || '9999') ||
                        a.title.localeCompare(b.title);
            }
        });
    }

    function applyFiltersAndRender() {
        const filtered = getFilteredItems();

        const isFiltered = Boolean(
            filters.q || filters.level || filters.room ||
            filters.track || filters.day || (filters.sort && filters.sort !== 'level_desc')
        );

        btnResetFilters.classList.toggle('hidden', !isFiltered);
        activeFilterBadge.classList.toggle('hidden', !isFiltered);

        if (filtered.length === 0) {
            occGrid.style.display = 'none';
            emptyState.classList.remove('hidden');
            emptyTitle.textContent = isFiltered ? 'No matching occupancy ratings' : 'No occupancy records';
            emptyDesc.textContent = isFiltered
                ? 'Try adjusting your search criteria, clearing level/room filters, or switching conventions.'
                : 'No occupancy records are available for this convention.';
            btnEmptyReset.textContent = 'Reset Filters';
            btnEmptyReset.onclick = resetFilters;
            resultsCount.textContent = '0 records matching filters';
            occMetaInfo.textContent = '';
            return;
        }

        emptyState.classList.add('hidden');
        resultsCount.textContent = `Showing ${filtered.length} of ${currentData.items.length} rated slots`;
        occMetaInfo.textContent = currentData.convention.has_events ? '✨ Enriched with event & feedback data' : '';

        renderOccupancyCards(filtered);
        occGrid.style.display = 'grid';
    }

    // -----------------------------------------------------------------------
    // Card Rendering
    // -----------------------------------------------------------------------
    function renderOccupancyCards(items) {
        occGrid.replaceChildren();

        items.forEach(item => {
            const card = el('article', {
                cls: 'occ-card',
                id: `occ-card-${item.key}`,
            });

            // Highlight border by track color if available
            if (item.track && item.track.color) {
                card.style.borderLeft = `5px solid ${item.track.color}`;
            }

            // Top section: Header & Level Gauge
            const topDiv = el('div');

            const header = el('div', { cls: 'occ-card-header' });
            const leftCol = el('div', { cls: 'occ-card-header-left' });

            // Title
            const titleEl = el('h2', { cls: 'occ-card-title' }, item.title);
            leftCol.appendChild(titleEl);

            // Badges row
            const badgesRow = el('div', { cls: 'occ-card-badges-row' });
            badgesRow.appendChild(el('span', {
                cls: 'occ-code-badge',
                title: item.slot_index > 0 ? `Event Code with Slot ${item.slot_index}` : 'Event Code',
            }, item.slot_index > 0 ? item.key : item.code));

            if (item.track) {
                badgesRow.appendChild(el('span', {
                    cls: 'track-badge',
                    style: {
                        background: `${item.track.color}15`,
                        color: item.track.color,
                        borderColor: `${item.track.color}40`,
                    },
                },
                    el('span', { cls: 'track-dot', style: { background: item.track.color } }),
                    item.track.name
                ));
            }

            leftCol.appendChild(badgesRow);
            header.appendChild(leftCol);

            // Level Gauge / Meter on the right
            const lvlInfo = getLevelInfo(item.level, item.rating);
            const meterBox = el('div', { cls: 'occ-meter-box' });

            const badge = el('span', { cls: `occ-meter-badge ${lvlInfo.cssBadge}` }, lvlInfo.badgeText);
            meterBox.appendChild(badge);

            // 5-bar gauge
            const meterBars = el('div', { cls: 'occ-meter-bars', 'aria-hidden': 'true' });
            const fillCount = Math.max(0, Math.min(5, Number(item.level) || 0));
            for (let i = 1; i <= 5; i++) {
                const pip = el('span', {
                    cls: `occ-meter-pip ${i <= fillCount ? lvlInfo.cssPip : ''}`,
                });
                meterBars.appendChild(pip);
            }
            meterBox.appendChild(meterBars);
            header.appendChild(meterBox);

            topDiv.appendChild(header);

            // Metadata Lines (Room, Day, Time)
            const metaDiv = el('div', { cls: 'occ-card-meta' });

            if (item.room) {
                metaDiv.appendChild(el('div', { cls: 'occ-meta-line' },
                    el('span', { cls: 'occ-meta-icon' }, '📍'),
                    el('span', { cls: 'occ-meta-room' }, item.room)
                ));
            }

            if (item.day || item.start_time) {
                const timeText = [item.day, item.start_time].filter(Boolean).join(' at ');
                metaDiv.appendChild(el('div', { cls: 'occ-meta-line' },
                    el('span', { cls: 'occ-meta-icon' }, '📅'),
                    el('span', {}, timeText)
                ));
            }

            if (item.submission_type) {
                metaDiv.appendChild(el('div', { cls: 'occ-meta-line' },
                    el('span', { cls: 'occ-meta-icon' }, '📋'),
                    el('span', {}, item.submission_type)
                ));
            }

            topDiv.appendChild(metaDiv);

            // Abstract Collapsible Preview (if available)
            if (item.abstract) {
                const absContainer = el('div');
                let isExpanded = false;

                const toggleBtn = el('button', {
                    cls: 'occ-abstract-toggle',
                    type: 'button',
                    onclick: () => {
                        isExpanded = !isExpanded;
                        absText.style.display = isExpanded ? 'block' : 'none';
                        toggleBtn.textContent = isExpanded ? 'Hide description ▴' : 'Show description ▾';
                    },
                }, 'Show description ▾');

                const absText = el('div', {
                    cls: 'occ-abstract-text',
                    style: { display: 'none' },
                }, item.abstract);

                absContainer.appendChild(toggleBtn);
                absContainer.appendChild(absText);
                topDiv.appendChild(absContainer);
            }

            card.appendChild(topDiv);

            // Bottom section: Footer with Feedback Cross-Link and Share Button
            const footer = el('div', { cls: 'occ-card-footer' });

            if (item.feedback_count > 0) {
                const fbUrl = `${window.BASE_PATH || ''}/feedback?con=${encodeURIComponent(currentConId)}&event=${encodeURIComponent(item.code)}`;
                const avgText = item.feedback_avg_rating != null ? `★ ${item.feedback_avg_rating.toFixed(1)} • ` : '';
                const reviewWord = item.feedback_count === 1 ? 'review' : 'reviews';
                const fbLink = el('a', {
                    cls: 'occ-feedback-link',
                    href: fbUrl,
                    title: `View all ${item.feedback_count} attendee reviews for ${item.title}`,
                }, `💬 ${avgText}${item.feedback_count} ${reviewWord} → Feedback`);
                footer.appendChild(fbLink);
            } else {
                const noFb = el('span', { cls: 'occ-no-feedback' }, '💬 No feedback submitted');
                footer.appendChild(noFb);
            }

            // Share / Copy Link Button
            const shareBtn = el('button', {
                cls: 'occ-btn-share',
                type: 'button',
                title: 'Copy direct link to this card',
                onclick: () => copyCardLink(item.key),
            }, '🔗 Share');
            footer.appendChild(shareBtn);

            card.appendChild(footer);
            occGrid.appendChild(card);
        });
    }

    // -----------------------------------------------------------------------
    // Copy Link & Scroll Actions
    // -----------------------------------------------------------------------
    function copyCardLink(key) {
        filters.targetItem = key;
        updateUrlParams();

        const fullUrl = window.location.origin + window.location.pathname +
            `?con=${encodeURIComponent(currentConId)}&item=${encodeURIComponent(key)}`;

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(fullUrl).then(() => {
                showToast(`Direct link copied for ${key}!`, 'info');
            }).catch(() => {
                showToast(`Link: ${fullUrl}`, 'info', 5000);
            });
        } else {
            showToast(`Link: ${fullUrl}`, 'info', 5000);
        }

        highlightCard(key);
    }

    function scrollToItem(key) {
        const card = document.getElementById(`occ-card-${key}`);
        if (card) {
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            highlightCard(key);
        }
    }

    function highlightCard(key) {
        const card = document.getElementById(`occ-card-${key}`);
        if (card) {
            card.classList.add('occ-card-highlighted');
            setTimeout(() => card.classList.remove('occ-card-highlighted'), 2500);
        }
    }

    function resetFilters() {
        filters.q = '';
        filters.level = '';
        filters.room = '';
        filters.track = '';
        filters.day = '';
        filters.sort = 'level_desc';
        filters.targetItem = null;

        searchInput.value = '';
        btnClearSearch.classList.add('hidden');
        filterLevel.value = '';
        filterRoom.value = '';
        filterTrack.value = '';
        filterDay.value = '';
        filterSort.value = 'level_desc';

        updateUrlParams();

        if (currentData && currentData.stats) {
            renderDistributionBar(currentData.stats.distribution, currentData.stats.total_rated || 1);
            renderDistributionLegend(currentData.stats.distribution, currentData.stats.total_rated || 1);
        }

        applyFiltersAndRender();
    }

    function showError(msg) {
        loadingState.style.display = 'none';
        occGrid.style.display = 'none';
        occVisualSection.style.display = 'none';
        toolbarCard.style.display = 'none';
        emptyState.classList.remove('hidden');
        emptyTitle.textContent = 'Error loading occupancies';
        emptyDesc.textContent = msg;
    }

    // -----------------------------------------------------------------------
    // Event Listeners
    // -----------------------------------------------------------------------
    function bindEvents() {
        conSelectDropdown.addEventListener('change', (e) => {
            selectConvention(e.target.value);
        });

        // Search Input (debounced)
        const onSearchDebounced = debounce(() => {
            filters.q = searchInput.value.trim();
            btnClearSearch.classList.toggle('hidden', !filters.q);
            updateUrlParams();
            applyFiltersAndRender();
        }, 200);

        searchInput.addEventListener('input', onSearchDebounced);

        btnClearSearch.addEventListener('click', () => {
            searchInput.value = '';
            filters.q = '';
            btnClearSearch.classList.add('hidden');
            updateUrlParams();
            applyFiltersAndRender();
            searchInput.focus();
        });

        filterLevel.addEventListener('change', (e) => {
            filters.level = e.target.value;
            updateUrlParams();

            if (currentData && currentData.stats) {
                renderDistributionBar(currentData.stats.distribution, currentData.stats.total_rated || 1);
                renderDistributionLegend(currentData.stats.distribution, currentData.stats.total_rated || 1);
            }

            applyFiltersAndRender();
        });

        filterRoom.addEventListener('change', (e) => {
            filters.room = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        filterTrack.addEventListener('change', (e) => {
            filters.track = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        filterDay.addEventListener('change', (e) => {
            filters.day = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        filterSort.addEventListener('change', (e) => {
            filters.sort = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        btnResetFilters.addEventListener('click', resetFilters);
        btnEmptyReset.addEventListener('click', resetFilters);

        // Browser Back / Forward
        window.addEventListener('popstate', () => {
            const p = readUrlParams();
            filters.q = p.q;
            filters.level = p.level;
            filters.room = p.room;
            filters.track = p.track;
            filters.day = p.day;
            filters.sort = p.sort;
            filters.targetItem = p.item;

            searchInput.value = filters.q;
            btnClearSearch.classList.toggle('hidden', !filters.q);
            filterLevel.value = filters.level;
            filterRoom.value = filters.room;
            filterTrack.value = filters.track;
            filterDay.value = filters.day;
            filterSort.value = filters.sort;

            if (p.con && p.con !== currentConId) {
                selectConvention(p.con);
            } else {
                if (currentData && currentData.stats) {
                    renderDistributionBar(currentData.stats.distribution, currentData.stats.total_rated || 1);
                    renderDistributionLegend(currentData.stats.distribution, currentData.stats.total_rated || 1);
                }
                applyFiltersAndRender();
                if (p.item) scrollToItem(p.item);
            }
        });
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
