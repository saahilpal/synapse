document.addEventListener("DOMContentLoaded", () => {
    // App State
    let timelineEvents = [];
    let currentEventIndex = 0;
    let selectedProjectionKind = "overview";
    let selectedNode = null;
    let graphRenderer = null;

    // Initialize graph renderer
    graphRenderer = new SynapseGraphRenderer("graph-svg");

    // UI Elements
    const timelineScrubber = document.getElementById("timeline-scrubber");
    const timelineTitle = document.getElementById("timeline-current-title");
    const timelineMeta = document.getElementById("timeline-commit-meta");
    const timelineTicks = document.getElementById("timeline-ticks");
    const timelinePlayBtn = document.getElementById("timeline-play-btn");
    const timelineSpeedSelect = document.getElementById("timeline-speed-select");
    let playIntervalId = null;
    
    const statEvents = document.getElementById("stat-events");
    const statContexts = document.getElementById("stat-contexts");
    const statObjects = document.getElementById("stat-objects");
    const systemBadge = document.getElementById("system-badge");
    const statusText = document.getElementById("status-text");

    const canvasTitle = document.getElementById("canvas-title");
    const projectionSelector = document.getElementById("projection-selector");
    const filterPanel = document.getElementById("filter-panel");
    const subsystemFilterGroup = document.getElementById("subsystem-filter-group");
    const branchFilterGroup = document.getElementById("branch-filter-group");
    const compareHashSelect = document.getElementById("compare-hash");
    
    const detailEmpty = document.getElementById("detail-empty");
    const detailPanel = document.getElementById("detail-panel");
    const detailType = document.getElementById("detail-type");
    const detailTitle = document.getElementById("detail-title");
    const detailId = document.getElementById("detail-id");
    const detailSourceUri = document.getElementById("detail-source-uri");
    const detailConfidencePct = document.getElementById("detail-confidence-pct");
    const detailConfidenceFill = document.getElementById("detail-confidence-fill");
    const detailConfidenceRationale = document.getElementById("detail-confidence-rationale");
    const detailValidationState = document.getElementById("detail-validation-state");
    const detailMetadata = document.getElementById("detail-metadata");

    // Action buttons
    const btnAddNote = document.getElementById("btn-add-note");
    const btnAddIncident = document.getElementById("btn-add-incident");
    const submitNoteBtn = document.getElementById("submit-note-btn");
    const submitIncidentBtn = document.getElementById("submit-incident-btn");
    const applyFiltersBtn = document.getElementById("apply-filters-btn");

    // Zoom Buttons
    document.getElementById("zoom-in-btn").addEventListener("click", () => graphRenderer.zoomIn());
    document.getElementById("zoom-out-btn").addEventListener("click", () => graphRenderer.zoomOut());
    document.getElementById("reset-zoom-btn").addEventListener("click", () => graphRenderer.resetZoom());

    // Connect Modals
    btnAddNote.addEventListener("click", () => showModal("modal-note"));
    btnAddIncident.addEventListener("click", () => showModal("modal-incident"));

    // Close modals on clicking background
    document.querySelectorAll(".modal-backdrop").forEach(el => {
        el.addEventListener("click", (e) => {
            if (e.target === el) {
                el.style.display = "none";
            }
        });
    });

    // Start App Sequence
    bootstrap();

    async function bootstrap() {
        try {
            await fetchStatus();
            await fetchTimeline();
            
            // Initial graph render
            if (timelineEvents.length > 0) {
                currentEventIndex = timelineEvents.length - 1;
                timelineScrubber.value = currentEventIndex;
                updateTimelineDisplay();
                await fetchAndRenderProjection();
            }
            
            systemBadge.classList.add("online");
            statusText.textContent = "Online";
        } catch (err) {
            console.error("Bootstrap error:", err);
            statusText.textContent = "Offline/Error";
            systemBadge.classList.remove("online");
        }
    }

    async function fetchStatus() {
        const res = await fetch("/api/v1/status");
        if (!res.ok) throw new Error("status fetch failed");
        const status = await res.json();
        
        statEvents.textContent = status.events || 0;
        statContexts.textContent = status.context_objects || 0;
        statObjects.textContent = status.semantic_objects || 0;
    }

    async function fetchTimeline() {
        const res = await fetch("/api/v1/timeline");
        if (!res.ok) throw new Error("timeline fetch failed");
        const data = await res.json();
        
        // Timeline events are received chronologically, let's reverse them if they are sorted DESC
        timelineEvents = data.events || [];
        timelineEvents.reverse(); // Ensure chronological order from oldest to newest

        if (timelineEvents.length > 0) {
            timelineScrubber.max = timelineEvents.length - 1;
            timelineScrubber.value = timelineEvents.length - 1;
            
            // Build ticks
            timelineTicks.innerHTML = "";
            timelineEvents.forEach((evt, idx) => {
                const tick = document.createElement("div");
                tick.className = "timeline-tick" + (idx === currentEventIndex ? " active" : "");
                timelineTicks.appendChild(tick);
            });

            // Populate branch compare hashes dropdown
            compareHashSelect.innerHTML = "";
            timelineEvents.forEach(evt => {
                if (evt.payload && evt.payload.context_hash) {
                    const opt = document.createElement("option");
                    opt.value = evt.payload.context_hash;
                    opt.textContent = `${evt.summary.substring(0, 30)}... (${evt.payload.context_hash.substring(0, 8)})`;
                    compareHashSelect.appendChild(opt);
                }
            });
        }
    }

    function updateTimelineDisplay() {
        if (timelineEvents.length === 0) return;
        const currentEvent = timelineEvents[currentEventIndex];
        
        timelineTitle.textContent = currentEvent.summary || "Manual context commit";
        const commit = currentEvent.git_commit_hash ? currentEvent.git_commit_hash.substring(0, 8) : "no-commit";
        const branch = currentEvent.branch || "main";
        timelineMeta.textContent = `[${branch} / ${commit}]`;

        // Update tick visual active state
        const ticks = timelineTicks.children;
        for (let i = 0; i < ticks.length; i++) {
            if (i === currentEventIndex) {
                ticks[i].classList.add("active");
            } else {
                ticks[i].classList.remove("active");
            }
        }
    }

    // Timeline Scrub Handling
    timelineScrubber.addEventListener("input", (e) => {
        stopPlayback();
        currentEventIndex = parseInt(e.target.value);
        updateTimelineDisplay();
    });

    timelineScrubber.addEventListener("change", async (e) => {
        stopPlayback();
        currentEventIndex = parseInt(e.target.value);
        await fetchAndRenderProjection();
    });

    // Auto-playback controls
    timelinePlayBtn.addEventListener("click", () => {
        if (playIntervalId) {
            stopPlayback();
        } else {
            startPlayback();
        }
    });

    timelineSpeedSelect.addEventListener("change", () => {
        if (playIntervalId) {
            stopPlayback();
            startPlayback();
        }
    });

    function startPlayback() {
        timelinePlayBtn.textContent = "❚❚";
        const intervalMs = parseInt(timelineSpeedSelect.value) || 2000;
        playIntervalId = setInterval(async () => {
            if (currentEventIndex >= timelineEvents.length - 1) {
                currentEventIndex = 0;
            } else {
                currentEventIndex++;
            }
            timelineScrubber.value = currentEventIndex;
            updateTimelineDisplay();
            await fetchAndRenderProjection();
        }, intervalMs);
    }

    function stopPlayback() {
        if (playIntervalId) {
            clearInterval(playIntervalId);
            playIntervalId = null;
        }
        timelinePlayBtn.textContent = "▶";
    }

    // Projection tab selectors
    projectionSelector.addEventListener("click", async (e) => {
        const btn = e.target.closest(".btn-tab");
        if (!btn) return;
        
        document.querySelectorAll(".btn-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        selectedProjectionKind = btn.dataset.kind;
        canvasTitle.textContent = btn.innerText.replace(/^\S+\s+/, ""); // Remove icon emoji
        
        // Manage filter views
        if (selectedProjectionKind === "subsystem") {
            filterPanel.style.display = "block";
            subsystemFilterGroup.style.display = "block";
            branchFilterGroup.style.display = "none";
        } else if (selectedProjectionKind === "branch") {
            filterPanel.style.display = "block";
            subsystemFilterGroup.style.display = "none";
            branchFilterGroup.style.display = "block";
        } else {
            filterPanel.style.display = "none";
            subsystemFilterGroup.style.display = "none";
            branchFilterGroup.style.display = "none";
        }

        await fetchAndRenderProjection();
    });

    // Filter button clicked
    applyFiltersBtn.addEventListener("click", async () => {
        await fetchAndRenderProjection();
    });

    async function fetchAndRenderProjection() {
        if (timelineEvents.length === 0) return;
        
        // Find current context hash
        // The event timeline contains a context_hash in the payload of contexts created
        const currentEvent = timelineEvents[currentEventIndex];
        
        // Fallback trace logic to find context hash
        let contextHash = null;
        if (currentEvent.payload && currentEvent.payload.context_hash) {
            contextHash = currentEvent.payload.context_hash;
        } else if (currentEvent.payload && currentEvent.payload.payload_hash) {
            contextHash = currentEvent.payload.payload_hash;
        } else {
            // Find most recent context commit in events up to index
            for (let i = currentEventIndex; i >= 0; i--) {
                if (timelineEvents[i].event_type === "context.object_created" && timelineEvents[i].payload && timelineEvents[i].payload.context_hash) {
                    contextHash = timelineEvents[i].payload.context_hash;
                    break;
                }
            }
        }

        if (!contextHash) {
            // If still no hash, scan back for any active head or event sequence
            console.warn("Could not identify context hash for projection.");
            return;
        }

        let url = `/api/v1/projection/${contextHash}/${selectedProjectionKind}`;
        const params = [];
        
        if (selectedProjectionKind === "subsystem") {
            const prefix = document.getElementById("subsystem-prefix").value;
            if (prefix) params.push(`prefix=${encodeURIComponent(prefix)}`);
        } else if (selectedProjectionKind === "branch") {
            const compareWith = compareHashSelect.value;
            if (compareWith) params.push(`compare_with=${encodeURIComponent(compareWith)}`);
        }
        
        if (params.length > 0) {
            url += `?${params.join("&")}`;
        }

        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error("Failed to fetch projection");
            const graph = await res.json();
            
            graphRenderer.update(graph.nodes || [], graph.edges || [], onNodeClicked);
        } catch (err) {
            console.error("Error loading projection:", err);
        }
    }

    function onNodeClicked(node) {
        selectedNode = node;
        
        detailEmpty.style.display = "none";
        detailPanel.style.display = "block";

        detailType.textContent = node.kind;
        detailType.style.color = `var(--accent-${node.kind})`;
        detailTitle.textContent = node.label;
        detailId.textContent = node.id;
        detailSourceUri.textContent = node.metadata.source_uri || "no source";
        
        const confPct = Math.round(node.confidence * 100);
        detailConfidencePct.textContent = `${confPct}%`;
        detailConfidenceFill.style.width = `${confPct}%`;

        // Render validation state
        const valState = node.validation_state || (node.confidence >= 0.85 ? "validated" : "assumed");
        detailValidationState.textContent = valState;
        detailValidationState.className = `validation-badge ${valState.toLowerCase()}`;
        
        // Build detail rationale if available
        let rationale = "Derived from content analysis.";
        if (node.metadata.metadata && node.metadata.metadata.rationale) {
            rationale = node.metadata.metadata.rationale;
        }
        detailConfidenceRationale.textContent = rationale;

        // Render metadata json
        detailMetadata.textContent = JSON.stringify(node.metadata.metadata || {}, null, 2);
    }

    // Modal submit handles
    submitNoteBtn.addEventListener("click", async () => {
        const text = document.getElementById("note-message").value.trim();
        if (!text) return;

        try {
            submitNoteBtn.disabled = true;
            submitNoteBtn.textContent = "Committing...";
            
            const res = await fetch("/api/v1/note", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text })
            });

            if (!res.ok) throw new Error("Failed to submit note");
            
            closeModal("modal-note");
            document.getElementById("note-message").value = "";
            
            // Reload status & timeline
            await bootstrap();
        } catch (err) {
            alert("Error committing note: " + err.message);
        } finally {
            submitNoteBtn.disabled = false;
            submitNoteBtn.textContent = "Commit Note";
        }
    });

    submitIncidentBtn.addEventListener("click", async () => {
        const title = document.getElementById("incident-title").value.trim();
        const summary = document.getElementById("incident-summary").value.trim();
        if (!title || !summary) return;

        try {
            submitIncidentBtn.disabled = true;
            submitIncidentBtn.textContent = "Recording...";

            const res = await fetch("/api/v1/incident", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, summary })
            });

            if (!res.ok) throw new Error("Failed to record incident");

            closeModal("modal-incident");
            document.getElementById("incident-title").value = "";
            document.getElementById("incident-summary").value = "";

            await bootstrap();
        } catch (err) {
            alert("Error recording incident: " + err.message);
        } finally {
            submitIncidentBtn.disabled = false;
            submitIncidentBtn.textContent = "Record Incident";
        }
    });
});

function showModal(id) {
    document.getElementById(id).style.display = "flex";
}

function closeModal(id) {
    document.getElementById(id).style.display = "none";
}
