/* Cascading year -> meeting -> session picker for the F1Scope landing page.
 * Talks only to the internal API (/api/meetings, /api/sessions) added in
 * issue #10 — never calls OpenF1 directly from the browser. Restyled with
 * the cyberpunk/HUD theme in milestone E7; this is the functional layer. */
(function () {
  "use strict";

  const FIRST_SEASON = 2023; // OpenF1's free tier only has data from 2023 onwards

  const yearSelect = document.getElementById("year-select");
  const meetingSelect = document.getElementById("meeting-select");
  const sessionSelect = document.getElementById("session-select");
  const summary = document.getElementById("session-summary");

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

  async function onYearChange() {
    clearSummary();
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
  }

  function updateUrl(sessionKey) {
    const url = new URL(window.location.href);
    if (sessionKey) {
      url.searchParams.set("session_key", sessionKey);
    } else {
      url.searchParams.delete("session_key");
    }
    window.history.replaceState({}, "", url);
  }

  yearSelect.addEventListener("change", onYearChange);
  meetingSelect.addEventListener("change", onMeetingChange);
  sessionSelect.addEventListener("change", onSessionChange);

  populateYears();
})();
