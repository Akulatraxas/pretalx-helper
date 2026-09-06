/**
 * feedback.js — Interactive Feedback Viewer for Eurofurence Conventions.
 *
 * Provides:
 *   - Dynamic convention selection (EF 28, EF 29, EF 30, ...)
 *   - Grouping by EventSlug with expandable/collapsible reviews
 *   - Track filtering and title search for EF 30+
 *   - Occupancy level visualization (rated 0 to 5)
 *   - URL query parameter sync for shareable views and direct event links
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    let conventions = [];
    let currentConId = null;
    let currentConData = null;
    let conventionRequestSequence = 0;

    const filters = {
        q: '',
        track: '',
        rating: '',
        occupancy: '',
        hasComments: false,
        sort: 'reviews',
        targetEvent: null,
    };

    const expandedEvents = new Set();
    let allExpanded = false;

    // -----------------------------------------------------------------------
    // DOM Elements
    // -----------------------------------------------------------------------
    const conPillGroup       = document.getElementById('con-pill-group');
    const conSelectDropdown  = document.getElementById('con-select');
    const statsBanner        = document.getElementById('stats-banner');
    const statTotalEvents    = document.getElementById('stat-total-events');
    const statTotalFeedbacks = document.getElementById('stat-total-feedbacks');
    const statTotalComments  = document.getElementById('stat-total-comments');
    const statAvgRating      = document.getElementById('stat-avg-rating');
    const statAvgStars       = document.getElementById('stat-avg-stars');

    const searchInput        = document.getElementById('filter-search');
    const btnClearSearch     = document.getElementById('btn-clear-search');
    const groupFilterTrack   = document.getElementById('group-filter-track');
    const filterTrack        = document.getElementById('filter-track');
    const filterRating       = document.getElementById('filter-rating');
    const groupFilterOcc     = document.getElementById('group-filter-occupancy');
    const filterOcc          = document.getElementById('filter-occupancy');
    const filterComments     = document.getElementById('filter-has-comments');
    const filterSort         = document.getElementById('filter-sort');
    const btnResetFilters    = document.getElementById('btn-reset-filters');
    const activeFilterBadge  = document.getElementById('active-filter-badge');
    const btnToggleAll       = document.getElementById('btn-toggle-all');
    const btnToggleAllIcon   = document.getElementById('btn-toggle-all-icon');
    const btnToggleAllText   = document.getElementById('btn-toggle-all-text');

    const resultsCount       = document.getElementById('results-count');
    const conVersionInfo     = document.getElementById('convention-version-info');
    const loadingState       = document.getElementById('loading-state');
    const eventsList         = document.getElementById('events-list');
    const emptyState         = document.getElementById('empty-state');
    const emptyTitle         = document.getElementById('empty-title');
    const emptyDesc          = document.getElementById('empty-desc');
    const btnEmptyReset      = document.getElementById('btn-empty-reset');

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function starString(rating) {
        if (!rating) return '—';
        const rounded = Math.round(Number(rating));
        const full = Math.max(0, Math.min(5, rounded));
        return '★'.repeat(full) + '☆'.repeat(5 - full);
    }

    function formatDateTime(isoStr) {
        if (!isoStr) return '';
        try {
            const d = new Date(isoStr);
            if (isNaN(d.getTime())) return isoStr;
            return d.toLocaleDateString('en-GB', {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (_) {
            return isoStr;
        }
    }

    // -----------------------------------------------------------------------
    // URL Parameter Synchronization
    // -----------------------------------------------------------------------
    function readUrlParams() {
        const params = new URLSearchParams(window.location.search);
        return {
            con: params.get('con') || '',
            q: params.get('q') || '',
            track: params.get('track') || '',
            rating: params.get('rating') || '',
            occupancy: params.get('occupancy') || '',
            comments: params.get('comments') === '1' || params.get('has_comments') === '1',
            sort: params.get('sort') || 'reviews',
            event: params.get('event') || (window.location.hash ? window.location.hash.substring(1) : ''),
        };
    }

    function updateUrlParams() {
        const url = new URL(window.location.href);
        const params = url.searchParams;

        if (currentConId) params.set('con', currentConId);
        else params.delete('con');

        if (filters.q) params.set('q', filters.q);
        else params.delete('q');

        if (filters.track) params.set('track', filters.track);
        else params.delete('track');

        if (filters.rating) params.set('rating', filters.rating);
        else params.delete('rating');

        if (filters.occupancy) params.set('occupancy', filters.occupancy);
        else params.delete('occupancy');

        if (filters.hasComments) params.set('comments', '1');
        else params.delete('comments');

        if (filters.sort && filters.sort !== 'reviews') params.set('sort', filters.sort);
        else params.delete('sort');

        if (filters.targetEvent) params.set('event', filters.targetEvent);
        else params.delete('event');

        window.history.replaceState(null, '', url.pathname + (params.toString() ? '?' + params.toString() : ''));
    }

    // -----------------------------------------------------------------------
    // Initial Load
    // -----------------------------------------------------------------------
    async function init() {
        const initialParams = readUrlParams();
        filters.q = initialParams.q;
        filters.track = initialParams.track;
        filters.rating = initialParams.rating;
        filters.occupancy = initialParams.occupancy;
        filters.hasComments = initialParams.comments;
        filters.sort = initialParams.sort;
        filters.targetEvent = initialParams.event;

        // Populate controls from URL
        searchInput.value = filters.q;
        btnClearSearch.classList.toggle('hidden', !filters.q);
        filterRating.value = filters.rating;
        filterComments.checked = filters.hasComments;
        filterSort.value = filters.sort;

        try {
            const resp = await apiFetch('/api/conventions');
            conventions = (resp && resp.conventions) || [];
            if (!conventions.length) {
                showError('No conventions found in data directory.');
                return;
            }

            renderConventionSelectors();

            // Pick initial convention
            let selectedId = initialParams.con;
            if (!selectedId || !conventions.some(c => c.id === selectedId)) {
                selectedId = conventions[0].id; // newest convention first
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
            // Pill button
            const pill = el('button', {
                cls: 'con-pill',
                type: 'button',
                title: con.title || con.name,
                onclick: () => selectConvention(con.id),
            }, con.name);
            pill.dataset.conId = con.id;
            conPillGroup.appendChild(pill);

            // Select dropdown option
            const opt = el('option', { value: con.id }, con.title || con.name);
            conSelectDropdown.appendChild(opt);
        });
    }

    async function selectConvention(conId) {
        if (currentConId === conId && currentConData) return;
        const requestSequence = ++conventionRequestSequence;
        currentConId = conId;
        currentConData = null;

        // Update pills & dropdown active state
        document.querySelectorAll('.con-pill').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.conId === conId);
        });
        conSelectDropdown.value = conId;

        // Reset target event unless from initial load
        updateUrlParams();

        // Load data
        loadingState.style.display = 'flex';
        eventsList.style.display = 'none';
        emptyState.classList.add('hidden');
        statsBanner.style.display = 'none';

        try {
            const data = await apiFetch(`/api/convention/${encodeURIComponent(conId)}`);
            if (requestSequence !== conventionRequestSequence || currentConId !== conId) return;
            currentConData = data;
            expandedEvents.clear();
            allExpanded = false;
            updateToggleAllButton();

            // Set up convention-specific filters
            setupConventionFilters(data.convention);

            // Populate stats banner
            renderStatsBanner(data.stats, data.convention);

            // If targetEvent from URL, expand it automatically
            if (filters.targetEvent) {
                expandedEvents.add(filters.targetEvent);
            }

            // Render events
            applyFiltersAndRender();

            // If direct link targeted an event, scroll to it
            if (filters.targetEvent) {
                setTimeout(() => scrollToEvent(filters.targetEvent), 120);
            }
        } catch (err) {
            if (requestSequence !== conventionRequestSequence || currentConId !== conId) return;
            showError('Failed to load convention feedback: ' + err.message);
        } finally {
            if (requestSequence === conventionRequestSequence && currentConId === conId) {
                loadingState.style.display = 'none';
            }
        }
    }

    function setupConventionFilters(convention) {
        // Track Filter
        if (convention.has_events && convention.tracks && convention.tracks.length > 0) {
            groupFilterTrack.style.display = 'flex';
            filterTrack.replaceChildren(el('option', { value: '' }, 'All Tracks'));
            convention.tracks.forEach(tr => {
                const opt = el('option', { value: tr.name }, tr.name);
                filterTrack.appendChild(opt);
            });
            filterTrack.value = filters.track;
        } else {
            groupFilterTrack.style.display = 'none';
            filterTrack.value = '';
            filters.track = '';
        }

        // Occupancy Filter
        if (convention.has_occupancy) {
            groupFilterOcc.style.display = 'flex';
            filterOcc.value = filters.occupancy;
        } else {
            groupFilterOcc.style.display = 'none';
            filterOcc.value = '';
            filters.occupancy = '';
        }

        // Version info note
        if (convention.has_events) {
            conVersionInfo.textContent = '✨ Full event details & track metadata active';
        } else {
            conVersionInfo.textContent = '📁 Legacy convention feedback';
        }
    }

    function renderStatsBanner(stats, convention) {
        statTotalEvents.textContent = (stats.total_events || 0).toLocaleString();
        statTotalFeedbacks.textContent = (stats.total_feedbacks || 0).toLocaleString();
        statTotalComments.textContent = (stats.total_comments || 0).toLocaleString();
        statAvgRating.textContent = stats.avg_rating != null ? stats.avg_rating.toFixed(1) : '—';
        statAvgStars.textContent = stats.avg_rating != null ? starString(stats.avg_rating) : '';
        statsBanner.style.display = 'grid';
    }

    // -----------------------------------------------------------------------
    // Filtering & Sorting
    // -----------------------------------------------------------------------
    function getFilteredEvents() {
        if (!currentConData || !currentConData.events) return [];
        const qLower = (filters.q || '').trim().toLowerCase();

        return currentConData.events.filter(event => {
            // Text search (matches title, event_slug, track, comment text)
            if (qLower) {
                const matchSlug  = event.event_slug.toLowerCase().includes(qLower);
                const matchTitle = (event.title || '').toLowerCase().includes(qLower);
                const matchTrack = event.track && event.track.name.toLowerCase().includes(qLower);
                const matchComments = event.feedbacks.some(fb => fb.message && fb.message.toLowerCase().includes(qLower));

                if (!matchSlug && !matchTitle && !matchTrack && !matchComments) {
                    return false;
                }
            }

            // Track filter
            if (filters.track) {
                if (!event.track || event.track.name !== filters.track) {
                    return false;
                }
            }

            // Rating filter
            if (filters.rating) {
                const avg = event.avg_rating;
                if (filters.rating === '5' && (!avg || avg < 4.8)) return false;
                if (filters.rating === '4+' && (!avg || avg < 3.8)) return false;
                if (filters.rating === '3-' && (!avg || avg > 3.5)) return false;
            }

            // Occupancy filter
            if (filters.occupancy) {
                if (!event.occupancy) return false;
                const lvl = event.occupancy.level != null ? event.occupancy.level : -1;
                if (filters.occupancy === 'high' && lvl < 3) return false;
                if (filters.occupancy === 'medium' && lvl !== 2) return false;
                if (filters.occupancy === 'low' && lvl > 1) return false;
            }

            // Only events with written comments
            if (filters.hasComments) {
                if (!event.comments_count || event.comments_count <= 0) {
                    return false;
                }
            }

            return true;
        }).sort((a, b) => {
            switch (filters.sort) {
                case 'rating_desc':
                    return (b.avg_rating || 0) - (a.avg_rating || 0) || (b.feedback_count - a.feedback_count);
                case 'rating_asc':
                    const rA = a.avg_rating != null ? a.avg_rating : 99;
                    const rB = b.avg_rating != null ? b.avg_rating : 99;
                    return rA - rB || (b.feedback_count - a.feedback_count);
                case 'title':
                    return a.title.localeCompare(b.title, undefined, { sensitivity: 'base' });
                case 'reviews':
                default:
                    return (b.feedback_count - a.feedback_count) || ((b.avg_rating || 0) - (a.avg_rating || 0));
            }
        });
    }

    function applyFiltersAndRender() {
        const filtered = getFilteredEvents();

        // Update active filter badge & reset button
        const isFiltered = Boolean(filters.q || filters.track || filters.rating || filters.occupancy || filters.hasComments || (filters.sort && filters.sort !== 'reviews'));
        btnResetFilters.classList.toggle('hidden', !isFiltered);
        activeFilterBadge.classList.toggle('hidden', !isFiltered);

        if (filtered.length === 0) {
            eventsList.style.display = 'none';
            emptyState.classList.remove('hidden');
            emptyTitle.textContent = isFiltered ? 'No matching events found' : 'No feedback entries';
            emptyDesc.textContent = isFiltered
                ? 'Try adjusting your search query, clearing filters, or switching conventions.'
                : 'No feedback data is currently available for this convention.';
            resultsCount.textContent = '0 events matching filters';
            return;
        }

        emptyState.classList.add('hidden');
        resultsCount.textContent = `Showing ${filtered.length} of ${currentConData.events.length} events`;
        renderEventCards(filtered);
        eventsList.style.display = 'flex';
    }

    // -----------------------------------------------------------------------
    // DOM Card Rendering
    // -----------------------------------------------------------------------
    function renderEventCards(events) {
        eventsList.replaceChildren();

        events.forEach(event => {
            const isOpen = expandedEvents.has(event.event_slug);
            const card = el('article', {
                cls: `event-card ${isOpen ? 'open' : ''}`,
                id: `event-${event.event_slug}`,
            });

            // Accent border left if track color exists
            if (event.track && event.track.color) {
                card.style.borderLeft = `5px solid ${event.track.color}`;
            }

            // Card Header
            const header = el('div', { cls: 'event-card-header' });
            header.addEventListener('click', () => toggleEventAccordion(event.event_slug, card));

            // Left: Title and Badges
            const leftCol = el('div', { cls: 'event-header-left' });

            // Title row
            const titleRow = el('div', { cls: 'event-title-row' },
                el('h2', { cls: 'event-title' }, event.title),
                el('span', { cls: 'event-slug-badge', title: 'Event Code / Slug' }, event.event_slug)
            );

            // Direct link button
            const directLinkBtn = el('button', {
                cls: 'btn-direct-link',
                type: 'button',
                title: 'Copy direct link to this event',
                onclick: (e) => {
                    e.stopPropagation();
                    copyDirectLink(event.event_slug);
                },
            }, '🔗 Copy Link');
            titleRow.appendChild(directLinkBtn);
            leftCol.appendChild(titleRow);

            // Badges row
            const badgesRow = el('div', { cls: 'event-badges-row' });

            // Track badge
            if (event.track) {
                const trBadge = el('span', {
                    cls: 'track-badge',
                    style: {
                        background: `${event.track.color}15`,
                        color: event.track.color,
                        borderColor: `${event.track.color}40`,
                    },
                },
                el('span', { cls: 'track-dot', style: { background: event.track.color } }),
                event.track.name);
                badgesRow.appendChild(trBadge);
            }

            // Occupancy badge (cross-link to Occupancies tab)
            if (event.occupancy) {
                const occ = event.occupancy;
                const lvl = occ.level != null ? occ.level : 0;
                const occUrl = `${window.BASE_PATH || ''}/occupancies?con=${encodeURIComponent(currentConId)}&q=${encodeURIComponent(event.event_slug)}`;
                const occBadge = el('a', {
                    cls: `occ-badge occ-level-${lvl}`,
                    href: occUrl,
                    title: occ.room ? `${occ.room}${occ.start_time ? ' • ' + occ.start_time : ''} — View in Occupancies tab` : 'View in Occupancies tab',
                    onclick: (e) => e.stopPropagation(),
                }, `📊 Occupancy: ${occ.rating || 'Rated'} (${lvl}/5) ↗`);
                badgesRow.appendChild(occBadge);
            }

            // Slot room / schedule info
            if (event.slots && event.slots.length > 0) {
                const slot = event.slots[0];
                if (slot.room_name) {
                    const slotBadge = el('span', { cls: 'slot-info-badge' },
                        `📍 ${slot.room_name}${slot.start ? ' (' + fmtTime(slot.start) + ')' : ''}`
                    );
                    badgesRow.appendChild(slotBadge);
                }
            }

            leftCol.appendChild(badgesRow);
            header.appendChild(leftCol);

            // Right: Rating Score & Chevron
            const rightCol = el('div', { cls: 'event-header-right' });
            const scoreBox = el('div', { cls: 'event-score-box' });

            const scoreMain = el('div', { cls: 'score-main' });
            if (event.avg_rating != null) {
                scoreMain.appendChild(el('span', { cls: 'score-num' }, event.avg_rating.toFixed(1)));
                scoreMain.appendChild(el('span', { cls: 'score-stars' }, starString(event.avg_rating)));
            } else {
                scoreMain.appendChild(el('span', { cls: 'score-num' }, '—'));
            }
            scoreBox.appendChild(scoreMain);

            const countsText = `${event.feedback_count} ${event.feedback_count === 1 ? 'review' : 'reviews'}` +
                (event.comments_count > 0 ? ` (${event.comments_count} text)` : '');
            scoreBox.appendChild(el('span', { cls: 'score-counts' }, countsText));

            rightCol.appendChild(scoreBox);
            rightCol.appendChild(el('span', { cls: 'accordion-chevron', 'aria-hidden': 'true' }, '▼'));
            header.appendChild(rightCol);

            card.appendChild(header);

            // Card Body (Expandable)
            const body = el('div', { cls: 'event-card-body' });

            // Event abstract if available
            if (event.abstract) {
                const absBox = el('div', { cls: 'event-abstract-box' },
                    el('div', { cls: 'event-abstract-title' }, 'Event Description'),
                    el('p', { style: { margin: 0 } }, event.abstract)
                );
                body.appendChild(absBox);
            }

            // Section header
            const sectionHeader = el('div', { cls: 'feedback-section-header' },
                el('span', { cls: 'feedback-section-title' }, `Attendee Reviews (${event.feedbacks.length})`)
            );
            body.appendChild(sectionHeader);

            // Feedbacks list
            const fbList = el('div', { cls: 'feedback-list' });
            event.feedbacks.forEach(fb => {
                const fbCard = el('div', { cls: 'feedback-item' });

                const fbHeader = el('div', { cls: 'feedback-item-header' });
                const starsSpan = el('span', { cls: 'feedback-rating-stars' },
                    fb.rating ? `${starString(fb.rating)} (${fb.rating}/5)` : 'No rating'
                );
                fbHeader.appendChild(starsSpan);

                const metaRight = el('div', { cls: 'feedback-meta-right' });
                if (fb.source_id && fb.source_id !== 'LEGACY') {
                    metaRight.appendChild(el('span', { cls: 'feedback-source-id', title: 'Source / Slot ID' }, fb.source_id));
                }
                if (fb.date) {
                    metaRight.appendChild(el('time', { dateTime: fb.date }, formatDateTime(fb.date)));
                }
                fbHeader.appendChild(metaRight);
                fbCard.appendChild(fbHeader);

                // Message body
                if (fb.message) {
                    fbCard.appendChild(el('div', { cls: 'feedback-message' }, fb.message));
                } else {
                    fbCard.appendChild(el('div', { cls: 'feedback-no-comment' }, 'Rating submitted without written comment'));
                }

                fbList.appendChild(fbCard);
            });

            body.appendChild(fbList);
            card.appendChild(body);
            eventsList.appendChild(card);
        });
    }

    // -----------------------------------------------------------------------
    // Accordion & Direct Link Actions
    // -----------------------------------------------------------------------
    function toggleEventAccordion(slug, cardEl) {
        const card = cardEl || document.getElementById(`event-${slug}`);
        if (!card) return;

        if (expandedEvents.has(slug)) {
            expandedEvents.delete(slug);
            card.classList.remove('open');
        } else {
            expandedEvents.add(slug);
            card.classList.add('open');
        }
    }

    function toggleAllEvents() {
        allExpanded = !allExpanded;
        const cards = document.querySelectorAll('.event-card');

        if (allExpanded) {
            getFilteredEvents().forEach(ev => expandedEvents.add(ev.event_slug));
            cards.forEach(c => c.classList.add('open'));
        } else {
            expandedEvents.clear();
            cards.forEach(c => c.classList.remove('open'));
        }
        updateToggleAllButton();
    }

    function updateToggleAllButton() {
        btnToggleAllIcon.textContent = allExpanded ? '⊟' : '⊞';
        btnToggleAllText.textContent = allExpanded ? 'Collapse All' : 'Expand All';
    }

    function copyDirectLink(slug) {
        filters.targetEvent = slug;
        updateUrlParams();

        const fullUrl = window.location.origin + window.location.pathname +
            `?con=${encodeURIComponent(currentConId)}&event=${encodeURIComponent(slug)}`;

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(fullUrl).then(() => {
                showToast(`Direct link copied for event ${slug}!`, 'info');
            }).catch(() => {
                showToast(`Link: ${fullUrl}`, 'info', 5000);
            });
        } else {
            showToast(`Link: ${fullUrl}`, 'info', 5000);
        }

        // Expand the targeted card
        expandedEvents.add(slug);
        const card = document.getElementById(`event-${slug}`);
        if (card) {
            card.classList.add('open');
            card.classList.add('event-card-highlighted');
            setTimeout(() => card.classList.remove('event-card-highlighted'), 3000);
        }
    }

    function scrollToEvent(slug) {
        const card = document.getElementById(`event-${slug}`);
        if (card) {
            card.classList.add('open');
            card.classList.add('event-card-highlighted');
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => card.classList.remove('event-card-highlighted'), 3000);
        }
    }

    function resetFilters() {
        filters.q = '';
        filters.track = '';
        filters.rating = '';
        filters.occupancy = '';
        filters.hasComments = false;
        filters.sort = 'reviews';
        filters.targetEvent = null;

        searchInput.value = '';
        btnClearSearch.classList.add('hidden');
        filterTrack.value = '';
        filterRating.value = '';
        filterOcc.value = '';
        filterComments.checked = false;
        filterSort.value = 'reviews';

        updateUrlParams();
        applyFiltersAndRender();
    }

    function showError(msg) {
        loadingState.style.display = 'none';
        eventsList.style.display = 'none';
        statsBanner.style.display = 'none';
        emptyState.classList.remove('hidden');
        emptyTitle.textContent = 'Error loading feedback';
        emptyDesc.textContent = msg;
    }

    // -----------------------------------------------------------------------
    // Event Listeners
    // -----------------------------------------------------------------------
    function bindEvents() {
        // Convention Select Dropdown (mobile fallback)
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

        // Track Filter
        filterTrack.addEventListener('change', (e) => {
            filters.track = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        // Rating Filter
        filterRating.addEventListener('change', (e) => {
            filters.rating = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        // Occupancy Filter
        filterOcc.addEventListener('change', (e) => {
            filters.occupancy = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        // Comments only checkbox
        filterComments.addEventListener('change', (e) => {
            filters.hasComments = e.target.checked;
            updateUrlParams();
            applyFiltersAndRender();
        });

        // Sort Select
        filterSort.addEventListener('change', (e) => {
            filters.sort = e.target.value;
            updateUrlParams();
            applyFiltersAndRender();
        });

        // Reset Filter Buttons
        btnResetFilters.addEventListener('click', resetFilters);
        btnEmptyReset.addEventListener('click', resetFilters);

        // Toggle All Button
        btnToggleAll.addEventListener('click', toggleAllEvents);

        // Handle browser Back / Forward buttons
        window.addEventListener('popstate', () => {
            const p = readUrlParams();
            filters.q = p.q;
            filters.track = p.track;
            filters.rating = p.rating;
            filters.occupancy = p.occupancy;
            filters.hasComments = p.comments;
            filters.sort = p.sort;
            filters.targetEvent = p.event;

            searchInput.value = filters.q;
            btnClearSearch.classList.toggle('hidden', !filters.q);
            filterTrack.value = filters.track;
            filterRating.value = filters.rating;
            filterOcc.value = filters.occupancy;
            filterComments.checked = filters.hasComments;
            filterSort.value = filters.sort;

            if (p.con && p.con !== currentConId) {
                selectConvention(p.con);
            } else {
                applyFiltersAndRender();
                if (p.event) scrollToEvent(p.event);
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
