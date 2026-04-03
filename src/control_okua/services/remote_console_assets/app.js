(function () {
  "use strict";

  const POLL_SUMMARY_MS = 4000;
  const POLL_DETAIL_MS = 3000;

  const state = {
    session: null,
    bootstrapRequired: false,
    selectedNodeId: null,
    nodes: [],
    summaryTimer: null,
    detailTimer: null,
    isBusy: false,
  };

  const refs = {
    loginForm: document.getElementById("login-form"),
    loginUsername: document.getElementById("login-username"),
    loginPassword: document.getElementById("login-password"),
    bootstrapPanel: document.getElementById("bootstrap-panel"),
    bootstrapForm: document.getElementById("bootstrap-form"),
    bootstrapAdminUsername: document.getElementById("bootstrap-admin-username"),
    bootstrapAdminPassword: document.getElementById("bootstrap-admin-password"),
    bootstrapTechUsername: document.getElementById("bootstrap-tech-username"),
    bootstrapTechPassword: document.getElementById("bootstrap-tech-password"),
    bootstrapObserverUsername: document.getElementById("bootstrap-observer-username"),
    bootstrapObserverPassword: document.getElementById("bootstrap-observer-password"),
    authMessage: document.getElementById("auth-message"),
    accessSummary: document.getElementById("access-summary"),
    currentUserChip: document.getElementById("current-user-chip"),
    currentRoleChip: document.getElementById("current-role-chip"),
    logoutButton: document.getElementById("logout-button"),
    refreshAllButton: document.getElementById("refresh-all-button"),
    globalMessage: document.getElementById("global-message"),
    summaryGrid: document.getElementById("summary-grid"),
    operationalMap: document.getElementById("operational-map"),
    mapEmpty: document.getElementById("map-empty"),
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
    usersPanel: document.getElementById("users-panel"),
    usersMessage: document.getElementById("users-message"),
    usersList: document.getElementById("users-list"),
    usersEmpty: document.getElementById("users-empty"),
    createUserForm: document.getElementById("create-user-form"),
    createUsername: document.getElementById("create-username"),
    createPassword: document.getElementById("create-password"),
    createRole: document.getElementById("create-role"),
    createNotes: document.getElementById("create-notes"),
    createEnabled: document.getElementById("create-enabled"),
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopPolling();
      return;
    }
    if (isAuthenticated()) {
      startPolling();
      void refreshAll();
    }
  });

  refs.loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void handleLogin();
  });

  refs.bootstrapForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void handleBootstrap();
  });

  refs.logoutButton.addEventListener("click", () => {
    void handleLogout();
  });

  refs.refreshAllButton.addEventListener("click", () => {
    void refreshAll();
  });

  refs.requestStatButton.addEventListener("click", () => {
    if (state.selectedNodeId !== null) {
      void invokeNodeAction("request-stat-now");
    }
  });

  refs.rebootButton.addEventListener("click", () => {
    if (state.selectedNodeId !== null) {
      void invokeNodeAction("reboot", { delay_ms: 0 });
    }
  });

  refs.createUserForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void handleCreateUser();
  });

  refs.usersList.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement)) {
      return;
    }
    const card = target.closest("[data-username]");
    if (!(card instanceof HTMLElement)) {
      return;
    }
    const username = card.dataset.username || "";
    if (!username) {
      return;
    }
    if (target.dataset.action === "save-profile") {
      void handleSaveUser(card, username);
      return;
    }
    if (target.dataset.action === "change-password") {
      void handleChangePassword(card, username);
      return;
    }
    if (target.dataset.action === "delete-user") {
      void handleDeleteUser(username);
    }
  });

  void syncSessionState();

  async function syncSessionState() {
    try {
      const response = await apiRequest("/api/v1/auth/session", { authOptional: true });
      const data = response.data || {};
      state.bootstrapRequired = Boolean(data.bootstrap_required);
      state.session = data.authenticated ? data.user : null;
      syncAccessUi(data);
      if (state.session) {
        startPolling();
        await refreshAll();
      } else {
        stopPolling();
        renderLoggedOutState();
      }
    } catch (error) {
      stopPolling();
      state.session = null;
      state.bootstrapRequired = false;
      syncAccessUi({});
      renderLoggedOutState();
      setBanner(refs.authMessage, describeError(error), true);
    }
  }

  async function handleLogin() {
    const username = refs.loginUsername.value.trim();
    const password = refs.loginPassword.value;
    if (!username || !password) {
      setBanner(refs.authMessage, "Ingresa usuario y contraseña.", true);
      return;
    }
    try {
      const response = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: { username, password },
        authOptional: true,
      });
      refs.loginPassword.value = "";
      state.session = response.data?.user || null;
      state.bootstrapRequired = false;
      clearBanner(refs.authMessage);
      syncAccessUi(response.data || {});
      startPolling();
      await refreshAll();
    } catch (error) {
      refs.loginPassword.value = "";
      setBanner(refs.authMessage, describeError(error), true);
    }
  }

  async function handleBootstrap() {
    const accounts = [
      {
        username: refs.bootstrapAdminUsername.value.trim(),
        password: refs.bootstrapAdminPassword.value,
        role: "admin",
      },
      {
        username: refs.bootstrapTechUsername.value.trim(),
        password: refs.bootstrapTechPassword.value,
        role: "tecnico",
      },
      {
        username: refs.bootstrapObserverUsername.value.trim(),
        password: refs.bootstrapObserverPassword.value,
        role: "observador",
      },
    ];
    try {
      const response = await apiRequest("/api/v1/auth/bootstrap", {
        method: "POST",
        body: { accounts },
        authOptional: true,
      });
      refs.bootstrapAdminPassword.value = "";
      refs.bootstrapTechPassword.value = "";
      refs.bootstrapObserverPassword.value = "";
      state.session = response.data?.user || null;
      state.bootstrapRequired = false;
      setBanner(refs.authMessage, "Bootstrap inicial completado. Sesión admin activa.", false);
      syncAccessUi(response.data || {});
      startPolling();
      await refreshAll();
    } catch (error) {
      refs.bootstrapAdminPassword.value = "";
      refs.bootstrapTechPassword.value = "";
      refs.bootstrapObserverPassword.value = "";
      setBanner(refs.authMessage, describeError(error), true);
    }
  }

  async function handleLogout() {
    try {
      await apiRequest("/api/v1/auth/logout", {
        method: "POST",
        authOptional: true,
      });
    } catch (_error) {
      // Logout debe limpiar UI aunque la sesión ya no exista.
    } finally {
      state.session = null;
      state.selectedNodeId = null;
      stopPolling();
      clearBanner(refs.globalMessage);
      clearBanner(refs.detailMessage);
      clearBanner(refs.usersMessage);
      void syncSessionState();
    }
  }

  async function refreshAll() {
    if (!isAuthenticated() || state.isBusy) {
      return;
    }
    state.isBusy = true;
    try {
      const [healthResponse, summaryResponse, nodesResponse] = await Promise.all([
        apiRequest("/api/v1/health"),
        apiRequest("/api/v1/runtime/summary"),
        apiRequest("/api/v1/nodes"),
      ]);

      const nodes = Array.isArray(nodesResponse.data?.nodes) ? nodesResponse.data.nodes : [];
      state.nodes = nodes;
      if (
        state.selectedNodeId !== null &&
        !nodes.some((node) => Number(node.node_id) === Number(state.selectedNodeId))
      ) {
        state.selectedNodeId = null;
      }
      renderSummary(healthResponse.data, summaryResponse.data);
      renderOperationalMap(nodes);
      renderNodes(nodes);
      clearBanner(refs.globalMessage);

      if (state.selectedNodeId !== null) {
        await refreshSelectedNode();
      } else {
        refs.nodeDetail.classList.add("hidden");
        refs.detailEmpty.classList.remove("hidden");
        refs.detailEmpty.textContent = "Selecciona un nodo para ver su detalle técnico.";
        syncActionButtons();
      }
      if (state.session?.role === "admin") {
        await loadUsers();
      } else {
        hideUsersPanel();
      }
    } catch (error) {
      handleGlobalError(error);
    } finally {
      state.isBusy = false;
    }
  }

  async function refreshSelectedNode() {
    if (!isAuthenticated() || state.selectedNodeId === null) {
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
    if (!isAuthenticated() || state.selectedNodeId === null) {
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

  async function loadUsers() {
    try {
      const response = await apiRequest("/api/v1/accounts");
      const users = Array.isArray(response.data?.users) ? response.data.users : [];
      renderUsers(users);
      clearBanner(refs.usersMessage);
    } catch (error) {
      hideUsersPanel();
      setBanner(refs.usersMessage, describeError(error), true);
    }
  }

  async function handleCreateUser() {
    try {
      await apiRequest("/api/v1/accounts", {
        method: "POST",
        body: {
          username: refs.createUsername.value.trim(),
          password: refs.createPassword.value,
          role: refs.createRole.value,
          notes: refs.createNotes.value.trim(),
          enabled: refs.createEnabled.checked,
        },
      });
      refs.createUserForm.reset();
      refs.createRole.value = "observador";
      refs.createEnabled.checked = true;
      setBanner(refs.usersMessage, "Usuario remoto creado.", false);
      await syncSessionState();
    } catch (error) {
      setBanner(refs.usersMessage, describeError(error), true);
    }
  }

  async function handleSaveUser(card, username) {
    const usernameInput = card.querySelector("[data-field='username']");
    const roleSelect = card.querySelector("[data-field='role']");
    const enabledInput = card.querySelector("[data-field='enabled']");
    const notesInput = card.querySelector("[data-field='notes']");
    try {
      await apiRequest(`/api/v1/accounts/${encodeURIComponent(username)}`, {
        method: "PATCH",
        body: {
          username: usernameInput ? usernameInput.value.trim() : username,
          role: roleSelect ? roleSelect.value : "observador",
          enabled: enabledInput ? enabledInput.checked : true,
          notes: notesInput ? notesInput.value.trim() : "",
        },
      });
      setBanner(refs.usersMessage, `Usuario ${username} actualizado.`, false);
      await syncSessionState();
    } catch (error) {
      setBanner(refs.usersMessage, describeError(error), true);
    }
  }

  async function handleChangePassword(card, username) {
    const passwordInput = card.querySelector("[data-field='new-password']");
    const newPassword = passwordInput ? passwordInput.value : "";
    if (!newPassword) {
      setBanner(refs.usersMessage, "Ingresa una nueva contraseña antes de guardar.", true);
      return;
    }
    try {
      await apiRequest(`/api/v1/accounts/${encodeURIComponent(username)}/password`, {
        method: "POST",
        body: { new_password: newPassword },
      });
      if (passwordInput) {
        passwordInput.value = "";
      }
      setBanner(refs.usersMessage, `Contraseña actualizada para ${username}.`, false);
      await syncSessionState();
    } catch (error) {
      setBanner(refs.usersMessage, describeError(error), true);
    }
  }

  async function handleDeleteUser(username) {
    if (!window.confirm(`¿Borrar usuario remoto ${username}?`)) {
      return;
    }
    try {
      await apiRequest(`/api/v1/accounts/${encodeURIComponent(username)}`, {
        method: "DELETE",
      });
      setBanner(refs.usersMessage, `Usuario ${username} borrado.`, false);
      await syncSessionState();
    } catch (error) {
      setBanner(refs.usersMessage, describeError(error), true);
    }
  }

  async function apiRequest(path, options = {}) {
    const headers = {
      Accept: "application/json",
    };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    let response;
    try {
      response = await fetch(path, {
        method: options.method || "GET",
        headers,
        credentials: "same-origin",
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
      if (response.status === 401 && !options.authOptional) {
        state.session = null;
        stopPolling();
        syncAccessUi({});
      }
      throw {
        kind: "http",
        status: response.status,
        payload,
      };
    }

    return payload;
  }

  function syncAccessUi(sessionData) {
    const sessionUser = state.session;
    const bootstrapRequired = Boolean(state.bootstrapRequired || sessionData.bootstrap_required);
    refs.bootstrapPanel.classList.toggle("hidden", !bootstrapRequired);
    refs.loginForm.classList.toggle("hidden", bootstrapRequired || Boolean(sessionUser));
    refs.logoutButton.disabled = !sessionUser;
    refs.refreshAllButton.disabled = !sessionUser;
    refs.currentUserChip.textContent = sessionUser
      ? `Usuario: ${sessionUser.username || "n/a"}`
      : "No autenticado";
    refs.currentRoleChip.textContent = sessionUser
      ? `Rol: ${sessionUser.role || "n/a"}`
      : "Rol: n/a";

    if (bootstrapRequired) {
      refs.accessSummary.classList.remove("hidden");
      refs.accessSummary.textContent =
        "Bootstrap pendiente: crea las cuentas iniciales del sitio para habilitar el acceso remoto.";
    } else if (sessionUser) {
      refs.accessSummary.classList.remove("hidden");
      refs.accessSummary.textContent =
        `Sesión activa vía ${sessionData.auth_scheme || "session_cookie"} para ${sessionUser.username}.`;
    } else {
      refs.accessSummary.classList.add("hidden");
      refs.accessSummary.textContent = "";
    }
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
      refs.nodesEmpty.textContent = isAuthenticated()
        ? "No hay nodos visibles en el runtime actual."
        : "Inicia sesión para consultar la lista de nodos remotos.";
      refs.nodesEmpty.classList.remove("hidden");
      refs.nodesList.innerHTML = "";
      return;
    }

    refs.nodesEmpty.classList.add("hidden");
    refs.nodesList.innerHTML = nodes
      .map((node) => {
        const isSelected = state.selectedNodeId === node.node_id;
        const actionLabel = isSelected ? "Detalle abierto" : "Ver detalle";
        const statusClass = `status-${normalizeNodeStatus(node.status)}`;
        return `
          <article class="node-card ${isSelected ? "is-selected" : ""}">
            <header>
              <div>
                <div class="node-title">${escapeHtml(node.label || `Nodo ${node.node_id}`)}</div>
                <div class="fine-print">node_id ${escapeHtml(String(node.node_id))} · ${escapeHtml(node.box_label || "sin caja")}</div>
              </div>
              <span class="node-status ${statusClass}">${escapeHtml(node.status || "unknown")}</span>
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
        if (Number.isFinite(nodeId)) {
          selectNode(nodeId);
        }
      });
    });
  }

  function renderOperationalMap(nodes) {
    if (!Array.isArray(nodes) || nodes.length === 0) {
      refs.mapEmpty.textContent = isAuthenticated()
        ? "No hay nodos visibles para dibujar el mapa operativo."
        : "Inicia sesión para ver el mapa operativo del runtime actual.";
      refs.mapEmpty.classList.remove("hidden");
      refs.operationalMap.innerHTML = "";
      return;
    }

    const groupedBoxes = groupNodesByBox(nodes);
    refs.mapEmpty.classList.add("hidden");
    refs.operationalMap.innerHTML = groupedBoxes
      .map((group) => {
        const counts = summarizeStatuses(group.nodes);
        const countSummary = [
          `${group.nodes.length} nodo${group.nodes.length === 1 ? "" : "s"}`,
          `online ${counts.online}`,
          `degraded ${counts.degraded}`,
          `offline ${counts.offline}`,
          `calibrating ${counts.calibrating}`,
        ].join(" · ");
        const nodeItems = group.nodes
          .map((node) => {
            const isSelected = Number(state.selectedNodeId) === Number(node.node_id);
            const normalizedStatus = normalizeNodeStatus(node.status);
            return `
              <button
                class="map-node status-${normalizedStatus} ${isSelected ? "is-selected" : ""}"
                type="button"
                data-node-id="${escapeHtml(String(node.node_id))}"
              >
                <span class="map-node-topline">
                  <span class="map-node-label">${escapeHtml(node.label || `Nodo ${node.node_id}`)}</span>
                  <span class="map-node-state">${escapeHtml(node.status || "unknown")}</span>
                </span>
                <span class="map-node-meta">
                  node_id ${escapeHtml(String(node.node_id))} · ${escapeHtml(node.health_summary || "Sin health_summary")}
                </span>
              </button>
            `;
          })
          .join("");

        return `
          <article class="map-box">
            <header class="map-box-header">
              <div>
                <h3>${escapeHtml(group.boxLabel)}</h3>
                <p>${escapeHtml(countSummary)}</p>
              </div>
            </header>
            <div class="map-box-nodes">
              ${nodeItems}
            </div>
          </article>
        `;
      })
      .join("");

    refs.operationalMap.querySelectorAll("button[data-node-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const nodeId = Number(button.getAttribute("data-node-id"));
        if (Number.isFinite(nodeId)) {
          selectNode(nodeId);
        }
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

  function selectNode(nodeId) {
    state.selectedNodeId = Number(nodeId);
    refs.detailEmpty.classList.add("hidden");
    renderOperationalMap(state.nodes);
    renderNodes(state.nodes);
    void refreshSelectedNode();
  }

  function renderUsers(users) {
    if (!isAuthenticated() || state.session?.role !== "admin") {
      hideUsersPanel();
      return;
    }

    refs.usersPanel.classList.remove("hidden");
    if (!Array.isArray(users) || users.length === 0) {
      refs.usersEmpty.classList.remove("hidden");
      refs.usersList.innerHTML = "";
      return;
    }

    refs.usersEmpty.classList.add("hidden");
    refs.usersList.innerHTML = users
      .map((user) => {
        const isCurrent = state.session?.username === user.username;
        return `
          <article class="user-card" data-username="${escapeHtml(user.username)}">
            <header>
              <div>
                <strong>${escapeHtml(user.username)}</strong>
                <div class="user-meta">
                  <span>rol actual: ${escapeHtml(user.role)}</span>
                  <span>último cambio password: ${escapeHtml(stringifyValue(user.last_password_change_at))}</span>
                </div>
              </div>
              <span class="user-status">${isCurrent ? "sesión actual" : user.enabled ? "habilitado" : "deshabilitado"}</span>
            </header>

            <div class="user-grid">
              <label class="field">
                <span>Username</span>
                <input data-field="username" type="text" value="${escapeHtml(user.username)}" />
              </label>
              <label class="field">
                <span>Rol</span>
                <select data-field="role">
                  ${roleOption(user.role, "observador")}
                  ${roleOption(user.role, "tecnico")}
                  ${roleOption(user.role, "admin")}
                </select>
              </label>
              <label class="field">
                <span>Notas</span>
                <input data-field="notes" type="text" value="${escapeHtml(user.notes || "")}" />
              </label>
              <label class="field checkbox-field">
                <input data-field="enabled" type="checkbox" ${user.enabled ? "checked" : ""} />
                <span>Cuenta habilitada</span>
              </label>
              <label class="field">
                <span>Nueva contraseña</span>
                <input data-field="new-password" type="password" autocomplete="new-password" />
              </label>
            </div>

            <div class="button-row">
              <button class="button" type="button" data-action="save-profile">Guardar perfil</button>
              <button class="button button-secondary" type="button" data-action="change-password">Cambiar contraseña</button>
              <button class="button button-danger" type="button" data-action="delete-user">Borrar</button>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function hideUsersPanel() {
    refs.usersPanel.classList.add("hidden");
    refs.usersList.innerHTML = "";
    refs.usersEmpty.classList.add("hidden");
  }

  function syncActionButtons() {
    const role = state.session?.role || "";
    const canRequestStat = role === "tecnico" || role === "admin";
    const canReboot = role === "admin";
    refs.requestStatButton.disabled = !canRequestStat || state.selectedNodeId === null;
    refs.rebootButton.disabled = !canReboot || state.selectedNodeId === null;

    if (!isAuthenticated()) {
      refs.actionHint.textContent = "Inicia sesión para habilitar acciones remotas.";
      return;
    }
    if (role === "observador") {
      refs.actionHint.textContent = "Rol observador: solo lectura.";
      return;
    }
    if (role === "tecnico") {
      refs.actionHint.textContent = "Rol tecnico: REQUEST_STAT_NOW habilitado; REBOOT_SOFT sigue reservado para admin.";
      return;
    }
    refs.actionHint.textContent = "Rol admin: ambas acciones curadas están disponibles, sujetas a las precondiciones reales del runtime.";
  }

  function startPolling() {
    stopPolling();
    if (!isAuthenticated()) {
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
      void syncSessionState();
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

  function renderLoggedOutState() {
    refs.summaryGrid.innerHTML = "";
    refs.operationalMap.innerHTML = "";
    refs.nodesList.innerHTML = "";
    refs.nodeDetail.classList.add("hidden");
    refs.detailEmpty.classList.remove("hidden");
    refs.detailEmpty.textContent = "Selecciona un nodo para ver su detalle técnico.";
    refs.mapEmpty.classList.remove("hidden");
    refs.mapEmpty.textContent = "Inicia sesión para ver el mapa operativo del runtime actual.";
    refs.nodesEmpty.classList.remove("hidden");
    refs.nodesEmpty.textContent = "Inicia sesión para consultar la lista de nodos remotos.";
    hideUsersPanel();
    syncActionButtons();
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
      return `401 unauthorized: ${message || "credenciales inválidas o sesión expirada."}`;
    }
    if (status === 403) {
      return `403 forbidden: ${message || "acción no permitida para este rol."}`;
    }
    if (status === 404) {
      return `404 ${code || "not_found"}: ${message || "recurso no encontrado."}`;
    }
    if (status === 409) {
      return `409 ${code || "conflict"}: ${message || "el runtime no está en condición accionable."}`;
    }
    if (status === 502) {
      return `502 ${code || "command_failed"}: la transacción remota fue intentada y falló.`;
    }
    return `${status || "error"} ${code || "internal_error"}: ${message || "fallo no controlado."}`;
  }

  function card(title, value, detail) {
    return `
      <article class="summary-card">
        <h3>${escapeHtml(title)}</h3>
        <strong>${escapeHtml(stringifyValue(value))}</strong>
        <span>${escapeHtml(detail || "")}</span>
      </article>
    `;
  }

  function renderDefinitionList(values) {
    return Object.entries(values)
      .map(([key, value]) => {
        return `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(stringifyValue(value))}</dd>`;
      })
      .join("");
  }

  function roleOption(currentRole, optionRole) {
    const selected = currentRole === optionRole ? "selected" : "";
    return `<option value="${optionRole}" ${selected}>${optionRole}</option>`;
  }

  function setBanner(element, text, isError) {
    element.textContent = text;
    element.classList.remove("hidden");
    element.classList.toggle("is-error", Boolean(isError));
  }

  function clearBanner(element) {
    element.textContent = "";
    element.classList.add("hidden");
    element.classList.remove("is-error");
  }

  function stringifyValue(value) {
    if (value === null || value === undefined || value === "") {
      return "n/a";
    }
    return String(value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function isAuthenticated() {
    return Boolean(state.session && state.session.username && state.session.role);
  }

  function groupNodesByBox(nodes) {
    const groups = new Map();
    nodes.forEach((node) => {
      const boxLabel = normalizeBoxLabel(node.box_label);
      const existing = groups.get(boxLabel);
      if (existing) {
        existing.push(node);
        return;
      }
      groups.set(boxLabel, [node]);
    });
    return Array.from(groups.entries())
      .sort((left, right) => left[0].localeCompare(right[0], "es"))
      .map(([boxLabel, groupedNodes]) => ({
        boxLabel,
        nodes: groupedNodes.slice().sort(compareNodeSummary),
      }));
  }

  function summarizeStatuses(nodes) {
    return nodes.reduce(
      (acc, node) => {
        const key = normalizeNodeStatus(node.status);
        if (Object.prototype.hasOwnProperty.call(acc, key)) {
          acc[key] += 1;
        } else {
          acc.unknown += 1;
        }
        return acc;
      },
      { online: 0, calibrating: 0, degraded: 0, offline: 0, unknown: 0 }
    );
  }

  function compareNodeSummary(left, right) {
    return Number(left.node_id || 0) - Number(right.node_id || 0);
  }

  function normalizeBoxLabel(rawValue) {
    if (typeof rawValue === "string" && rawValue.trim()) {
      return rawValue.trim();
    }
    return "Sin caja asignada";
  }

  function normalizeNodeStatus(rawStatus) {
    const normalized = typeof rawStatus === "string" ? rawStatus.trim().toLowerCase() : "";
    if (normalized === "online") {
      return "online";
    }
    if (normalized === "calibrating") {
      return "calibrating";
    }
    if (normalized === "degraded") {
      return "degraded";
    }
    if (normalized === "offline") {
      return "offline";
    }
    return "unknown";
  }
})();
