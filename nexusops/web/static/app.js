// NexusOps Control Plane Frontend Application

let currentActiveTool = null;
let currentDecisionRequestId = null;
let currentDecisionType = null;

document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    setupEventListeners();
    refreshAllData();

    // Auto-refresh metrics & approvals every 10 seconds
    setInterval(refreshAllData, 10000);
});

function setupNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    navItems.forEach((btn) => {
        btn.addEventListener("click", () => {
            navItems.forEach((b) => b.classList.remove("active"));
            document.querySelectorAll(".tab-pane").forEach((tab) => tab.classList.remove("active"));

            btn.classList.add("active");
            const targetTab = btn.getAttribute("data-tab");
            const pane = document.getElementById(targetTab);
            if (pane) pane.classList.add("active");

            // Update title
            const tabTitleMap = {
                "tab-overview": "Infrastructure Overview",
                "tab-approvals": "Human-in-the-Loop Approvals",
                "tab-containers": "Containers & Services",
                "tab-tools": "Model Context Protocol Tools",
                "tab-audit": "Operational Audit Trail",
            };
            document.getElementById("page-title").textContent = tabTitleMap[targetTab] || "NexusOps Control Plane";
        });
    });
}

function setupEventListeners() {
    document.getElementById("btn-refresh").addEventListener("click", refreshAllData);

    document.getElementById("btn-reset-mock").addEventListener("click", async () => {
        await fetch("/api/infra/reset", { method: "POST" });
        refreshAllData();
        alert("Simulated infrastructure reset to baseline state.");
    });

    document.getElementById("approval-status-filter").addEventListener("change", loadApprovals);

    // Modal decision controls
    const modal = document.getElementById("decision-modal");
    document.getElementById("modal-close-btn").addEventListener("click", () => modal.classList.remove("show"));
    document.getElementById("modal-cancel-btn").addEventListener("click", () => modal.classList.remove("show"));
    document.getElementById("modal-confirm-btn").addEventListener("click", submitDecision);

    // Tool test form
    document.getElementById("tool-test-form").addEventListener("submit", executeToolTest);
}

async function refreshAllData() {
    await Promise.all([
        loadStatus(),
        loadApprovals(),
        loadContainers(),
        loadTools(),
        loadAuditLogs(),
        loadMetrics(),
    ]);
}

async function loadStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();

        document.getElementById("stat-total-tools").textContent = data.total_tools;
        document.getElementById("stat-pending-approvals").textContent = data.pending_approvals_count;
        document.getElementById("nav-pending-badge").textContent = data.pending_approvals_count;
        document.getElementById("stat-uptime").textContent = `${Math.floor(data.uptime_seconds)}s`;
    } catch (err) {
        console.error("Failed to load status:", err);
    }
}

async function loadMetrics() {
    try {
        // Query system metrics via MCP tool endpoint or mock
        const res = await fetch("/mcp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                id: 1,
                method: "tools/call",
                params: { name: "get_system_metrics", arguments: {} },
            }),
        });
        const data = await res.json();
        const metrics = JSON.parse(data.result.content[0].text);

        const container = document.getElementById("system-metrics-container");
        container.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 10px;">
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:12px;">
                        <span>CPU Load (${metrics.cpu.core_count} cores)</span>
                        <strong>${metrics.cpu.percent}%</strong>
                    </div>
                    <div style="background:#21262d; border-radius:4px; height:8px; margin-top:4px;">
                        <div style="background:#58a6ff; width:${metrics.cpu.percent}%; height:100%; border-radius:4px;"></div>
                    </div>
                </div>
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:12px;">
                        <span>Memory (${metrics.memory.used_gb} / ${metrics.memory.total_gb} GB)</span>
                        <strong>${metrics.memory.percent}%</strong>
                    </div>
                    <div style="background:#21262d; border-radius:4px; height:8px; margin-top:4px;">
                        <div style="background:#bc8cff; width:${metrics.memory.percent}%; height:100%; border-radius:4px;"></div>
                    </div>
                </div>
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:12px;">
                        <span>Root Disk (${metrics.disk.free_gb} GB Free)</span>
                        <strong>${metrics.disk.percent}%</strong>
                    </div>
                    <div style="background:#21262d; border-radius:4px; height:8px; margin-top:4px;">
                        <div style="background:#3fb950; width:${metrics.disk.percent}%; height:100%; border-radius:4px;"></div>
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
        console.error("Failed to load metrics:", err);
    }
}

async function loadApprovals() {
    try {
        const filter = document.getElementById("approval-status-filter").value;
        const url = filter ? `/api/approvals?status=${filter}` : `/api/approvals`;
        const res = await fetch(url);
        const approvals = await res.json();

        const container = document.getElementById("approvals-list-container");
        if (approvals.length === 0) {
            container.innerHTML = `<p class="text-muted" style="text-align:center; padding: 24px;">No approvals found matching filter.</p>`;
            return;
        }

        container.innerHTML = approvals.map(app => `
            <div class="approval-card ${app.safety_tier === 'critical' ? 'critical' : ''}">
                <div>
                    <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 6px;">
                        <span class="badge ${getStatusBadge(app.status)}">${app.status.toUpperCase()}</span>
                        <span class="badge badge-danger">${app.safety_tier.toUpperCase()}</span>
                        <strong>${app.tool_name}</strong>
                    </div>
                    <p style="font-size: 13px; margin-bottom: 4px;"><strong>Reason:</strong> ${escapeHtml(app.reason)}</p>
                    <div style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">
                        Requester: ${app.requester} (${app.requester_role}) | Args: ${JSON.stringify(app.arguments)}
                    </div>
                </div>
                ${app.status === 'pending' ? `
                    <div style="display: flex; gap: 8px;">
                        <button class="btn btn-success btn-sm" onclick="openDecisionModal('${app.id}', 'approve', '${app.tool_name}')">Approve</button>
                        <button class="btn btn-danger btn-sm" onclick="openDecisionModal('${app.id}', 'reject', '${app.tool_name}')">Reject</button>
                    </div>
                ` : `
                    <div style="font-size: 12px; color: var(--text-muted);">
                        ${app.decision_by ? `By: ${app.decision_by}` : ''}
                    </div>
                `}
            </div>
        `).join("");
    } catch (err) {
        console.error("Failed to load approvals:", err);
    }
}

function openDecisionModal(requestId, type, toolName) {
    currentDecisionRequestId = requestId;
    currentDecisionType = type;

    const modal = document.getElementById("decision-modal");
    document.getElementById("modal-title").textContent = type === "approve" ? "Approve High-Risk Action" : "Reject Action";
    document.getElementById("modal-desc").textContent = `Are you sure you want to ${type.toUpperCase()} the execution of tool '${toolName}'?`;

    const confirmBtn = document.getElementById("modal-confirm-btn");
    confirmBtn.className = `btn btn-${type === 'approve' ? 'success' : 'danger'}`;
    confirmBtn.textContent = type === 'approve' ? "Confirm Approval" : "Confirm Rejection";

    modal.classList.add("show");
}

async function submitDecision() {
    if (!currentDecisionRequestId || !currentDecisionType) return;

    const approver = document.getElementById("modal-approver-name").value || "lead-devops-engineer";
    const note = document.getElementById("modal-note").value || `Action ${currentDecisionType}d via NexusOps dashboard`;

    const url = `/api/approvals/${currentDecisionRequestId}/${currentDecisionType}`;
    try {
        const res = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer nexus-admin-secret-key-12345",
            },
            body: JSON.stringify({ approver, note }),
        });

        if (!res.ok) {
            const err = await res.json();
            alert(`Error: ${err.detail || 'Failed to process decision'}`);
        } else {
            document.getElementById("decision-modal").classList.remove("show");
            refreshAllData();
        }
    } catch (err) {
        alert("Failed to submit decision: " + err);
    }
}

async function loadContainers() {
    try {
        const res = await fetch("/api/infra/containers");
        const containers = await res.json();

        document.getElementById("stat-containers-count").textContent = containers.length;
        const unhealthy = containers.filter(c => c.health !== 'healthy').length;
        document.getElementById("stat-containers-unhealthy").textContent = `${unhealthy} degraded/unhealthy`;

        const grid = document.getElementById("containers-list-container");
        grid.innerHTML = containers.map(c => {
            const borderClass = c.status === 'error' ? 'border-error' : (c.health === 'unhealthy' ? 'border-unhealthy' : '');
            return `
                <div class="container-card ${borderClass}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>${c.name}</strong>
                        <div>
                            <span class="badge ${c.status === 'running' ? 'badge-success' : 'badge-danger'}">${c.status}</span>
                            <span class="badge ${c.health === 'healthy' ? 'badge-primary' : 'badge-warning'}">${c.health}</span>
                        </div>
                    </div>
                    <div class="container-meta">
                        <span>Image: ${c.image}</span>
                        <span>Restarts: ${c.restart_count}</span>
                    </div>
                    <div style="display: flex; gap: 16px; font-size: 12px; font-family: var(--font-mono);">
                        <span>CPU: ${c.cpu_percent}%</span>
                        <span>Memory: ${c.memory_mb} MB</span>
                    </div>
                    <div style="display: flex; gap: 6px; margin-top: 8px;">
                        <button class="btn btn-secondary btn-sm" onclick="quickRemediate('${c.name}', 'restart_service')">Restart</button>
                        ${c.name.includes('redis') ? `<button class="btn btn-secondary btn-sm" onclick="quickRemediate('${c.name}', 'flush_cache')">Flush Cache</button>` : ''}
                        <button class="btn btn-outline btn-sm" onclick="quickInspectLogs('${c.name}')">View Logs</button>
                    </div>
                </div>
            `;
        }).join("");
    } catch (err) {
        console.error("Failed to load containers:", err);
    }
}

async function quickRemediate(serviceName, toolName) {
    const args = toolName === "restart_service" ? { service_name: serviceName } : {};
    try {
        const res = await fetch("/mcp", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer nexus-operator-secret-key-67890",
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                id: 1,
                method: "tools/call",
                params: { name: toolName, arguments: args },
            }),
        });
        const data = await res.json();
        alert(`Executed ${toolName}:\n${data.result.content[0].text}`);
        refreshAllData();
    } catch (err) {
        alert("Failed to execute remediation: " + err);
    }
}

async function quickInspectLogs(containerName) {
    try {
        const res = await fetch("/mcp", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                id: 1,
                method: "tools/call",
                params: { name: "analyze_service_logs", arguments: { container_id_or_name: containerName } },
            }),
        });
        const data = await res.json();
        alert(`Log Analysis for ${containerName}:\n${data.result.content[0].text}`);
    } catch (err) {
        alert("Failed to fetch logs: " + err);
    }
}

async function loadTools() {
    try {
        const res = await fetch("/api/tools");
        const toolsMap = await res.json();

        const container = document.getElementById("tools-list-container");
        container.innerHTML = Object.values(toolsMap).map(tool => `
            <div class="tool-item" onclick="selectTool('${tool.name}')">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <strong>${tool.name}</strong>
                    <div>
                        <span class="badge ${getTierBadge(tool.safety_tier)}">${tool.safety_tier}</span>
                        <span class="badge badge-purple">${tool.required_role}</span>
                    </div>
                </div>
                <p style="font-size: 12px; color: var(--text-muted);">${escapeHtml(tool.description)}</p>
            </div>
        `).join("");
    } catch (err) {
        console.error("Failed to load tools:", err);
    }
}

window.selectTool = async function(toolName) {
    currentActiveTool = toolName;
    document.querySelectorAll(".tool-item").forEach(item => item.classList.remove("active"));
    event.currentTarget.classList.add("active");

    document.getElementById("test-tool-name").value = toolName;

    // Prefill default arguments
    const defaults = {
        "list_containers": { "all_containers": true },
        "inspect_container": { "container_id_or_name": "nexus-redis-cache" },
        "get_container_logs": { "container_id_or_name": "nexus-auth-service", "tail": 20 },
        "analyze_service_logs": { "container_id_or_name": "nexus-redis-cache" },
        "check_service_health": { "container_id_or_name": "nexus-api-gateway" },
        "restart_service": { "service_name": "nexus-auth-service" },
        "scale_service": { "service_name": "nexus-worker", "replicas": 3 },
        "flush_cache": {},
        "terminate_container": { "container_id_or_name": "nexus-redis-cache" },
        "prune_system_resources": { "prune_volumes": false },
        "probe_network_port": { "host": "127.0.0.1", "port": 8000 },
        "list_active_processes": { "limit": 5, "sort_by": "cpu" },
        "get_system_metrics": {},
    };
    document.getElementById("test-tool-args").value = JSON.stringify(defaults[toolName] || {}, null, 2);
};

async function executeToolTest(e) {
    e.preventDefault();
    const toolName = document.getElementById("test-tool-name").value;
    if (!toolName) {
        alert("Please select a tool first.");
        return;
    }

    let args;
    try {
        args = JSON.parse(document.getElementById("test-tool-args").value);
    } catch (err) {
        alert("Invalid JSON arguments");
        return;
    }

    const apiKey = document.getElementById("test-tool-role").value;
    const outputEl = document.getElementById("test-tool-output");
    outputEl.textContent = "Executing via MCP JSON-RPC 2.0...";

    try {
        const payload = {
            jsonrpc: "2.0",
            id: Date.now(),
            method: "tools/call",
            params: {
                name: toolName,
                arguments: args,
            },
        };

        const res = await fetch("/mcp", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${apiKey}`,
            },
            body: JSON.stringify(payload),
        });

        const json = await res.json();
        outputEl.textContent = JSON.stringify(json, null, 2);
        refreshAllData();
    } catch (err) {
        outputEl.textContent = `Error: ${err}`;
    }
}

async function loadAuditLogs() {
    try {
        const res = await fetch("/api/audit?limit=25");
        const logs = await res.json();

        const tbody = document.getElementById("audit-logs-tbody");
        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;" class="text-muted">No audit events recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => `
            <tr>
                <td style="font-family: var(--font-mono); font-size:11px;">${l.timestamp.split("T")[1].replace("Z", "")}</td>
                <td><strong>${l.requester}</strong></td>
                <td><span class="badge badge-purple">${l.role}</span></td>
                <td><code>${l.tool_name}</code></td>
                <td><span class="badge ${getStatusBadge(l.status)}">${l.status}</span></td>
                <td>${l.duration_ms}ms</td>
                <td style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; color:var(--text-muted);">
                    ${l.error_message || l.result_summary || (l.approval_id ? `Approval ID: ${l.approval_id}` : 'OK')}
                </td>
            </tr>
        `).join("");
    } catch (err) {
        console.error("Failed to load audit logs:", err);
    }
}

function getTierBadge(tier) {
    if (tier === 'critical') return 'badge-danger';
    if (tier === 'moderate') return 'badge-warning';
    return 'badge-success';
}

function getStatusBadge(status) {
    const s = (status || '').toLowerCase();
    if (s === 'success' || s === 'approved' || s === 'executed') return 'badge-success';
    if (s === 'pending' || s === 'pending_approval') return 'badge-warning';
    if (s === 'failed' || s === 'unauthorized' || s === 'rejected' || s === 'expired') return 'badge-danger';
    return 'badge-primary';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
