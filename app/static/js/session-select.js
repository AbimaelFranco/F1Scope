/* Cascading year -> meeting -> session picker for the F1Scope landing page.
 * Talks only to the internal API (/api/meetings, /api/sessions) added in
 * issue #10 — never calls OpenF1 directly from the browser. Restyled with
 * the cyberpunk/HUD theme in milestone E7; this is the functional layer. */
(function () {
  "use strict";

  const FIRST_SEASON = 2023; // OpenF1's free tier only has data from 2023 onwards

  const MAX_COMPARED_DRIVERS = 2; // v1 scope (docs/PLANNING.md): compare exactly two drivers

  const yearSelect = document.getElementById("year-select");
  const meetingSelect = document.getElementById("meeting-select");
  const sessionSelect = document.getElementById("session-select");
  const summary = document.getElementById("session-summary");
  const driverPicker = document.getElementById("driver-picker");
  const driverPickerHint = document.getElementById("driver-picker-hint");
  const driverList = document.getElementById("driver-list");

  const selectedDrivers = new Set();

  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request to ${url} failed: ${response.status}`);
    }
    return response.json();
  }

  function resetSelect(select, placeholder, { enabled = false } = {}) {
    select.innerHTML = "";
    const option = document.createElement("option");
    option.value = "";
    option.textContent = placeholder;
    select.appendChild(option);
    select.disabled = !enabled;
  }

  function populateYears() {
    const currentYear = new Date().getFullYear();
    resetSelect(yearSelect, "Selecciona un año", { enabled: true });
    for (let year = currentYear; year >= FIRST_SEASON; year--) {
      const option = document.createElement("option");
      option.value = String(year);
      option.textContent = String(year);
      yearSelect.appendChild(option);
    }
  }

  function clearSummary() {
    summary.hidden = true;
    summary.innerHTML = "";
  }

  function clearDriverPicker() {
    driverPicker.hidden = true;
    driverList.innerHTML = "";
    selectedDrivers.clear();
  }

  async function onYearChange() {
    clearSummary();
    clearDriverPicker();
    resetSelect(sessionSelect, "Selecciona un Gran Premio primero");

    const year = yearSelect.value;
    if (!year) {
      resetSelect(meetingSelect, "Selecciona un año primero");
      return;
    }

    resetSelect(meetingSelect, "Cargando...");
    try {
      const meetings = await fetchJSON(`/api/meetings?year=${encodeURIComponent(year)}`);
      const placeholder = meetings.length ? "Selecciona un Gran Premio" : "Sin datos para este año";
      resetSelect(meetingSelect, placeholder, { enabled: meetings.length > 0 });
      for (const meeting of meetings) {
        const option = document.createElement("option");
        option.value = meeting.meeting_key;
        option.textContent = `${meeting.meeting_name} (${meeting.country_name})`;
        meetingSelect.appendChild(option);
      }
    } catch (err) {
      resetSelect(meetingSelect, "Error al cargar Grandes Premios");
      console.error("F1Scope: failed to load meetings", err);
    }
  }

  async function onMeetingChange() {
    clearSummary();
    clearDriverPicker();

    const meetingKey = meetingSelect.value;
    if (!meetingKey) {
      resetSelect(sessionSelect, "Selecciona un Gran Premio primero");
      return;
    }

    resetSelect(sessionSelect, "Cargando...");
    try {
      const sessions = await fetchJSON(`/api/sessions?meeting_key=${encodeURIComponent(meetingKey)}`);
      const placeholder = sessions.length ? "Selecciona una sesión" : "Sin sesiones para este Gran Premio";
      resetSelect(sessionSelect, placeholder, { enabled: sessions.length > 0 });
      for (const session of sessions) {
        const option = document.createElement("option");
        option.value = session.session_key;
        option.textContent = `${session.session_name} (${session.session_type})`;
        option.dataset.session = JSON.stringify(session);
        sessionSelect.appendChild(option);
      }
    } catch (err) {
      resetSelect(sessionSelect, "Error al cargar sesiones");
      console.error("F1Scope: failed to load sessions", err);
    }
  }

  function onSessionChange() {
    const option = sessionSelect.selectedOptions[0];
    if (!option || !option.value) {
      clearSummary();
      clearDriverPicker();
      updateUrl(null);
      return;
    }

    const session = JSON.parse(option.dataset.session);
    const meetingLabel = meetingSelect.selectedOptions[0]
      ? meetingSelect.selectedOptions[0].textContent
      : "";

    summary.hidden = false;
    summary.innerHTML = `
      <h2>${session.session_name}</h2>
      <p>${meetingLabel} — ${session.session_type}</p>
      <p>${new Date(session.date_start).toLocaleString()}</p>
      <p class="session-key">session_key: ${session.session_key}</p>
    `;
    updateUrl(session.session_key);
    loadDrivers(session.session_key);
  }

  async function loadDrivers(sessionKey) {
    clearDriverPicker();
    driverPicker.hidden = false;
    driverPickerHint.textContent = "Cargando pilotos...";

    try {
      const drivers = await fetchJSON(`/api/drivers?session_key=${encodeURIComponent(sessionKey)}`);
      if (!drivers.length) {
        driverPickerHint.textContent = "Sin pilotos registrados para esta sesión.";
        return;
      }
      for (const driver of drivers) {
        driverList.appendChild(renderDriverOption(driver));
      }
      updateDriverPickerHint();
    } catch (err) {
      driverPickerHint.textContent = "Error al cargar pilotos.";
      console.error("F1Scope: failed to load drivers", err);
    }
  }

  function renderDriverOption(driver) {
    const label = document.createElement("label");
    label.className = "driver-option";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = String(driver.driver_number);
    checkbox.addEventListener("change", onDriverToggle);

    const swatch = document.createElement("span");
    swatch.className = "driver-swatch";
    swatch.style.backgroundColor = `#${driver.team_colour || "888888"}`;

    const text = document.createElement("span");
    text.className = "driver-name";
    text.textContent = `${driver.name_acronym} — ${driver.full_name} (${driver.team_name})`;

    label.append(checkbox, swatch, text);
    return label;
  }

  function onDriverToggle(event) {
    const driverNumber = event.target.value;
    if (event.target.checked) {
      selectedDrivers.add(driverNumber);
    } else {
      selectedDrivers.delete(driverNumber);
    }

    const atLimit = selectedDrivers.size >= MAX_COMPARED_DRIVERS;
    for (const checkbox of driverList.querySelectorAll("input[type=checkbox]")) {
      checkbox.disabled = atLimit && !checkbox.checked;
    }

    updateDriverPickerHint();
    updateUrl(sessionSelect.value, [...selectedDrivers]);
  }

  function updateDriverPickerHint() {
    const remaining = MAX_COMPARED_DRIVERS - selectedDrivers.size;
    driverPickerHint.textContent =
      remaining > 0
        ? `Selecciona ${remaining} piloto${remaining === 1 ? "" : "s"} más para comparar.`
        : "2 pilotos seleccionados.";
  }

  function updateUrl(sessionKey, driverNumbers) {
    const url = new URL(window.location.href);
    if (sessionKey) {
      url.searchParams.set("session_key", sessionKey);
    } else {
      url.searchParams.delete("session_key");
    }
    if (driverNumbers && driverNumbers.length) {
      url.searchParams.set("drivers", driverNumbers.join(","));
    } else {
      url.searchParams.delete("drivers");
    }
    window.history.replaceState({}, "", url);
  }

  yearSelect.addEventListener("change", onYearChange);
  meetingSelect.addEventListener("change", onMeetingChange);
  sessionSelect.addEventListener("change", onSessionChange);

  populateYears();
})();
