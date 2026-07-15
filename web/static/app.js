/**
 * Pretalx Schedule Preview — Frontend Application
 *
 * Fetches schedule data from the backend API and renders it in two view modes:
 * - Calendar: grouped by day and start time, masonry card grid
 * - Rooms: one column per room, sorted by time
 *
 * All DOM manipulation uses safe methods (createElement, textContent) — no innerHTML.
 */

(function () {
    "use strict";

    // --- Configuration ---
    const pathname = window.location.pathname;
    const BASE_PATH = pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;

    // --- State ---
    let scheduleData = null;
    let currentView = "calendar"; // "calendar" | "rooms"
    let currentDayIndex = 0;
    let filters = {
        search: "",
        tracks: new Set(),
        tags: new Set(),
        speakers: new Set(),
        rooms: new Set(),
    };

    // --- DOM references ---
    const $ = (id) => document.getElementById(id);
    const loadingOverlay = $("loading-overlay");
    const errorOverlay = $("error-overlay");
    const errorMessage = $("error-message");
    const mainContent = $("main-content");
    const viewCalendar = $("view-calendar");
    const viewRooms = $("view-rooms");
    const noResults = $("no-results");
    const dayTabsContainer = $("day-tabs");
    const eventTitle = $("event-title");
    const filterSearch = $("filter-search");
    const btnCalendar = $("btn-calendar");
    const btnRooms = $("btn-rooms");
    const btnRefresh = $("btn-refresh");
    const btnRetry = $("btn-retry");
    const btnClearFilters = $("btn-clear-filters");
    const detailModal = $("detail-modal");
    const modalClose = $("modal-close");
    const modalCopyLink = $("modal-copy-link");

    // --- Utility: generate a consistent color from a string ---
    function stringToHSL(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        const h = Math.abs(hash % 360);
        return "hsl(" + h + ", 55%, 45%)";
    }

    // --- Utility: create an SVG icon via DOMParser ---
    function createSVGIcon(svgString) {
        const doc = new DOMParser().parseFromString(svgString, "image/svg+xml");
        const svg = doc.documentElement;
        if (svg instanceof SVGElement) {
            return svg;
        }
        // Fallback: return empty span
        return document.createElement("span");
    }

    // --- Data Fetching ---
    async function fetchScheduleData() {
        try {
            const response = await fetch(BASE_PATH + "/api/schedule");
            if (!response.ok) {
                const err = await response.json().catch(function () {
                    return { error: "HTTP " + response.status };
                });
                throw new Error(err.error || "Failed to load data");
            }
            return await response.json();
        } catch (e) {
            throw e;
        }
    }

    async function loadData() {
        showLoading();
        try {
            scheduleData = await fetchScheduleData();
            eventTitle.textContent =
                (scheduleData.event ? scheduleData.event.name : "Schedule") +
                " — Schedule Preview";
            document.title = eventTitle.textContent;
            // Show refresh button only in wip mode
            if (scheduleData.schedule_version === "wip") {
                btnRefresh.classList.remove("hidden");
            } else {
                btnRefresh.classList.add("hidden");
            }
            buildDayTabs();
            buildFilterDropdowns();
            render();
            showMain();
        } catch (e) {
            showError(e.message || "Failed to load schedule data.");
        }
    }

    // --- Visibility helpers ---
    function showLoading() {
        loadingOverlay.classList.remove("hidden");
        errorOverlay.classList.add("hidden");
        mainContent.classList.add("hidden");
    }
    function showError(msg) {
        loadingOverlay.classList.add("hidden");
        errorOverlay.classList.remove("hidden");
        mainContent.classList.add("hidden");
        errorMessage.textContent = msg;
    }
    function showMain() {
        loadingOverlay.classList.add("hidden");
        errorOverlay.classList.add("hidden");
        mainContent.classList.remove("hidden");
    }

    // --- Day Tabs ---
    // currentDayIndex === -1 is the sentinel for the "All Days" tab.
    function buildDayTabs() {
        dayTabsContainer.replaceChildren();
        if (!scheduleData || !scheduleData.days) return;

        // "All Days" tab (index -1) — only added when there is more than one real day
        var realDays = scheduleData.days.filter(function (d) { return d.date !== "unscheduled"; });
        if (realDays.length > 1) {
            var allBtn = document.createElement("button");
            allBtn.className = "day-tab" + (currentDayIndex === -1 ? " active" : "");
            allBtn.textContent = "All Days";
            allBtn.setAttribute("data-day-index", "-1");
            allBtn.addEventListener("click", function () {
                currentDayIndex = -1;
                updateActiveDayTab();
                pushURLState();
                render();
            });
            dayTabsContainer.appendChild(allBtn);
        }

        scheduleData.days.forEach(function (day, idx) {
            var btn = document.createElement("button");
            btn.className = "day-tab" + (idx === currentDayIndex ? " active" : "");
            btn.textContent = day.label;
            btn.setAttribute("data-day-index", String(idx));
            btn.addEventListener("click", function () {
                currentDayIndex = idx;
                updateActiveDayTab();
                pushURLState();
                render();
            });
            dayTabsContainer.appendChild(btn);
        });
    }

    function updateActiveDayTab() {
        var tabs = dayTabsContainer.querySelectorAll(".day-tab");
        tabs.forEach(function (tab) {
            var tabIdx = parseInt(tab.getAttribute("data-day-index"), 10);
            if (tabIdx === currentDayIndex) {
                tab.classList.add("active");
            } else {
                tab.classList.remove("active");
            }
        });
    }

    // --- Filter Dropdowns ---
    function buildFilterDropdowns() {
        buildDropdown(
            "dropdown-tracks",
            "btn-filter-tracks",
            scheduleData.tracks || [],
            "name",
            "tracks",
            true
        );
        buildDropdown(
            "dropdown-tags",
            "btn-filter-tags",
            scheduleData.tags || [],
            "tag",
            "tags",
            false
        );
        buildDropdown(
            "dropdown-speakers",
            "btn-filter-speakers",
            scheduleData.speakers || [],
            "name",
            "speakers",
            false,
            true
        );
        buildDropdown(
            "dropdown-rooms",
            "btn-filter-rooms",
            scheduleData.rooms || [],
            "name",
            "rooms",
            false
        );
    }

    function buildDropdown(
        panelId,
        btnId,
        items,
        labelKey,
        filterKey,
        showColor,
        hasSearch
    ) {
        var panel = $(panelId);
        var btn = $(btnId);
        panel.replaceChildren();

        if (hasSearch && items.length > 8) {
            var searchDiv = document.createElement("div");
            searchDiv.className = "dropdown-search";
            var searchInput = document.createElement("input");
            searchInput.type = "text";
            searchInput.placeholder = "Filter...";
            searchInput.setAttribute("aria-label", "Filter " + filterKey);
            searchInput.addEventListener("input", function () {
                var q = searchInput.value.toLowerCase();
                var dropdownItems = panel.querySelectorAll(".dropdown-item");
                dropdownItems.forEach(function (item) {
                    var label = item.getAttribute("data-label") || "";
                    if (label.toLowerCase().indexOf(q) >= 0) {
                        item.style.display = "";
                    } else {
                        item.style.display = "none";
                    }
                });
            });
            searchDiv.appendChild(searchInput);
            panel.appendChild(searchDiv);
        }

        items.forEach(function (item) {
            var label = item[labelKey] || "";
            var id = item.id || item.code || label;
            var row = document.createElement("div");
            row.className = "dropdown-item";
            row.setAttribute("data-id", String(id));
            row.setAttribute("data-label", label);
            row.setAttribute("role", "menuitemcheckbox");
            row.setAttribute("aria-checked", "false");

            var checkbox = document.createElement("span");
            checkbox.className = "checkbox";
            row.appendChild(checkbox);

            if (showColor && item.color) {
                var dot = document.createElement("span");
                dot.className = "color-dot";
                dot.style.backgroundColor = item.color;
                row.appendChild(dot);
            }

            var labelEl = document.createElement("span");
            labelEl.className = "item-label";
            labelEl.textContent = label;
            row.appendChild(labelEl);

            row.addEventListener("click", function () {
                var selected = filters[filterKey].has(String(id));
                if (selected) {
                    filters[filterKey].delete(String(id));
                    row.classList.remove("selected");
                    row.setAttribute("aria-checked", "false");
                } else {
                    filters[filterKey].add(String(id));
                    row.classList.add("selected");
                    row.setAttribute("aria-checked", "true");
                }
                updateFilterButtonState(btn, filters[filterKey]);
                updateClearButton();
                pushURLState();
                render();
            });

            panel.appendChild(row);
        });

        // Toggle dropdown on button click.
        // Clone the button to strip any previously registered listeners
        // (buildDropdown is re-called on every loadData, e.g. refresh/retry).
        var newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        btn = newBtn;

        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            var isOpen = panel.classList.contains("open");
            closeAllDropdowns();
            if (!isOpen) {
                panel.classList.add("open");
                btn.setAttribute("aria-expanded", "true");
            }
        });
    }

    function updateFilterButtonState(btn, filterSet) {
        if (filterSet.size > 0) {
            btn.classList.add("has-selection");
        } else {
            btn.classList.remove("has-selection");
        }
    }

    function updateClearButton() {
        var hasFilters =
            filters.search ||
            filters.tracks.size > 0 ||
            filters.tags.size > 0 ||
            filters.speakers.size > 0 ||
            filters.rooms.size > 0;
        if (hasFilters) {
            btnClearFilters.classList.remove("hidden");
        } else {
            btnClearFilters.classList.add("hidden");
        }
    }

    function closeAllDropdowns() {
        document.querySelectorAll(".dropdown-panel").forEach(function (p) {
            p.classList.remove("open");
        });
        document.querySelectorAll(".filter-btn").forEach(function (b) {
            b.setAttribute("aria-expanded", "false");
        });
    }

    // Close dropdowns when clicking outside — but NOT when clicking inside a panel
    document.addEventListener("click", function (e) {
        if (!e.target.closest(".filter-dropdown")) {
            closeAllDropdowns();
        }
    });

    // --- Filtering Logic ---
    function matchesFilters(slot) {
        // Search filter
        if (filters.search) {
            var q = filters.search.toLowerCase();
            var title = (slot.title || "").toLowerCase();
            var speakerNames = (slot.speakers || [])
                .map(function (s) {
                    return (s.name || "").toLowerCase();
                })
                .join(" ");
            if (title.indexOf(q) < 0 && speakerNames.indexOf(q) < 0) {
                return false;
            }
        }

        // Track filter
        if (filters.tracks.size > 0) {
            var trackId = slot.track ? String(slot.track.id) : "";
            if (!filters.tracks.has(trackId)) return false;
        }

        // Tag filter (AND — slot must have ALL selected tags)
        if (filters.tags.size > 0) {
            var slotTagIds = (slot.tags || []).map(function (t) {
                return String(t.id);
            });
            var allTagsMatch = true;
            filters.tags.forEach(function (tagId) {
                if (slotTagIds.indexOf(tagId) < 0) allTagsMatch = false;
            });
            if (!allTagsMatch) return false;
        }

        // Speaker filter
        if (filters.speakers.size > 0) {
            var slotSpeakerIds = (slot.speakers || []).map(function (s) {
                return String(s.code);
            });
            var hasMatchingSpeaker = false;
            filters.speakers.forEach(function (speakerId) {
                if (slotSpeakerIds.indexOf(speakerId) >= 0)
                    hasMatchingSpeaker = true;
            });
            if (!hasMatchingSpeaker) return false;
        }

        // Room filter
        if (filters.rooms.size > 0) {
            var roomId = slot.room ? String(slot.room.id) : "";
            if (!filters.rooms.has(roomId)) return false;
        }

        return true;
    }

    // --- Rendering ---

    /**
     * Check if any text-based search filter is active (search, tracks, tags, speakers).
     * When search text is active, we search across ALL days.
     */
    function isSearchActive() {
        return filters.search.length > 0;
    }

    function render() {
        if (!scheduleData) return;

        if (currentView === "calendar") {
            renderCalendarView();
            viewCalendar.classList.remove("hidden");
            viewRooms.classList.add("hidden");
        } else {
            renderRoomsView();
            viewRooms.classList.remove("hidden");
            viewCalendar.classList.add("hidden");
        }
    }

    function renderCalendarView() {
        viewCalendar.replaceChildren();
        if (!scheduleData.days) return;

        // When search is active, search across ALL days
        if (isSearchActive()) {
            renderCrossDayCalendar();
        } else {
            renderSingleDayCalendar();
        }
    }

    /**
     * Render calendar for a single day, or all days when currentDayIndex === -1.
     */
    function renderSingleDayCalendar() {
        if (currentDayIndex === -1) {
            renderAllDaysCalendar();
            return;
        }
        if (!scheduleData.days[currentDayIndex]) return;

        var day = scheduleData.days[currentDayIndex];
        var filteredSlots = day.slots.filter(matchesFilters);

        if (filteredSlots.length === 0) {
            noResults.classList.remove("hidden");
            return;
        }
        noResults.classList.add("hidden");

        renderTimeGroups(filteredSlots, viewCalendar);
    }

    /**
     * Render all real (non-unscheduled) days with day-section headers.
     * Used by the "All Days" tab.
     */
    function renderAllDaysCalendar() {
        var totalResults = 0;

        scheduleData.days.forEach(function (day) {
            if (day.date === "unscheduled") return; // skip unscheduled
            var filteredSlots = day.slots.filter(matchesFilters);
            if (filteredSlots.length === 0) return;
            totalResults += filteredSlots.length;

            var daySection = document.createElement("div");
            daySection.className = "cross-day-section";

            var dayHeader = document.createElement("div");
            dayHeader.className = "cross-day-header";

            var dayLabel = document.createElement("span");
            dayLabel.className = "cross-day-label";
            dayLabel.textContent = day.label;
            dayHeader.appendChild(dayLabel);

            var dayLine = document.createElement("div");
            dayLine.className = "cross-day-line";
            dayHeader.appendChild(dayLine);

            daySection.appendChild(dayHeader);
            renderTimeGroups(filteredSlots, daySection);
            viewCalendar.appendChild(daySection);
        });

        if (totalResults === 0) {
            noResults.classList.remove("hidden");
        } else {
            noResults.classList.add("hidden");
        }
    }

    /**
     * Render search results across ALL days, with day section headers.
     */
    function renderCrossDayCalendar() {
        var totalResults = 0;

        scheduleData.days.forEach(function (day, dayIdx) {
            var filteredSlots = day.slots.filter(matchesFilters);
            if (filteredSlots.length === 0) return;
            totalResults += filteredSlots.length;

            // Day section header
            var daySection = document.createElement("div");
            daySection.className = "cross-day-section";

            var dayHeader = document.createElement("div");
            dayHeader.className = "cross-day-header";

            var dayLabel = document.createElement("span");
            dayLabel.className = "cross-day-label";
            dayLabel.textContent = day.label;
            dayHeader.appendChild(dayLabel);

            var countBadge = document.createElement("span");
            countBadge.className = "cross-day-count";
            countBadge.textContent = filteredSlots.length + " result" + (filteredSlots.length !== 1 ? "s" : "");
            dayHeader.appendChild(countBadge);

            var dayLine = document.createElement("div");
            dayLine.className = "cross-day-line";
            dayHeader.appendChild(dayLine);

            daySection.appendChild(dayHeader);

            // Render time groups within this day
            renderTimeGroups(filteredSlots, daySection);

            viewCalendar.appendChild(daySection);
        });

        if (totalResults === 0) {
            noResults.classList.remove("hidden");
        } else {
            noResults.classList.add("hidden");
        }
    }

    /**
     * Render slots grouped by start time into a container.
     */
    function renderTimeGroups(slots, container) {
        var timeGroups = {};
        var timeOrder = [];

        slots.forEach(function (slot) {
            var startTime = slot.start
                ? slot.start.substring(11, 16)
                : "unscheduled";
            if (!timeGroups[startTime]) {
                timeGroups[startTime] = [];
                timeOrder.push(startTime);
            }
            timeGroups[startTime].push(slot);
        });

        timeOrder.sort();

        timeOrder.forEach(function (time) {
            var group = document.createElement("div");
            group.className = "time-group";

            // Header with time badge
            var header = document.createElement("div");
            header.className = "time-group-header";

            var badge = document.createElement("span");
            badge.className = "time-badge";
            badge.textContent = time === "unscheduled" ? "TBD" : time;
            header.appendChild(badge);

            var line = document.createElement("div");
            line.className = "time-group-line";
            header.appendChild(line);

            group.appendChild(header);

            // Grid of cards
            var grid = document.createElement("div");
            grid.className = "time-group-grid";

            timeGroups[time].forEach(function (slot) {
                grid.appendChild(createEventCard(slot));
            });

            group.appendChild(grid);
            container.appendChild(group);
        });
    }

    function renderRoomsView() {
        viewRooms.replaceChildren();
        if (!scheduleData.days || !scheduleData.rooms) return;

        var filteredSlots;
        if (currentDayIndex === -1) {
            // All Days mode: merge all non-unscheduled days
            filteredSlots = [];
            scheduleData.days.forEach(function (day) {
                if (day.date !== "unscheduled") {
                    filteredSlots = filteredSlots.concat(day.slots.filter(matchesFilters));
                }
            });
        } else {
            if (!scheduleData.days[currentDayIndex]) return;
            var day = scheduleData.days[currentDayIndex];
            filteredSlots = day.slots.filter(matchesFilters);
        }

        if (filteredSlots.length === 0) {
            noResults.classList.remove("hidden");
            return;
        }
        noResults.classList.add("hidden");

        // Group by room
        var roomSlots = {};
        filteredSlots.forEach(function (slot) {
            var roomId = slot.room ? String(slot.room.id) : "none";
            if (!roomSlots[roomId]) {
                roomSlots[roomId] = [];
            }
            roomSlots[roomId].push(slot);
        });

        // When room filter is active, only show the selected rooms as columns
        var visibleRooms = scheduleData.rooms.filter(function (room) {
            if (filters.rooms.size === 0) return true;
            return filters.rooms.has(String(room.id));
        });

        // Create a scroll wrapper with indicators
        var scrollWrapper = document.createElement("div");
        scrollWrapper.className = "rooms-scroll-wrapper";

        // Determine column count
        var roomCount = visibleRooms.length;
        var grid = document.createElement("div");
        grid.className = "rooms-grid";
        grid.style.gridTemplateColumns =
            "repeat(" + Math.max(roomCount, 1) + ", minmax(300px, 1fr))";

        visibleRooms.forEach(function (room) {
            var roomId = String(room.id);
            var slots = roomSlots[roomId] || [];

            var column = document.createElement("div");
            column.className = "room-column";

            var colHeader = document.createElement("div");
            colHeader.className = "room-column-header";
            var colTitle = document.createElement("h3");
            colTitle.textContent = room.name;
            colHeader.appendChild(colTitle);
            column.appendChild(colHeader);

            var slotsContainer = document.createElement("div");
            slotsContainer.className = "room-slots";

            slots.forEach(function (slot) {
                slotsContainer.appendChild(createEventCard(slot, true));
            });

            column.appendChild(slotsContainer);
            grid.appendChild(column);
        });

        // Left scroll indicator
        var leftIndicator = document.createElement("div");
        leftIndicator.className = "scroll-indicator scroll-indicator-left";
        leftIndicator.setAttribute("aria-hidden", "true");
        var leftArrow = createSVGIcon(
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>'
        );
        leftIndicator.appendChild(leftArrow);
        leftIndicator.addEventListener("click", function () {
            grid.scrollBy({ left: -320, behavior: "smooth" });
        });

        // Right scroll indicator
        var rightIndicator = document.createElement("div");
        rightIndicator.className = "scroll-indicator scroll-indicator-right";
        rightIndicator.setAttribute("aria-hidden", "true");
        var rightArrow = createSVGIcon(
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>'
        );
        rightIndicator.appendChild(rightArrow);
        rightIndicator.addEventListener("click", function () {
            grid.scrollBy({ left: 320, behavior: "smooth" });
        });

        // Scroll hint text for first-time users
        var scrollHint = document.createElement("div");
        scrollHint.className = "scroll-hint";
        var hintIcon = createSVGIcon(
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 12 1 12"></polyline><polyline points="23 12 19 12"></polyline><polyline points="7 8 5 12 7 16"></polyline><polyline points="17 8 19 12 17 16"></polyline><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
        );
        scrollHint.appendChild(hintIcon);
        var hintText = document.createElement("span");
        hintText.textContent = "Scroll horizontally to see all rooms";
        scrollHint.appendChild(hintText);

        scrollWrapper.appendChild(leftIndicator);
        scrollWrapper.appendChild(grid);
        scrollWrapper.appendChild(rightIndicator);

        viewRooms.appendChild(scrollHint);
        viewRooms.appendChild(scrollWrapper);

        // Update scroll indicator visibility
        function updateScrollIndicators() {
            var scrollLeft = grid.scrollLeft;
            var maxScroll = grid.scrollWidth - grid.clientWidth;

            if (maxScroll <= 5) {
                // No scrolling needed — hide everything
                leftIndicator.classList.remove("visible");
                rightIndicator.classList.remove("visible");
                scrollHint.classList.add("hidden");
                scrollWrapper.classList.remove("has-scroll");
            } else {
                scrollWrapper.classList.add("has-scroll");
                // Show/hide scroll hint (only hide after first scroll)
                if (scrollLeft > 10) {
                    scrollHint.classList.add("hidden");
                }
                leftIndicator.classList.toggle("visible", scrollLeft > 10);
                rightIndicator.classList.toggle("visible", scrollLeft < maxScroll - 10);
            }
        }

        grid.addEventListener("scroll", updateScrollIndicators, { passive: true });
        // Initial check after layout
        requestAnimationFrame(function () {
            updateScrollIndicators();
        });
        // Also check on resize
        window.addEventListener("resize", updateScrollIndicators);
    }

    // --- Event Card Creation ---
    function createEventCard(slot, showTime) {
        var card = document.createElement("div");
        card.className = "event-card";
        if (slot.is_blocker) {
            card.classList.add("is-blocker");
        }

        // Set track color as CSS variable
        var trackColor =
            slot.track && slot.track.color ? slot.track.color : "#64748b";
        card.style.setProperty("--card-track-color", trackColor);

        // Badges row
        var badges = document.createElement("div");
        badges.className = "card-badges";

        // Room badge
        if (slot.room && slot.room.name) {
            var roomBadge = document.createElement("span");
            roomBadge.className = "card-badge badge-room";
            roomBadge.textContent = slot.room.name;
            badges.appendChild(roomBadge);
        }

        // Duration badge
        if (slot.duration) {
            var durBadge = document.createElement("span");
            durBadge.className = "card-badge badge-duration";
            durBadge.textContent = slot.duration + " min";
            badges.appendChild(durBadge);
        }

        // Type badge
        if (slot.submission_type && slot.submission_type !== "Blocker") {
            var typeBadge = document.createElement("span");
            typeBadge.className = "card-badge badge-type";
            typeBadge.textContent = slot.submission_type;
            //badges.appendChild(typeBadge); // Currently not properly used in pretalx - WIP for next year's event
        }

        // Track badge
        if (slot.track && slot.track.name) {
            var trackBadge = document.createElement("span");
            trackBadge.className = "card-badge badge-track";
            trackBadge.style.backgroundColor = hexToRGBA(trackColor, 0.25);
            trackBadge.style.color = lightenColor(trackColor);
            trackBadge.textContent = slot.track.name;
            badges.appendChild(trackBadge);
        }

        card.appendChild(badges);

        // Title
        var title = document.createElement("div");
        title.className = "card-title";
        title.textContent = slot.title || "Untitled";
        card.appendChild(title);

        // First speaker
        if (slot.speakers && slot.speakers.length > 0) {
            var speakerDiv = document.createElement("div");
            speakerDiv.className = "card-speaker";

            var dot = document.createElement("span");
            dot.className = "speaker-dot";
            dot.style.backgroundColor = stringToHSL(
                slot.speakers[0].name || ""
            );
            speakerDiv.appendChild(dot);

            var nameSpan = document.createElement("span");
            nameSpan.textContent = slot.speakers[0].name || "Unknown";
            if (slot.speakers.length > 1) {
                nameSpan.textContent += " + " + (slot.speakers.length - 1) + " more";
            }
            speakerDiv.appendChild(nameSpan);

            card.appendChild(speakerDiv);
        }

        // Time (shown in room view)
        if (showTime && slot.start && slot.end) {
            var timeDiv = document.createElement("div");
            timeDiv.className = "card-time";
            timeDiv.textContent =
                slot.start.substring(11, 16) +
                " – " +
                slot.end.substring(11, 16);
            card.appendChild(timeDiv);
        }

        // Click to open detail
        card.addEventListener("click", function () {
            openDetailModal(slot);
        });

        return card;
    }

    // --- Detail Modal ---
    function openDetailModal(slot) {
        var trackColor =
            slot.track && slot.track.color ? slot.track.color : "#64748b";

        // Track bar
        $("modal-track-bar").style.backgroundColor = trackColor;

        // Submission image (hero banner)
        var modalImageEl = $("modal-image");
        if (slot.image) {
            modalImageEl.src = proxyImageUrl(slot.image);
            modalImageEl.alt = slot.title || "Event image";
            modalImageEl.classList.remove("hidden");
            modalImageEl.addEventListener("error", function () {
                modalImageEl.classList.add("hidden");
            }, { once: true });
        } else {
            modalImageEl.classList.add("hidden");
            modalImageEl.src = "";
        }

        // Badges
        var badgesContainer = $("modal-badges");
        badgesContainer.replaceChildren();

        var makeBadge = function (text, bgColor, textColor) {
            var badge = document.createElement("span");
            badge.className = "modal-badge";
            badge.style.backgroundColor = bgColor;
            badge.style.color = textColor;
            badge.textContent = text;
            return badge;
        };

        if (slot.room && slot.room.name) {
            badgesContainer.appendChild(
                makeBadge(
                    slot.room.name,
                    "rgba(59, 130, 246, 0.15)",
                    "#60a5fa"
                )
            );
        }
        if (slot.duration) {
            badgesContainer.appendChild(
                makeBadge(
                    slot.duration + " min",
                    "rgba(255,255,255,0.06)",
                    "#94a3b8"
                )
            );
        }
        // Commented out for now as sumission_type is not properly used in pretalx - WIP for next year
        /* if (slot.submission_type) {
            badgesContainer.appendChild(
                makeBadge(
                    slot.submission_type,
                    "rgba(249, 115, 22, 0.12)",
                    "#fb923c"
                )
            );
        } */
        if (slot.track && slot.track.name) {
            badgesContainer.appendChild(
                makeBadge(
                    slot.track.name,
                    hexToRGBA(trackColor, 0.2),
                    lightenColor(trackColor)
                )
            );
        }
        if (slot.is_blocker) {
            badgesContainer.appendChild(
                makeBadge("BLOCKER", "rgba(239,68,68,0.15)", "#f87171")
            );
        }

        // Title
        $("modal-title").textContent = slot.title || "Untitled";

        // Speakers
        var speakersContainer = $("modal-speakers");
        speakersContainer.replaceChildren();
        if (slot.speakers && slot.speakers.length > 0) {
            slot.speakers.forEach(function (speaker) {
                var card = document.createElement("div");
                card.className = "modal-speaker-card";

                // Avatar
                if (speaker.avatar) {
                    var img = document.createElement("img");
                    img.className = "speaker-avatar";
                    img.src = proxyImageUrl(speaker.avatar);
                    img.alt = speaker.name || "Speaker";
                    img.loading = "lazy";
                    img.addEventListener("error", function () {
                        // Replace broken image with placeholder
                        var placeholder = createAvatarPlaceholder(
                            speaker.name || ""
                        );
                        card.replaceChild(placeholder, img);
                    });
                    card.appendChild(img);
                } else {
                    card.appendChild(
                        createAvatarPlaceholder(speaker.name || "")
                    );
                }

                // Info
                var info = document.createElement("div");
                info.className = "speaker-info";
                var name = document.createElement("div");
                name.className = "speaker-name";
                name.textContent = speaker.name || "Unknown";
                info.appendChild(name);

                if (speaker.code) {
                    var code = document.createElement("div");
                    code.className = "speaker-code";
                    code.textContent = speaker.code;
                    info.appendChild(code);
                }
                card.appendChild(info);

                speakersContainer.appendChild(card);
            });
        }

        // Meta info (time, date)
        var metaContainer = $("modal-meta");
        metaContainer.replaceChildren();

        if (slot.start && slot.end) {
            var timeIcon =
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>';
            var timeMeta = document.createElement("div");
            timeMeta.className = "meta-item";
            timeMeta.appendChild(createSVGIcon(timeIcon));
            var timeText = document.createElement("span");
            timeText.textContent =
                slot.start.substring(11, 16) +
                " – " +
                slot.end.substring(11, 16);
            timeMeta.appendChild(timeText);
            metaContainer.appendChild(timeMeta);
        }

        if (slot.start) {
            var dateIcon =
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>';
            var dateMeta = document.createElement("div");
            dateMeta.className = "meta-item";
            dateMeta.appendChild(createSVGIcon(dateIcon));
            var dateText = document.createElement("span");
            dateText.textContent = slot.start.substring(0, 10);
            dateMeta.appendChild(dateText);
            metaContainer.appendChild(dateMeta);
        }

        // Tags
        if (slot.tags && slot.tags.length > 0) {
            slot.tags.forEach(function (tag) {
                var tagMeta = document.createElement("div");
                tagMeta.className = "meta-item";
                var tagText = document.createElement("span");
                tagText.textContent = "#" + (tag.tag || "");
                tagMeta.appendChild(tagText);
                metaContainer.appendChild(tagMeta);
            });
        }

        // Abstract
        var abstractSection = $("modal-abstract-section");
        var abstractEl = $("modal-abstract");
        if (slot.abstract && slot.abstract.trim()) {
            abstractSection.classList.remove("hidden");
            abstractEl.classList.add("markdown-content");
            // abstract is pre-rendered HTML from the backend markdown converter
            abstractEl.innerHTML = slot.abstract;
        } else {
            abstractSection.classList.add("hidden");
            abstractEl.innerHTML = "";
        }

        // Description
        var descSection = $("modal-description-section");
        var descEl = $("modal-description");
        if (slot.description && slot.description.trim()) {
            descSection.classList.remove("hidden");
            descEl.classList.add("markdown-content");
            // description is pre-rendered HTML from the backend markdown converter
            descEl.innerHTML = slot.description;
        } else {
            descSection.classList.add("hidden");
            descEl.innerHTML = "";
        }

        // Update URL to include event deep-link
        pushURLState(slot.stable_id);

        // Show modal
        detailModal.classList.remove("hidden");
        document.body.style.overflow = "hidden";
    }

    function closeDetailModal() {
        detailModal.classList.add("hidden");
        document.body.style.overflow = "";
        // Restore URL without event param
        pushURLState(null);
        // Reset copy-link button text if it was changed
        if (modalCopyLink) {
            modalCopyLink.textContent = "Copy link";
        }
    }

    function createAvatarPlaceholder(name) {
        var placeholder = document.createElement("div");
        placeholder.className = "speaker-avatar-placeholder";
        placeholder.style.backgroundColor = stringToHSL(name);
        var initial =
            name && name.length > 0 ? name.charAt(0).toUpperCase() : "?";
        placeholder.textContent = initial;
        return placeholder;
    }

    // --- Helpers ---

    /**
     * Proxy an image URL through the backend to add authentication.
     * This is necessary because Pretalx avatar URLs may require API token auth.
     */
    function proxyImageUrl(url) {
        if (!url) return "";
        return BASE_PATH + "/api/image-proxy?url=" + encodeURIComponent(url);
    }

    /**
     * Strip HTML tags from a string, returning plain text.
     * Uses DOMParser for safe HTML stripping (no innerHTML assignment).
     */
    function stripHTML(html) {
        if (!html) return "";
        var doc = new DOMParser().parseFromString(html, "text/html");
        return doc.body.textContent || "";
    }

    function hexToRGBA(hex, alpha) {
        if (!hex || hex.charAt(0) !== "#") return "rgba(100,100,100," + alpha + ")";
        var r = parseInt(hex.substring(1, 3), 16);
        var g = parseInt(hex.substring(3, 5), 16);
        var b = parseInt(hex.substring(5, 7), 16);
        if (isNaN(r) || isNaN(g) || isNaN(b))
            return "rgba(100,100,100," + alpha + ")";
        return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
    }

    function lightenColor(hex) {
        if (!hex || hex.charAt(0) !== "#") return "#94a3b8";
        var r = Math.min(255, parseInt(hex.substring(1, 3), 16) + 60);
        var g = Math.min(255, parseInt(hex.substring(3, 5), 16) + 60);
        var b = Math.min(255, parseInt(hex.substring(5, 7), 16) + 60);
        if (isNaN(r) || isNaN(g) || isNaN(b)) return "#94a3b8";
        return (
            "#" +
            r.toString(16).padStart(2, "0") +
            g.toString(16).padStart(2, "0") +
            b.toString(16).padStart(2, "0")
        );
    }

    // --- URL State Sync ---

    /**
     * Push the current view + day + filter state into the URL as query params.
     * Optionally include an open event ID (for deep-linking to a modal).
     * Uses history.replaceState so navigation still works cleanly.
     */
    function pushURLState(openEventId) {
        var params = new URLSearchParams();

        if (currentView !== "calendar") params.set("view", currentView);
        // -1 = "All Days" tab; 0 is the default so omit it from the URL
        if (currentDayIndex !== 0) params.set("day", String(currentDayIndex));
        if (filters.search) params.set("search", filters.search);
        if (filters.tracks.size > 0)
            params.set("tracks", Array.from(filters.tracks).join(","));
        if (filters.tags.size > 0)
            params.set("tags", Array.from(filters.tags).join(","));
        if (filters.speakers.size > 0)
            params.set("speakers", Array.from(filters.speakers).join(","));
        if (filters.rooms.size > 0)
            params.set("rooms", Array.from(filters.rooms).join(","));
        if (openEventId != null)
            params.set("event", openEventId);

        var paramStr = params.toString();
        var newUrl = window.location.pathname + (paramStr ? "?" + paramStr : "");
        window.history.replaceState(null, "", newUrl);
    }

    /**
     * Read URL query params and apply them to the current state.
     * Called once on page load, before data is fetched.
     * Returns the event ID to open after data loads (if any).
     */
    function readURLState() {
        var params = new URLSearchParams(window.location.search);

        var view = params.get("view");
        if (view === "rooms") {
            currentView = "rooms";
            btnRooms.classList.add("active");
            btnCalendar.classList.remove("active");
        } else {
            currentView = "calendar";
            btnCalendar.classList.add("active");
            btnRooms.classList.remove("active");
        }

        var day = parseInt(params.get("day"), 10);
        if (!isNaN(day) && day >= -1) {
            currentDayIndex = day;
        }

        var search = params.get("search");
        if (search) {
            filters.search = search;
            filterSearch.value = search;
        }

        var tracks = params.get("tracks");
        if (tracks) {
            tracks.split(",").forEach(function (id) {
                if (id) filters.tracks.add(id.trim());
            });
        }

        var tags = params.get("tags");
        if (tags) {
            tags.split(",").forEach(function (id) {
                if (id) filters.tags.add(id.trim());
            });
        }

        var speakers = params.get("speakers");
        if (speakers) {
            speakers.split(",").forEach(function (id) {
                if (id) filters.speakers.add(id.trim());
            });
        }

        var rooms = params.get("rooms");
        if (rooms) {
            rooms.split(",").forEach(function (id) {
                if (id) filters.rooms.add(id.trim());
            });
        }

        var eventKey = params.get("event");
        return eventKey || null;
    }

    /**
     * After schedule data is loaded, sync dropdown visual states
     * to match any filters that were pre-loaded from the URL.
     */
    function syncDropdownStatesFromFilters() {
        document.querySelectorAll(".dropdown-item").forEach(function (item) {
            var panel = item.closest(".dropdown-panel");
            if (!panel) return;
            var filterKey = panel.id
                .replace("dropdown-", "");
            var itemId = item.getAttribute("data-id");
            if (filters[filterKey] && filters[filterKey].has(itemId)) {
                item.classList.add("selected");
                item.setAttribute("aria-checked", "true");
            }
        });
        // Update button highlighted states
        var keyMap = {
            tracks: "btn-filter-tracks",
            tags: "btn-filter-tags",
            speakers: "btn-filter-speakers",
            rooms: "btn-filter-rooms",
        };
        Object.keys(keyMap).forEach(function (key) {
            var btn = $(keyMap[key]);
            if (btn) updateFilterButtonState(btn, filters[key]);
        });
    }

    // --- Event Listeners ---

    // View toggle
    btnCalendar.addEventListener("click", function () {
        currentView = "calendar";
        btnCalendar.classList.add("active");
        btnRooms.classList.remove("active");
        pushURLState();
        render();
    });

    btnRooms.addEventListener("click", function () {
        currentView = "rooms";
        btnRooms.classList.add("active");
        btnCalendar.classList.remove("active");
        pushURLState();
        render();
    });

    // Search
    var searchTimeout;
    filterSearch.addEventListener("input", function () {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(function () {
            filters.search = filterSearch.value.trim();
            updateClearButton();
            pushURLState();
            render();
        }, 250);
    });

    // Refresh
    btnRefresh.addEventListener("click", function () {
        fetch(BASE_PATH + "/api/refresh", { method: "POST" })
            .then(function () {
                // Wait a moment for data to be fetched, then reload
                setTimeout(loadData, 2000);
            })
            .catch(function () {
                // Fallback: just reload anyway
                loadData();
            });
    });

    // Retry
    btnRetry.addEventListener("click", loadData);

    // Clear filters
    btnClearFilters.addEventListener("click", function () {
        filters.search = "";
        filters.tracks.clear();
        filters.tags.clear();
        filters.speakers.clear();
        filters.rooms.clear();
        filterSearch.value = "";

        // Reset dropdown visual states
        document.querySelectorAll(".dropdown-item.selected").forEach(function (item) {
            item.classList.remove("selected");
            item.setAttribute("aria-checked", "false");
        });
        document.querySelectorAll(".filter-btn.has-selection").forEach(function (btn) {
            btn.classList.remove("has-selection");
        });

        updateClearButton();
        pushURLState();
        render();
    });

    // Modal close
    modalClose.addEventListener("click", closeDetailModal);
    detailModal.addEventListener("click", function (e) {
        if (e.target === detailModal) {
            closeDetailModal();
        }
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !detailModal.classList.contains("hidden")) {
            closeDetailModal();
        }
    });

    // Modal copy-link button
    if (modalCopyLink) {
        modalCopyLink.addEventListener("click", function () {
            var url = window.location.href;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(url).then(function () {
                    modalCopyLink.textContent = "Copied!";
                    setTimeout(function () {
                        modalCopyLink.textContent = "Copy link";
                    }, 2000);
                }).catch(function () {
                    modalCopyLink.textContent = url;
                });
            } else {
                // Fallback: select a temporary input
                var tmp = document.createElement("input");
                tmp.value = url;
                document.body.appendChild(tmp);
                tmp.select();
                try { document.execCommand("copy"); modalCopyLink.textContent = "Copied!"; } catch (e) { }
                document.body.removeChild(tmp);
                setTimeout(function () { modalCopyLink.textContent = "Copy link"; }, 2000);
            }
        });
    }

    /**
     * If an event ID is provided (from URL param), find and open that slot's modal.
     * Should be called after scheduleData is loaded.
     */
    function openEventByStableId(stableId) {
        if (!stableId || !scheduleData || !scheduleData.days) return;
        for (var d = 0; d < scheduleData.days.length; d++) {
            var slots = scheduleData.days[d].slots;
            for (var s = 0; s < slots.length; s++) {
                if (slots[s].stable_id === stableId) {
                    // Switch to the day that contains this event
                    currentDayIndex = d;
                    updateActiveDayTab();
                    render();
                    openDetailModal(slots[s]);
                    return;
                }
            }
        }
    }

    // --- Init ---
    // Read URL state first (sets view, day, filters) then load data.
    var _pendingEventKey = readURLState();
    loadData().then(function () {
        // After data loads, sync dropdown visual states for pre-loaded filters
        syncDropdownStatesFromFilters();
        updateClearButton();
        // Re-render now that day index might have changed
        updateActiveDayTab();
        render();
        if (_pendingEventKey) {
            openEventByStableId(_pendingEventKey);
        }
    });
})();
