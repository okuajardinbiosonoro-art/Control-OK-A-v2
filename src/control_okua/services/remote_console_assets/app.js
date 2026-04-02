(function () {
  "use strict";

  const STORAGE_KEY = "ckv2_remote_console_session_v1";
  const POLL_SUMMARY_MS = 4000;
  const POLL_DETAIL_MS = 3000;
  const ROLE_ORDER = ["observador", "tecnico", "admin"];

  const state = {
    token: "",
    roleHint: "observador",
    selectedNodeId: null,
    summaryTimer: null,
    detailTimer: null,
    isBusy: false,
  };

  const refs = {
    tokenForm: document.getElementById("token-form"),
    tokenInput: document.getElementById("token-input"),
    roleSelect: document.getElementById("role-select"),
    logoutButton: document.getElementById("logout-button"),
    refreshAllButton: document.getElementById("refresh-all-button"),
    authChip: document.getElementById("auth-chip"),
    roleChip: document.getElementById("role-chip"),
    globalMessage: document.getElementById("global-message"),
    summaryGrid: document.getElementById("summary-grid"),
    nodesList: document.getElementById("nodes-list"),
    nodesEmpty: document.getElementById("nodes-empty"),
    detailEmpty: document.getElementById("detail-empty"),
    nodeDetail: document.getElementById("node-detail"),
    detailTitle: document.getElementById("detail-title"),
    detailSubtitle: document.getElementById("detail-subtitle"),
    detailMessage: document.getElementById("detail-message"),
    actionHint: document.getElementById("action-hint"),
    requestStatButton: document.getElementById("request-stat-button"),
    rebootButton: document.getElementById("reboot-button"),
    runtimeFields: document.getElementById("runtime-fields"),
    controlFields: document.getElementById("control-fields"),
    otaFields: document.getElementById("ota-fields"),
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopPolling();
      return;
    }
    startPolling();
    void refreshAll();
  });

  refs.tokenForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const token = refs.tokenInput.value.trim();
    const roleHint = refs.roleSelect.value;
    if (!token) {
      setBanner(refs.globalMessage, "Ingresa un bearer token para continuar.", true);
      return;
    }
    state.token = token;
    state.roleHint = roleHint;
    saveSession();
    syncAccessUi();
    refs.tokenInput.value = "";
    setBanner(refs.globalMessage, "Token guardado localmente para esta consola.", false);
    startPolling();
    void refreshAll();
  });

  refs.logoutButton.addEventListener("click", () => {
    clearSession();
    renderLoggedOutState();
  });

  refs.refreshAllButton.addEventListener("click", () => {
    void refreshAll();
  });

  refs.requestStatButton.addEventListener("click", () => {
    if (state.selectedNodeId === null) {
      return;
    }
    void invokeNodeAction("request-stat-now");
  });

  refs.rebootButton.addEventListener("click", () => {
    if (state.selectedNodeId === null) {
      return;
    }
    void invokeNodeAction("reboot", { delay_ms: 0 });
  });

  loadSession();
  syncAccessUi();
  if (state.token) {
    startPolling();
    void refreshAll();
  } else {
    renderLoggedOutState();
  }

  async function refreshAll() {
    if (!state.token || state.isBusy) {
      return;
    }
    state.isBusy = true;
    try {
      const [healthResponse, summaryResponse, nodesResponse] = await Promise.all([
        apiRequest("/api/v1/health"),
        apiRequest("/api/v1/runtime/summary"),
        apiRequest("/api/v1/nodes"),
      ]);

      renderSummary(healthResponse.data, summaryResponse.data);
      renderNodes(nodesResponse.data.nodes || []);
      clearBanner(refs.globalMessage);

      if (state.selectedNodeId !== null) {
        await refreshSelectedNode();
      }
    } catch (error) {
      handleGlobalError(error);
    } finally {
      state.isBusy = false;
    }
  }

  async function refreshSelectedNode() {
    if (state.selectedNodeId === null || !state.token) {
      return;
    }
    try {
      const detailResponse = await apiRequest(`/api/v1/nodes/${state.selectedNodeId}`);
      renderNodeDetail(detailResponse.data);
      clearBanner(refs.detailMessage);
    } catch (error) {
      handleDetailError(error);
    }
  }

  async function invokeNodeAction(actionName, body) {
    if (state.selectedNodeId === null) {
      return;
    }
    const nodeId = state.selectedNodeId;
    const path = `/api/v1/nodes/${nodeId}/actions/${actionName}`;
    const button = actionName === "reboot" ? refs.rebootButton : refs.requestStatButton;
    button.disabled = true;
    try {
      const response = await apiRequest(path, {
        method: "POST",
        body: body || {},
      });
      const commandName = response.data?.result?.command_name || actionName;
      const finalStatus = response.data?.result?.final_status || "ok";
      setBanner(
        refs.detailMessage,
        `${commandName} completado con estado ${finalStatus}.`,
        false
      );
      await refreshSelectedNode();
      await refreshAll();
    } catch (error) {
      setBanner(refs.detailMessage, describeError(error), true);
    } finally {
      syncActionButtons();
    }
  }

  async function apiRequest(path, options = {}) {
    const headers = {
      Accept: "application/json",
      Authorization: `Bearer ${state.token}`,
    };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    let response;
    try {
      response = await fetch(path, {
        method: options.method || "GET",
        headers,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      });
    } catch (error) {
      throw {
        kind: "network",
        message: "No se pudo alcanzar el host remoto local.",
        cause: error,
      };
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }

    if (!response.ok) {
      throw {
        kind: "http",
        status: response.status,
        payload,
      };
    }

    return payload;
  }

  function renderSummary(healthData, summaryData) {
    const summaryCards = [
      card("Gateway", healthData?.status || "unknown", healthData?.service || ""),
      card("Sesion", summaryData?.session?.state || healthData?.session?.state || "unknown", summaryData?.session?.message || ""),
      card("Backend", summaryData?.session?.backend_kind || healthData?.session?.backend_kind || "n/a", summaryData?.session?.profile_id || ""),
      card("Control-plane", healthData?.control_plane?.available ? "disponible" : "no disponible", healthData?.control_plane?.listener_active ? "listener activo" : "listener inactivo"),
      card("Nodos", stringifyValue(summaryData?.nodes?.total_nodes), `online ${stringifyValue(summaryData?.nodes?.online_count)}`),
      card("PPS", stringifyValue(summaryData?.nodes?.total_pps_evt), `stat ${stringifyValue(summaryData?.nodes?.total_pps_stat)}`),
    ];
    refs.summaryGrid.innerHTML = summaryCards.join("");
  }

  function renderNodes(nodes) {
    if (!Array.isArray(nodes) || nodes.length === 0) {
      refs.nodesEmpty.textContent = state.token
        ? "No hay nodos visibles en el runtime actual."
        : "Sin datos todavía. Guarda un token válido para consultar la API.";
      refs.nodesEmpty.classList.remove("hidden");
      refs.nodesList.innerHTML = "";
      if (state.selectedNodeId !== null) {
        refs.detailEmpty.classList.remove("hidden");
      }
      return;
    }

    refs.nodesEmpty.classList.add("hidden");
    refs.nodesList.innerHTML = nodes
      .map((node) => {
        const isSelected = state.selectedNodeId === node.node_id;
        const actionLabel = isSelected ? "Detalle abierto" : "Ver detalle";
        return `
          <article class="node-card">
            <header>
              <div>
                <div class="node-title">${escapeHtml(node.label || `Nodo ${node.node_id}`)}</div>
                <div class="fine-print">node_id ${escapeHtml(String(node.node_id))} · ${escapeHtml(node.box_label || "sin caja")}</div>
              </div>
              <span class="node-status">${escapeHtml(node.status || "unknown")}</span>
            </header>
            <div class="node-meta">
              <span>${escapeHtml(node.health_summary || "Sin health_summary")}</span>
              <span>last_seen_age_s: ${escapeHtml(stringifyValue(node.last_seen_age_s))}</span>
              <span>pps_evt/stat: ${escapeHtml(stringifyValue(node.pps_evt))} / ${escapeHtml(stringifyValue(node.pps_stat))}</span>
              <span>fw: ${escapeHtml(node.fw_version || "n/a")} · resolution: ${escapeHtml(node.control_plane?.resolution_status || "n/a")}</span>
            </div>
            <button class="button button-secondary" type="button" data-node-id="${node.node_id}">
              ${actionLabel}
            </button>
          </article>
        `;
      })
      .join("");

    refs.nodesList.querySelectorAll("button[data-node-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const nodeId = Number(button.getAttribute("data-node-id"));
        state.selectedNodeId = Number.isFinite(nodeId) ? nodeId : null;
        refs.detailEmpty.classList.add("hidden");
        void refreshSelectedNode();
      });
    });
  }

  function renderNodeDetail(detail) {
    if (!detail) {
      return;
    }
    refs.nodeDetail.classList.remove("hidden");
    refs.detailEmpty.classList.add("hidden");
    refs.detailTitle.textContent = detail.label || `Nodo ${detail.node_id}`;
    refs.detailSubtitle.textContent = `node_id ${detail.node_id} · ${detail.box_label || "sin caja"} · status ${detail.runtime?.status || "unknown"}`;
    refs.runtimeFields.innerHTML = renderDefinitionList({
      status: detail.runtime?.status,
      health_summary: detail.runtime?.health_summary,
      status_reason: detail.runtime?.status_reason,
      last_seen_age_s: detail.runtime?.last_seen_age_s,
      last_stat_age_s: detail.runtime?.last_stat_age_s,
      pps_evt: detail.runtime?.pps_evt,
      pps_stat: detail.runtime?.pps_stat,
      rssi_dbm: detail.runtime?.rssi_dbm,
      free_heap: detail.runtime?.free_heap,
      fw: [detail.runtime?.fw_major, detail.runtime?.fw_minor].filter((value) => value !== null && value !== undefined).join("."),
    });
    refs.controlFields.innerHTML = renderDefinitionList({
      resolved_ip: detail.control_plane?.resolved_ip,
      resolution_status: detail.control_plane?.resolution_status,
      transaction_active: detail.control_plane?.transaction_active,
      last_command_name: detail.control_plane?.last_command_name,
      last_final_status: detail.control_plane?.last_final_status,
      last_error_message: detail.control_plane?.last_error_message,
      message: detail.control_plane?.message,
    });
    refs.otaFields.innerHTML = renderDefinitionList({
      state_key: detail.ota?.state_key,
      error_key: detail.ota?.error_key,
      check_pending: detail.ota?.check_pending,
      pending_reboot: detail.ota?.pending_reboot,
      pending_verify: detail.ota?.pending_verify,
      health_confirmed: detail.ota?.health_confirmed,
    });
    syncActionButtons();
  }

  function renderDefinitionList(values) {
    return Object.entries(values)
      .map(([key, value]) => {
        return `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(stringifyValue(value))}</dd>`;
      })
      .join("");
  }

  function syncActionButtons() {
    const canRequestStat = state.token && roleAtLeast(state.roleHint, "tecnico");
    const canReboot = state.token && roleAtLeast(state.roleHint, "admin");
    refs.requestStatButton.disabled = !canRequestStat || state.selectedNodeId === null;
    refs.rebootButton.disabled = !canReboot || state.selectedNodeId === null;

    if (!state.token) {
      refs.actionHint.textContent = "Guarda primero un token para habilitar la consola.";
      return;
    }
    if (state.roleHint === "observador") {
      refs.actionHint.textContent =
        "Role hint observador: la UI deja las acciones bloqueadas. El backend seguiría respondiendo 403 si se intentaran.";
      return;
    }
    if (state.roleHint === "tecnico") {
      refs.actionHint.textContent =
        "Role hint tecnico: REQUEST_STAT_NOW habilitado; REBOOT_SOFT sigue reservado para admin.";
      return;
    }
    refs.actionHint.textContent =
      "Role hint admin: ambas acciones curadas están disponibles, sujetas a las precondiciones reales del runtime.";
  }

  function startPolling() {
    stopPolling();
    if (!state.token) {
      return;
    }
    state.summaryTimer = window.setInterval(() => {
      void refreshAll();
    }, POLL_SUMMARY_MS);
    state.detailTimer = window.setInterval(() => {
      if (state.selectedNodeId !== null && !document.hidden) {
        void refreshSelectedNode();
      }
    }, POLL_DETAIL_MS);
  }

  function stopPolling() {
    if (state.summaryTimer !== null) {
      window.clearInterval(state.summaryTimer);
      state.summaryTimer = null;
    }
    if (state.detailTimer !== null) {
      window.clearInterval(state.detailTimer);
      state.detailTimer = null;
    }
  }

  function handleGlobalError(error) {
    setBanner(refs.globalMessage, describeError(error), true);
    if (error?.status === 401) {
      refs.authChip.textContent = "Token rechazado";
    }
    if (error?.status === 401 || error?.kind === "network") {
      refs.nodesList.innerHTML = "";
      refs.nodesEmpty.classList.remove("hidden");
    }
  }

  function handleDetailError(error) {
    setBanner(refs.detailMessage, describeError(error), true);
    if (error?.status === 404) {
      refs.nodeDetail.classList.add("hidden");
      refs.detailEmpty.classList.remove("hidden");
      refs.detailEmpty.textContent = "El nodo seleccionado ya no aparece en snapshots actuales.";
    }
  }

  function describeError(error) {
    if (!error) {
      return "Error desconocido.";
    }
    if (error.kind === "network") {
      return "No se pudo conectar con el servicio remoto local.";
    }
    const status = error.status;
    const code = error.payload?.error?.code;
    const message = error.payload?.error?.message;
    if (status === 401) {
      return "401 unauthorized: token ausente o inválido.";
    }
    if (status === 403) {
      return "403 forbidden: acción no permitida para este rol.";
    }
    if (status === 404 && code === "node_not_found") {
      return "404 node_not_found: el nodo ya no existe en los snapshots actuales.";
    }
    if (status === 409) {
      return `409 ${code || "conflict"}: ${message || "el runtime no está en condición accionable."}`;
    }
    if (status === 502) {
      return `502 ${code || "command_failed"}: la transacción remota fue intentada y falló.`;
    }
    return `${status || "error"} ${code || "internal_error"}: ${message || "fallo no controlado."}`;
  }

  function renderLoggedOutState() {
    stopPolling();
    refs.summaryGrid.innerHTML = "";
    refs.nodesList.innerHTML = "";
    refs.nodeDetail.classList.add("hidden");
    refs.detailEmpty.classList.remove("hidden");
    refs.detailEmpty.textContent = "Selecciona un nodo para ver su detalle técnico.";
    refs.nodesEmpty.classList.remove("hidden");
    refs.nodesEmpty.textContent = "Sin datos todavía. Guarda un token válido para consultar la API.";
    clearBanner(refs.detailMessage);
    setBanner(refs.globalMessage, "Ingresa un bearer token para habilitar la consola.", false);
    syncAccessUi();
    syncActionButtons();
  }

  function syncAccessUi() {
    refs.roleSelect.value = state.roleHint;
    refs.authChip.textContent = state.token ? "Token cargado" : "Sin token";
    refs.roleChip.textContent = `Role hint: ${state.roleHint}`;
    syncActionButtons();
  }

  function saveSession() {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        token: state.token,
        roleHint: state.roleHint,
      })
    );
  }

  function loadSession() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return;
      }
      const payload = JSON.parse(raw);
      state.token = typeof payload.token === "string" ? payload.token : "";
      state.roleHint = ROLE_ORDER.includes(payload.roleHint) ? payload.roleHint : "observador";
      refs.roleSelect.value = state.roleHint;
    } catch (_error) {
      clearSession();
    }
  }

  function clearSession() {
    state.token = "";
    state.roleHint = "observador";
    state.selectedNodeId = null;
    refs.tokenInput.value = "";
    refs.roleSelect.value = "observador";
    window.sessionStorage.removeItem(STORAGE_KEY);
  }

  function setBanner(target, message, isError) {
    target.textContent = message;
    target.classList.remove("hidden");
    target.classList.toggle("is-error", Boolean(isError));
  }

  function clearBanner(target) {
    target.textContent = "";
    target.classList.add("hidden");
    target.classList.remove("is-error");
  }

  function roleAtLeast(currentRole, requiredRole) {
    return ROLE_ORDER.indexOf(currentRole) >= ROLE_ORDER.indexOf(requiredRole);
  }

  function card(label, value, secondary) {
    return `
      <article class="summary-card">
        <h3>${escapeHtml(label)}</h3>
        <strong>${escapeHtml(stringifyValue(value))}</strong>
        <span>${escapeHtml(stringifyValue(secondary))}</span>
      </article>
    `;
  }

  function stringifyValue(value) {
    if (value === null || value === undefined || value === "") {
      return "n/a";
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    return String(value);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }
})();
