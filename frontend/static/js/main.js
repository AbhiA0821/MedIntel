// ============================================================
// MEDINTEL — Core Client Controller (Vanilla JavaScript)
// Stage 1 Design System & Shell + Stage 3 Receptionist Command Center
// ============================================================

let allPatients = [];
let activeAlertsList = [];
let simulatorRunning = false;
let updateIntervalSec = 3;
let pollTimer = null;
let currentSelectedPatient = null;
let latestDbTimestampDate = null;
let lastKnownCriticalIds = new Set();
let isInitialCriticalLoad = true;

// Active UI Filter State
let currentSeverityFilter = 'All Severity';
let currentWardFilter = 'All Wards';
let currentSearchQuery = '';
let currentSortBy = 'severity';
let searchDebounceTimer = null;

// ============================================================
// 1. SERIALIZED VOICE ALERT QUEUE MANAGER (PRESERVED)
// ============================================================
class VoiceAlertQueue {
  constructor(destination, onQueueUpdate) {
    this.destination = destination || 'RECEPTIONIST';
    this.onQueueUpdate = onQueueUpdate;
    this.enabled = true;
    this.queue = [];
    this.currentlySpeaking = null;
    this.lastSpoken = null;
    this.isPlaying = false;
    this.isPolling = false;
    this.audioPlayer = new Audio();
    this.playedIds = new Set();
    this.audioUnlocked = false;

    this._bindAudioUnlock();
  }

  _bindAudioUnlock() {
    const unlock = () => {
      this.unlockManually();
    };
    ['click', 'touchstart', 'keydown', 'pointerdown'].forEach(evt => {
      document.addEventListener(evt, unlock, { once: true, passive: true });
    });
  }

  unlockManually() {
    if (this.audioUnlocked) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        const ctx = new AudioCtx();
        if (ctx.state === 'suspended') ctx.resume();
      }
      const dummy = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
      dummy.play().catch(() => {});
    } catch(e) {}
    this.audioUnlocked = true;
    console.log('[VOICE QUEUE] Audio autoplay unlocked.');
    if (this.onQueueUpdate) this.onQueueUpdate(this.getState());
    if (!this.isPlaying && this.queue.length > 0) {
      this.playNext();
    }
  }

  toggle() {
    this.unlockManually();
    this.enabled = !this.enabled;
    if (this.enabled && !this.isPlaying && this.queue.length > 0) {
      this.playNext();
    }
    if (this.onQueueUpdate) this.onQueueUpdate(this.getState());
    return this.enabled;
  }

  getState() {
    return {
      enabled: this.enabled,
      currentlySpeaking: this.currentlySpeaking,
      queued: [...this.queue],
      lastSpoken: this.lastSpoken,
      pendingCount: this.queue.length,
      audioUnlocked: this.audioUnlocked
    };
  }

  async poll() {
    if (!this.enabled || this.isPolling) return;
    this.isPolling = true;
    try {
      const destParam = encodeURIComponent(this.destination);
      const res = await fetch(`/api/v1/alerts/voice/queue?destination=${destParam}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.status !== 'SUCCESS') return;

      const serverQueued = data.queued || [];
      if (!this.lastSpoken && data.last_spoken) {
        this.lastSpoken = data.last_spoken;
      }

      for (const alert of serverQueued) {
        if (!this.playedIds.has(alert.alert_id)) {
          const alreadyInQueue = this.queue.some(item => item.alert_id === alert.alert_id);
          const isCurrent = this.currentlySpeaking && this.currentlySpeaking.alert_id === alert.alert_id;
          if (!alreadyInQueue && !isCurrent) {
            this.queue.push(alert);
          }
        }
      }

      if (this.onQueueUpdate) this.onQueueUpdate(this.getState());

      if (!this.isPlaying && this.queue.length > 0) {
        this.playNext();
      }
    } catch (err) {
      console.warn('[VOICE QUEUE] Poll warning:', err);
    } finally {
      this.isPolling = false;
    }
  }

  async playNext() {
    if (!this.enabled || this.queue.length === 0 || this.isPlaying) return;

    this.isPlaying = true;
    const item = this.queue.shift();
    this.currentlySpeaking = item;
    if (this.onQueueUpdate) this.onQueueUpdate(this.getState());

    try {
      if (item.audio_url) {
        this.audioPlayer.src = item.audio_url;
        await this.audioPlayer.play();
        await new Promise(resolve => {
          this.audioPlayer.onended = resolve;
          this.audioPlayer.onerror = resolve;
        });
      } else {
        // Fallback to browser Web Speech API
        await new Promise(resolve => {
          if ('speechSynthesis' in window) {
            const utter = new SpeechSynthesisUtterance(item.spoken_text || 'Critical Patient Alert');
            utter.rate = 1.05;
            utter.pitch = 1.0;
            utter.onend = resolve;
            utter.onerror = resolve;
            window.speechSynthesis.speak(utter);
          } else {
            setTimeout(resolve, 3000);
          }
        });
      }

      this.playedIds.add(item.alert_id);
      this.lastSpoken = item;

      // Acknowledge spoken alert on backend
      try {
        await fetch(`/api/v1/alerts/voice/ack/${encodeURIComponent(item.alert_id)}`, { method: 'POST' });
      } catch (e) {}

    } catch (err) {
      console.warn('[VOICE PLAYBACK] Warning:', err);
    } finally {
      this.currentlySpeaking = null;
      this.isPlaying = false;
      if (this.onQueueUpdate) this.onQueueUpdate(this.getState());

      if (this.queue.length > 0) {
        setTimeout(() => this.playNext(), 400);
      }
    }
  }
}

// ============================================================
// 2. DATA FRESHNESS CHIP (SAFE TIMESTAMP PARSING)
// ============================================================
function parseAuthoritativeTimestamp(tsStr) {
  if (!tsStr) return null;
  const now = new Date();

  // Pattern 1: HH:MM:SS format from SQL MAX(recorded_at)
  const timeMatch = String(tsStr).trim().match(/^(\d{1,2}):(\d{2}):(\d{2})$/);
  if (timeMatch) {
    const d = new Date(now);
    d.setHours(parseInt(timeMatch[1], 10), parseInt(timeMatch[2], 10), parseInt(timeMatch[3], 10), 0);
    // If d is > 60s in the future due to slight client/server skew, clamp to now
    const diff = (now.getTime() - d.getTime()) / 1000;
    if (diff < -30) {
      // Midnight wrap or timezone offset: assume it was previous day
      d.setDate(d.getDate() - 1);
    }
    return d;
  }

  // Pattern 2: ISO string or full datetime
  const isoDate = new Date(tsStr);
  if (!isNaN(isoDate.getTime())) {
    return isoDate;
  }

  return null;
}

function updateFreshnessChip(latestDbUpdateStr) {
  if (latestDbUpdateStr) {
    latestDbTimestampDate = parseAuthoritativeTimestamp(latestDbUpdateStr);
  }

  const chip = document.getElementById('dataFreshnessChip');
  const textEl = document.getElementById('dataFreshnessText');
  if (!chip || !textEl) return;

  if (!latestDbTimestampDate) {
    chip.className = 'status-chip delayed';
    textEl.textContent = 'Syncing...';
    return;
  }

  const now = new Date();
  const ageSeconds = Math.max(0, Math.round((now.getTime() - latestDbTimestampDate.getTime()) / 1000));

  if (ageSeconds <= 60) {
    chip.className = 'status-chip live';
    textEl.textContent = `Live · updated ${ageSeconds}s ago`;
  } else {
    const mins = Math.floor(ageSeconds / 60);
    chip.className = 'status-chip delayed';
    const displayAge = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins} min`;
    textEl.textContent = `Data delayed · ${displayAge}`;
  }

  chip.title = `Authoritative DB update timestamp: ${latestDbUpdateStr || latestDbTimestampDate.toLocaleTimeString()}`;
}

// Real-time ticking interval for freshness chip (runs every second)
setInterval(() => {
  if (latestDbTimestampDate) {
    updateFreshnessChip();
  }
  // Also tick live header clock
  const clockEl = document.getElementById('liveClock');
  if (clockEl) {
    clockEl.textContent = new Date().toLocaleTimeString();
  }
}, 1000);

// ============================================================
// 3. LIVE MONITORING REFRESH & ACTIVE ALERTS FETCH
// ============================================================
async function refreshLiveVitals() {
  try {
    // 1. Fetch live vitals and active alerts in parallel
    const [vitalsRes, alertsRes] = await Promise.all([
      fetch('/api/v1/live_vitals'),
      fetch('/api/v1/alerts/active').catch(() => null)
    ]);

    if (!vitalsRes.ok) throw new Error('Live vitals API failed');
    const data = await vitalsRes.json();
    allPatients = data.patients || [];

    if (alertsRes && alertsRes.ok) {
      const alertData = await alertsRes.json();
      activeAlertsList = alertData.alerts || [];
    }

    // 2. Update KPI values from authoritative server state
    setText('kpiTotalPatients', data.total_patients !== undefined ? data.total_patients : allPatients.length);
    setText('kpiCriticalCount', data.critical_count !== undefined ? data.critical_count : 0);
    setText('kpiModerateCount', data.moderate_count !== undefined ? data.moderate_count : 0);
    setText('kpiLowCount', data.low_count !== undefined ? data.low_count : 0);
    setText('kpiTotalRecords', (data.total_vitals_count !== undefined ? data.total_vitals_count : 0).toLocaleString());

    // Preserved compatibility IDs
    setText('kpiLastUpdate', data.latest_db_update || '--:--:--');
    setText('sidebarLastUpdate', data.latest_db_update || '--:--:--');

    // Update freshness chip safely
    updateFreshnessChip(data.latest_db_update);

    // 3. Render left panel and right panel
    renderPatientTable();
    renderCriticalPanel();

  } catch (err) {
    console.error('[MEDINTEL] Error refreshing live vitals:', err);
    showStaleDataNotice(true);
  }
}

function showStaleDataNotice(show) {
  const container = document.getElementById('patientTableScrollContainer');
  let banner = document.getElementById('staleDataNoticeBanner');
  if (!container) return;

  if (show) {
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'staleDataNoticeBanner';
      banner.className = 'stale-data-banner';
      banner.innerHTML = `
        <span style="display:inline-flex; align-items:center; gap:6px;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          Connection delayed. Showing last known authoritative telemetry.
        </span>
        <button type="button" class="btn-retry" onclick="refreshLiveVitals()">Retry</button>
      `;
      container.parentElement.insertBefore(banner, container);
    }
  } else if (banner) {
    banner.remove();
  }
}

// ============================================================
// 4. LEFT PANEL: ALL ACTIVE PATIENTS (KEYED DIFF/PATCH)
// ============================================================
function onSearchInputDebounced() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    currentSearchQuery = (document.getElementById('searchInput')?.value || '').trim();
    renderPatientTable();
  }, 200);
}

function setSeverityFilter(sev) {
  currentSeverityFilter = sev;
  const select = document.getElementById('severityFilter');
  if (select) select.value = sev;

  // Update chip active states
  ['chipSevAll', 'chipSevCritical', 'chipSevModerate', 'chipSevLow'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active', 'critical', 'moderate', 'low');
  });

  if (sev === 'CRITICAL') {
    const el = document.getElementById('chipSevCritical');
    if (el) el.classList.add('active', 'critical');
  } else if (sev === 'MODERATE') {
    const el = document.getElementById('chipSevModerate');
    if (el) el.classList.add('active', 'moderate');
  } else if (sev === 'LOW') {
    const el = document.getElementById('chipSevLow');
    if (el) el.classList.add('active', 'low');
  } else {
    const el = document.getElementById('chipSevAll');
    if (el) el.classList.add('active');
  }

  // Update KPI card highlight
  updateKpiCardHighlight(sev);

  renderPatientTable();
}

function filterBySeverityCard(sev) {
  if (sev === 'ALL') {
    setSeverityFilter('All Severity');
  } else {
    setSeverityFilter(sev);
  }
}

function updateKpiCardHighlight(sev) {
  ['kpiCardTotal', 'kpiCardCritical', 'kpiCardModerate', 'kpiCardLow'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active-filter');
  });

  if (sev === 'CRITICAL') {
    document.getElementById('kpiCardCritical')?.classList.add('active-filter');
  } else if (sev === 'MODERATE') {
    document.getElementById('kpiCardModerate')?.classList.add('active-filter');
  } else if (sev === 'LOW') {
    document.getElementById('kpiCardLow')?.classList.add('active-filter');
  } else {
    document.getElementById('kpiCardTotal')?.classList.add('active-filter');
  }
}

function resetAllFilters() {
  currentSearchQuery = '';
  currentSeverityFilter = 'All Severity';
  currentWardFilter = 'All Wards';
  currentSortBy = 'severity';

  const sInput = document.getElementById('searchInput');
  if (sInput) sInput.value = '';
  const wSelect = document.getElementById('wardFilter');
  if (wSelect) wSelect.value = 'All Wards';
  const sSelect = document.getElementById('sortSelect');
  if (sSelect) sSelect.value = 'severity';

  setSeverityFilter('All Severity');
}

function renderPatientTable() {
  const tbody = document.getElementById('patientTableBody');
  if (!tbody) return;

  const searchVal = (currentSearchQuery || document.getElementById('searchInput')?.value || '').toLowerCase();
  const wardVal = document.getElementById('wardFilter')?.value || currentWardFilter;
  const sevVal = currentSeverityFilter;
  const sortVal = document.getElementById('sortSelect')?.value || currentSortBy;

  // Filter patients
  let filtered = allPatients.filter(p => {
    const pId = (p.patient_id || '').toLowerCase();
    const pName = (p.name || '').toLowerCase();
    const matchSearch = !searchVal || pId.includes(searchVal) || pName.includes(searchVal);
    const matchWard = wardVal === 'All Wards' || p.ward === wardVal || (p.ward && p.ward.toLowerCase().includes(wardVal.toLowerCase()));
    const matchSev = sevVal === 'All Severity' || (p.severity && p.severity.toUpperCase() === sevVal.toUpperCase());
    return matchSearch && matchWard && matchSev;
  });

  // Sort patients
  filtered.sort((a, b) => {
    if (sortVal === 'name') {
      return (a.name || '').localeCompare(b.name || '');
    } else if (sortVal === 'id') {
      return (a.pid_raw || 0) - (b.pid_raw || 0);
    } else if (sortVal === 'ward') {
      return (a.ward || '').localeCompare(b.ward || '');
    } else if (sortVal === 'updated') {
      return (b.last_update || '').localeCompare(a.last_update || '');
    }
    // Default: Severity order (CRITICAL > MODERATE > LOW)
    const weight = { 'CRITICAL': 3, 'MODERATE': 2, 'LOW': 1 };
    const diff = (weight[b.severity] || 0) - (weight[a.severity] || 0);
    if (diff !== 0) return diff;
    return (a.pid_raw || 0) - (b.pid_raw || 0);
  });

  // Update count indicators
  const totalCount = allPatients.length;
  setText('patientTableCount', totalCount);
  setText('navTotalPatientsBadge', totalCount);

  const statusTextEl = document.getElementById('patientFilterStatus');
  if (statusTextEl) {
    if (filtered.length === totalCount) {
      statusTextEl.textContent = `Showing all ${totalCount} patients`;
    } else {
      statusTextEl.textContent = `Showing ${filtered.length} of ${totalCount}`;
    }
  }

  // Handle empty state
  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="9">
          <div class="empty-state">
            <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            <div class="empty-state-title">No matching patients found</div>
            <div class="empty-state-sub">Adjust your search query or filter selection to view inpatient records.</div>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  // Keyed DOM Diff & Patch: map existing rows by data-pid
  const existingRowsMap = new Map();
  Array.from(tbody.children).forEach(row => {
    const pid = row.getAttribute('data-pid');
    if (pid) existingRowsMap.set(pid, row);
  });

  const activePids = new Set(filtered.map(p => p.patient_id));

  // Remove rows that no longer match the filter
  existingRowsMap.forEach((row, pid) => {
    if (!activePids.has(pid)) {
      row.remove();
      existingRowsMap.delete(pid);
    }
  });

  // Patch existing rows or insert new ones in correct order
  filtered.forEach((p, index) => {
    let row = existingRowsMap.get(p.patient_id);
    const isCritical = p.severity === 'CRITICAL';
    const isModerate = p.severity === 'MODERATE';

    const sevBadge = isCritical
      ? `<span class="badge-severity CRITICAL"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>CRITICAL</span>`
      : isModerate
        ? `<span class="badge-severity MODERATE"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>MODERATE</span>`
        : `<span class="badge-severity LOW"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>LOW RISK</span>`;

    const vitalsStripHtml = `
      <div class="vitals-strip">
        <span class="vital-metric ${p.heart_rate > 120 ? 'danger' : ''}">HR: <strong>${p.heart_rate}</strong></span> •
        <span class="vital-metric ${p.spo2 < 90 ? 'danger' : ''}">SpO₂: <strong>${p.spo2}%</strong></span> •
        <span class="vital-metric">BP: <strong>${p.systolic_bp}/${p.diastolic_bp}</strong></span> •
        <span class="vital-metric ${p.temperature > 38.5 ? 'danger' : ''}">T: <strong>${p.temperature}°</strong></span> •
        <span class="vital-metric">RR: <strong>${p.respiratory_rate}</strong></span>
      </div>
    `;

    const docName = p.assigned_doctor_name || p.assigned_doctor || 'Dr. Shreya Sutar';
    const specialty = p.assigned_doctor_specialty || p.specialty || 'General Medicine';
    const location = `${p.ward} • R:${p.room_no} B:${p.bed_no}`;
    const updateTimeStr = p.last_update || 'Live';

    const rowInnerHtml = `
      <td style="font-weight: 700; color: var(--text);">${escapeHtml(p.name)}</td>
      <td class="font-mono" style="font-weight: 700; color: var(--accent);">${p.patient_id}</td>
      <td style="color: var(--text-muted);">${specialty}</td>
      <td class="font-mono" style="font-size: 10.5px;">${location}</td>
      <td style="font-weight: 600;">${escapeHtml(docName)}</td>
      <td>${sevBadge}</td>
      <td>${vitalsStripHtml}</td>
      <td class="font-mono" style="font-size: 10px; color: var(--text-faint);" title="Authoritative telemetry recorded">${updateTimeStr}</td>
      <td class="row-actions-cell" onclick="event.stopPropagation();">
        <button type="button" class="row-menu-btn" onclick="toggleRowMenu('${p.patient_id}', event)" aria-label="Patient Actions for ${p.patient_id}">⋯</button>
        <div class="row-menu-dropdown" id="rowMenu_${p.patient_id}">
          <button type="button" class="menu-item" onclick="openPatientDrawer('${p.patient_id}'); closeAllRowMenus();">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
            View Details
          </button>
          <button type="button" class="menu-item" onclick="openEditModalForPatient('${p.patient_id}'); closeAllRowMenus();">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
            Edit Record
          </button>
          <button type="button" class="menu-item destructive" onclick="openDischargeModalForPatient('${p.patient_id}'); closeAllRowMenus();">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
            Discharge Patient
          </button>
          <button type="button" class="menu-item destructive" onclick="openDeleteModalForPatient('${p.patient_id}'); closeAllRowMenus();">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            Delete Record
          </button>
        </div>
      </td>
    `;

    if (row) {
      // Patch changed row
      row.className = isCritical ? 'row-critical' : '';
      if (row.innerHTML !== rowInnerHtml) {
        row.innerHTML = rowInnerHtml;
      }
    } else {
      // Create new row
      row = document.createElement('tr');
      row.setAttribute('data-pid', p.patient_id);
      row.className = isCritical ? 'row-critical' : '';
      row.tabIndex = 0;
      row.setAttribute('role', 'button');
      row.setAttribute('aria-label', `View telemetry for ${p.name} (${p.patient_id})`);
      row.innerHTML = rowInnerHtml;
      row.onclick = () => openPatientDrawer(p.patient_id);
      row.onkeydown = (e) => {
        if (e.key === 'Enter') openPatientDrawer(p.patient_id);
      };
      existingRowsMap.set(p.patient_id, row);
    }

    // Ensure correct DOM order
    if (tbody.children[index] !== row) {
      tbody.insertBefore(row, tbody.children[index] || null);
    }
  });

  // Null-guards for hidden pagination controls
  const pageIndicator = document.getElementById('patientTablePageIndicator');
  if (pageIndicator) pageIndicator.textContent = `Page 1 of 1`;
  const pageInfo = document.getElementById('patientTablePaginationInfo');
  if (pageInfo) pageInfo.textContent = `Showing ${filtered.length} patients`;
}

// Row action dropdown handlers
function toggleRowMenu(pid, e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById(`rowMenu_${pid}`);
  if (!menu) return;
  const wasOpen = menu.classList.contains('open');
  closeAllRowMenus();
  if (!wasOpen) {
    menu.classList.add('open');
  }
}

function closeAllRowMenus() {
  document.querySelectorAll('.row-menu-dropdown.open').forEach(m => m.classList.remove('open'));
}

document.addEventListener('click', () => {
  closeAllRowMenus();
});

// Quick action shortcuts from row menu
function openEditModalForPatient(pid) {
  openModal('modalEditPatient');
  const select = document.getElementById('editPatientSelect');
  if (select) {
    select.value = pid;
    if (typeof onEditPatientSelected === 'function') {
      onEditPatientSelected(pid);
    }
  }
}

function openDischargeModalForPatient(pid) {
  const modal = document.getElementById('dischargePatientModal') || document.getElementById('modalDischargePatient');
  if (modal) {
    modal.style.display = 'flex';
  } else {
    openModal('modalDeletePatient');
  }
  const p = (allPatients || []).find(x => String(x.patient_id) === String(pid) || String(x.patient_id) === 'P' + pid);
  const name = p ? p.name : pid;
  setText('dischargeConfirmPidName', `${pid} — ${name}`);
  if (p) {
    setText('dischargeConfirmWard', `${p.ward} • Room ${p.room_no} • Bed ${p.bed_no}`);
  }
  const inp = document.getElementById('dischargePatientIdInput');
  if (inp) inp.value = pid;
  const btn = document.getElementById('btnDischargePatientSubmit');
  if (btn) {
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
  }
}

function openDeleteModalForPatient(pid) {
  openModal('modalDeletePatient');
  const searchInput = document.getElementById('deletePatientSearchInput');
  if (searchInput) {
    searchInput.value = pid;
    if (typeof searchPatientForDelete === 'function') {
      searchPatientForDelete();
    }
  }
}

// ============================================================
// 5. RIGHT PANEL: CRITICAL PATIENTS PERMANENT FEED (UNCAPPED)
// ============================================================
function renderCriticalPanel() {
  const container = document.getElementById('criticalPatientsList');
  if (!container) return;

  // Authoritative critical patients from ALL patients dataset (UNCAPPED)
  const criticals = allPatients.filter(p => p.severity === 'CRITICAL');
  setText('criticalHeaderCount', criticals.length);

  if (criticals.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding: 30px 16px;">
        <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
        <div class="empty-state-title" style="color: var(--low);">No Critical Patients</div>
        <div class="empty-state-sub">All monitored patient vitals are within stable baseline thresholds.</div>
      </div>
    `;
    lastKnownCriticalIds.clear();
    return;
  }

  // Cross-reference with /api/v1/alerts/active for trigger condition and lifecycle status
  const alertMap = new Map();
  activeAlertsList.forEach(a => {
    const rawPid = a.patient_id ? String(a.patient_id).replace(/^P/, '') : null;
    if (rawPid) alertMap.set(rawPid, a);
    if (a.patient_id) alertMap.set(String(a.patient_id), a);
  });

  // Sort convention:
  // 1. Unacknowledged alerts first
  // 2. Alert timestamp descending (most recent alert first)
  // 3. Patient ID ascending
  criticals.sort((a, b) => {
    const alertA = alertMap.get(String(a.pid_raw)) || alertMap.get(a.patient_id);
    const alertB = alertMap.get(String(b.pid_raw)) || alertMap.get(b.patient_id);

    const ackA = alertA ? alertA.acknowledged : true;
    const ackB = alertB ? alertB.acknowledged : true;

    if (ackA !== ackB) {
      return ackA ? 1 : -1; // unacknowledged first
    }

    const timeA = alertA && alertA.created_at ? new Date(alertA.created_at).getTime() : 0;
    const timeB = alertB && alertB.created_at ? new Date(alertB.created_at).getTime() : 0;
    if (timeA !== timeB) {
      return timeB - timeA;
    }

    return (a.pid_raw || 0) - (b.pid_raw || 0);
  });

  // Detect newly arrived critical patients and announce via aria-live
  const currentCriticalIds = new Set(criticals.map(p => p.patient_id));
  if (!isInitialCriticalLoad) {
    criticals.forEach(p => {
      if (!lastKnownCriticalIds.has(p.patient_id)) {
        announceCriticalArrival(p);
      }
    });
  }
  lastKnownCriticalIds = currentCriticalIds;
  isInitialCriticalLoad = false;

  // Render uncapped critical patient cards
  container.innerHTML = criticals.map(p => {
    const matchedAlert = alertMap.get(String(p.pid_raw)) || alertMap.get(p.patient_id);
    const isUnacked = matchedAlert ? !matchedAlert.acknowledged : true;

    // Trigger condition/vital
    let triggerText = 'Critical Telemetry Threshold Exceeded';
    if (matchedAlert && matchedAlert.reason) {
      triggerText = matchedAlert.reason;
    } else if (p.reasons && p.reasons.length > 0) {
      triggerText = p.reasons[0];
    } else if (p.spo2 < 90) {
      triggerText = `SpO₂ ${p.spo2}% — critically low`;
    } else if (p.temperature > 38.5) {
      triggerText = `Pyrexia ${p.temperature}°C — critically high`;
    } else if (p.heart_rate > 120) {
      triggerText = `Tachycardia ${p.heart_rate} bpm`;
    }

    // Relative alert time, absolute on hover
    let alertTimeRelative = 'Alert time: not available';
    let alertTimeAbsolute = '';
    if (matchedAlert && matchedAlert.created_at) {
      const dt = new Date(matchedAlert.created_at);
      alertTimeAbsolute = dt.toLocaleString();
      const elapsedMins = Math.round((Date.now() - dt.getTime()) / 60000);
      alertTimeRelative = elapsedMins <= 1 ? 'Just now' : `${elapsedMins}m ago`;
    }

    const lifecycleStatus = matchedAlert ? (matchedAlert.acknowledged ? 'ACKNOWLEDGED' : 'PENDING_ACK') : 'ACTIVE';
    const docName = p.assigned_doctor_name || p.assigned_doctor || 'Dr. Shreya Sutar';

    return `
      <div class="critical-card ${isUnacked ? 'unacked' : ''}" onclick="openPatientDrawer('${p.patient_id}')" role="button" tabindex="0" onkeydown="if(event.key==='Enter')openPatientDrawer('${p.patient_id}')" aria-label="Critical alert for ${p.name}">
        <div class="critical-card-header">
          <div class="critical-patient-title">
            <span class="status-dot red"></span>
            <span class="font-mono" style="color:var(--accent);">${p.patient_id}</span>
            <span>${escapeHtml(p.name)}</span>
          </div>
          <span class="critical-time-tag font-mono" title="${alertTimeAbsolute}">${alertTimeRelative}</span>
        </div>

        <div class="critical-location-line">
          ${p.ward} • Room ${p.room_no} • Bed ${p.bed_no} • <span style="color:var(--text);">${escapeHtml(docName)}</span>
        </div>

        <div class="critical-trigger-box">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block; vertical-align:middle; margin-right:4px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="8" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          ${escapeHtml(triggerText)}
        </div>

        <div class="critical-footer-row">
          <div class="vitals-strip" style="background:transparent; padding:0;">
            <span class="${p.spo2 < 90 ? 'val-danger' : ''}">SpO₂: ${p.spo2}%</span> •
            <span class="${p.temperature > 38.5 ? 'val-danger' : ''}">T: ${p.temperature}°</span> •
            <span class="${p.heart_rate > 120 ? 'val-danger' : ''}">HR: ${p.heart_rate}</span>
          </div>
          <span class="ack-pill ${isUnacked ? 'unacked' : 'acked'} font-mono">${lifecycleStatus}</span>
        </div>
      </div>
    `;
  }).join('');
}

function announceCriticalArrival(patient) {
  const el = document.getElementById('criticalArrivalAnnouncement');
  if (el) {
    el.textContent = `New critical alert arrived for patient ${patient.name}, ID ${patient.patient_id}, in ${patient.ward}.`;
  }
}

// ============================================================
// 6. PATIENT SLIDE-OVER TELEMETRY DRAWER (PRESERVED)
// ============================================================
function openPatientDrawer(patientId) {
  const patient = allPatients.find(p => p.patient_id === patientId || p.pid_raw == patientId);
  if (!patient) return;
  currentSelectedPatient = patient;

  setText('drawerPid', patient.patient_id);
  setText('drawerName', patient.name);
  setText('drawerDemographics', `${patient.age || 45} yrs • ${patient.gender || 'Male'} • Ward: ${patient.ward}`);
  setText('drawerWardRoom', `${patient.ward} • Room ${patient.room_no} • Bed ${patient.bed_no}`);
  setText('drawerDoctor', patient.assigned_doctor_name || patient.assigned_doctor || 'Dr. Shreya Sutar');
  setText('drawerSpecialty', patient.assigned_doctor_specialty || patient.specialty || 'General Medicine');

  setText('drawerHr', `${patient.heart_rate} bpm`);
  setText('drawerSpo2', `${patient.spo2}%`);
  setText('drawerTemp', `${patient.temperature} °C`);
  setText('drawerBp', `${patient.systolic_bp}/${patient.diastolic_bp} mmHg`);
  setText('drawerRr', `${patient.respiratory_rate} /min`);

  const drawerReasons = patient.reasons && patient.reasons.length > 0
    ? patient.reasons.map(r => `• ${escapeHtml(r)}`).join('<br>')
    : '• Routine Continuous Telemetry';

  const drawerReasonEl = document.getElementById('drawerReason');
  if (drawerReasonEl) drawerReasonEl.innerHTML = drawerReasons;

  setText('drawerRec', patient.recommendation || 'Maintain continuous physiological monitoring.');

  const drawer = document.getElementById('patientDrawer');
  if (drawer) drawer.style.display = 'block';
}

function closePatientDrawer() {
  const drawer = document.getElementById('patientDrawer');
  if (drawer) drawer.style.display = 'none';
}

// Close drawer on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closePatientDrawer();
    closeAllRowMenus();
  }
});

// ============================================================
// 7. DATABASE OPERATIONS: ADMIT, EDIT & DISCHARGE MODALS
// ============================================================
function openModal(id) {
  const m = document.getElementById(id);
  if (!m) return;
  m.style.display = 'flex';

  if (id === 'modalAddPatient') {
    const alertEl = document.getElementById('addPatientAlert');
    if (alertEl) alertEl.style.display = 'none';
    const form = document.getElementById('formAddPatient');
    if (form) form.reset();
  } else if (id === 'modalEditPatient') {
    if (typeof populateEditPatientModal === 'function') {
      populateEditPatientModal();
    }
  } else if (id === 'modalDeletePatient' || id === 'deletePatientModal') {
    const alertEl = document.getElementById('deletePatientAlert');
    if (alertEl) alertEl.style.display = 'none';
    populateDeletePatientDropdown();
  } else if (id === 'modalDischargePatient' || id === 'dischargePatientModal') {
    const alertEl = document.getElementById('dischargePatientAlert');
    if (alertEl) alertEl.style.display = 'none';
    populateDischargePatientDropdown();
  }
}

function closeModal(id) {
  let modalId = id;
  if (id === 'modalDischargePatient') modalId = 'dischargePatientModal';
  if (id === 'modalDeletePatient') modalId = 'deletePatientModal';
  const m = document.getElementById(modalId) || document.getElementById(id);
  if (m) m.style.display = 'none';
}

let dischargePatientState = {
  selectedPid: null,
  matches: []
};

function populateDischargePatientDropdown() {
  dischargePatientState = { selectedPid: null, matches: [] };
  const input = document.getElementById('dischargePatientSearchInput');
  const alertEl = document.getElementById('dischargePatientAlert');
  const confirmBox = document.getElementById('dischargeConfirmBox');
  const matchesBox = document.getElementById('dischargePatientMatchesBox');
  const btnSubmit = document.getElementById('btnDischargePatientSubmit');
  const idInput = document.getElementById('dischargePatientIdInput');

  if (input) input.value = '';
  if (idInput) idInput.value = '';
  if (alertEl) alertEl.style.display = 'none';
  if (confirmBox) confirmBox.style.display = 'block';
  if (matchesBox) matchesBox.style.display = 'none';
  const titleEl = document.getElementById('dischargeConfirmPidName');
  if (titleEl) titleEl.textContent = 'Select a patient above or via patient row';
  const wardEl = document.getElementById('dischargeConfirmWard');
  if (wardEl) wardEl.textContent = '--';
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.style.opacity = '0.5';
    btnSubmit.style.cursor = 'not-allowed';
  }
}

async function searchPatientForDischarge() {
  const alertEl = document.getElementById('dischargePatientAlert');
  const confirmBox = document.getElementById('dischargeConfirmBox');
  const matchesBox = document.getElementById('dischargePatientMatchesBox');
  const matchesSelect = document.getElementById('dischargePatientMatchSelect');
  const btnSubmit = document.getElementById('btnDischargePatientSubmit');
  const idInput = document.getElementById('dischargePatientIdInput');

  if (alertEl) alertEl.style.display = 'none';
  if (matchesBox) matchesBox.style.display = 'none';
  dischargePatientState.selectedPid = null;
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.style.opacity = '0.5';
    btnSubmit.style.cursor = 'not-allowed';
  }

  const query = (document.getElementById('dischargePatientSearchInput')?.value || '').trim();
  if (!query) {
    showModalError(alertEl, 'Please enter a Patient ID or Name to search.');
    return;
  }

  try {
    const res = await fetch(`/api/v1/patients/search?query=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!res.ok) {
      showModalError(alertEl, data.detail || 'Search failed.');
      return;
    }

    const matches = data.matches || [];
    dischargePatientState.matches = matches;

    if (matches.length === 0) {
      showModalError(alertEl, 'Patient not found. Please check the Patient ID or Name.');
      return;
    }

    if (matches.length === 1) {
      const p = matches[0];
      dischargePatientState.selectedPid = p.pid_raw;
      if (idInput) idInput.value = p.pid_raw;
      const titleEl = document.getElementById('dischargeConfirmPidName');
      const wardEl = document.getElementById('dischargeConfirmWard');
      if (titleEl) titleEl.textContent = `${p.patient_id} — ${p.name}`;
      if (wardEl) wardEl.textContent = `${p.ward} • Room ${p.room_no} • Bed ${p.bed_no}`;
      if (confirmBox) confirmBox.style.display = 'block';
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.style.opacity = '1';
        btnSubmit.style.cursor = 'pointer';
      }
    } else {
      if (matchesSelect) {
        matchesSelect.innerHTML = `<option value="">-- Select Patient ID --</option>` +
          matches.map(m => `<option value="${m.pid_raw}">${m.patient_id} — ${m.name} (${m.ward})</option>`).join('');
      }
      if (matchesBox) matchesBox.style.display = 'block';
    }
  } catch (err) {
    showModalError(alertEl, `Search error: ${err.message}`);
  }
}

function selectMatchPatientForDischarge() {
  const select = document.getElementById('dischargePatientMatchSelect');
  const confirmBox = document.getElementById('dischargeConfirmBox');
  const btnSubmit = document.getElementById('btnDischargePatientSubmit');
  const idInput = document.getElementById('dischargePatientIdInput');

  const pidRaw = select?.value;
  if (!pidRaw) {
    dischargePatientState.selectedPid = null;
    if (idInput) idInput.value = '';
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.style.opacity = '0.5';
      btnSubmit.style.cursor = 'not-allowed';
    }
    return;
  }

  const pidNum = parseInt(pidRaw, 10);
  const p = dischargePatientState.matches.find(m => m.pid_raw === pidNum);

  if (p) {
    dischargePatientState.selectedPid = p.pid_raw;
    if (idInput) idInput.value = p.pid_raw;
    const titleEl = document.getElementById('dischargeConfirmPidName');
    const wardEl = document.getElementById('dischargeConfirmWard');
    if (titleEl) titleEl.textContent = `${p.patient_id} — ${p.name}`;
    if (wardEl) wardEl.textContent = `${p.ward} • Room ${p.room_no} • Bed ${p.bed_no}`;
    if (confirmBox) confirmBox.style.display = 'block';
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.style.opacity = '1';
      btnSubmit.style.cursor = 'pointer';
    }
  }
}

let deletePatientState = {
  selectedPid: null,
  matches: []
};

function populateDeletePatientDropdown() {
  deletePatientState = { selectedPid: null, matches: [] };
  const input = document.getElementById('deletePatientSearchInput');
  const alertEl = document.getElementById('deletePatientAlert');
  const confirmBox = document.getElementById('deleteConfirmBox');
  const matchesBox = document.getElementById('deletePatientMatchesBox');
  const btnSubmit = document.getElementById('btnDeletePatientSubmit');

  if (input) input.value = '';
  if (alertEl) alertEl.style.display = 'none';
  if (confirmBox) confirmBox.style.display = 'none';
  if (matchesBox) matchesBox.style.display = 'none';
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.style.opacity = '0.5';
    btnSubmit.style.cursor = 'not-allowed';
  }
}

async function searchPatientForDelete() {
  const alertEl = document.getElementById('deletePatientAlert');
  const confirmBox = document.getElementById('deleteConfirmBox');
  const matchesBox = document.getElementById('deletePatientMatchesBox');
  const matchesSelect = document.getElementById('deletePatientMatchSelect');
  const btnSubmit = document.getElementById('btnDeletePatientSubmit');

  if (alertEl) alertEl.style.display = 'none';
  if (confirmBox) confirmBox.style.display = 'none';
  if (matchesBox) matchesBox.style.display = 'none';
  deletePatientState.selectedPid = null;
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.style.opacity = '0.5';
    btnSubmit.style.cursor = 'not-allowed';
  }

  const query = (document.getElementById('deletePatientSearchInput')?.value || '').trim();
  if (!query) {
    showModalError(alertEl, 'Please enter a Patient ID or Name to search.');
    return;
  }

  try {
    const res = await fetch(`/api/v1/patients/search?query=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!res.ok) {
      showModalError(alertEl, data.detail || 'Search failed.');
      return;
    }

    const matches = data.matches || [];
    deletePatientState.matches = matches;

    if (matches.length === 0) {
      showModalError(alertEl, 'Patient not found. Please check the Patient ID or Name.');
      return;
    }

    if (matches.length === 1) {
      const p = matches[0];
      deletePatientState.selectedPid = p.pid_raw;
      const titleEl = document.getElementById('deleteConfirmPidName');
      const wardEl = document.getElementById('deleteConfirmWard');
      if (titleEl) titleEl.textContent = `${p.patient_id} — ${p.name}`;
      if (wardEl) wardEl.textContent = `${p.ward} • Room ${p.room_no} • Bed ${p.bed_no}`;
      if (confirmBox) confirmBox.style.display = 'block';
      if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.style.opacity = '1';
        btnSubmit.style.cursor = 'pointer';
      }
    } else {
      if (matchesSelect) {
        matchesSelect.innerHTML = `<option value="">-- Select Patient ID --</option>` +
          matches.map(m => `<option value="${m.pid_raw}">${m.patient_id} — ${m.name} (${m.ward})</option>`).join('');
      }
      if (matchesBox) matchesBox.style.display = 'block';
    }
  } catch (err) {
    showModalError(alertEl, `Search error: ${err.message}`);
  }
}

function selectMatchPatientForDelete() {
  const select = document.getElementById('deletePatientMatchSelect');
  const confirmBox = document.getElementById('deleteConfirmBox');
  const btnSubmit = document.getElementById('btnDeletePatientSubmit');

  const pidRaw = select?.value;
  if (!pidRaw) {
    deletePatientState.selectedPid = null;
    if (confirmBox) confirmBox.style.display = 'none';
    if (btnSubmit) {
      btnSubmit.disabled = true;
      btnSubmit.style.opacity = '0.5';
      btnSubmit.style.cursor = 'not-allowed';
    }
    return;
  }

  const pidNum = parseInt(pidRaw, 10);
  const p = deletePatientState.matches.find(m => m.pid_raw === pidNum);

  if (p) {
    deletePatientState.selectedPid = p.pid_raw;
    const titleEl = document.getElementById('deleteConfirmPidName');
    const wardEl = document.getElementById('deleteConfirmWard');
    if (titleEl) titleEl.textContent = `${p.patient_id} — ${p.name}`;
    if (wardEl) wardEl.textContent = `${p.ward} • Room ${p.room_no} • Bed ${p.bed_no}`;
    if (confirmBox) confirmBox.style.display = 'block';
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.style.opacity = '1';
      btnSubmit.style.cursor = 'pointer';
    }
  }
}

async function handleAddPatient(e) {
  e.preventDefault();
  const alertEl = document.getElementById('addPatientAlert');
  if (alertEl) alertEl.style.display = 'none';

  const firstName = (document.getElementById('addFirstName')?.value || '').trim();
  const lastName = (document.getElementById('addLastName')?.value || '').trim();
  const ageVal = document.getElementById('addAge')?.value;
  const genderVal = document.getElementById('addGender')?.value || 'Male';
  const wardVal = document.getElementById('addWard')?.value || 'ICU';
  const roomVal = (document.getElementById('addRoomNo')?.value || '201').trim();
  const bedVal = (document.getElementById('addBedNo')?.value || '1').trim();
  const bloodGroupVal = document.getElementById('addBloodGroup')?.value || 'O+';
  const customPid = document.getElementById('addCustomPid')?.value;

  if (!firstName || !lastName) {
    showModalError(alertEl, 'Patient first name and last name are required.');
    return;
  }
  const ageNum = parseInt(ageVal, 10);
  if (isNaN(ageNum) || ageNum < 0 || ageNum > 120) {
    showModalError(alertEl, 'Age must be between 0 and 120.');
    return;
  }
  if (!wardVal) {
    showModalError(alertEl, 'Ward is required.');
    return;
  }

  const doctorVal = document.getElementById('addDoctor')?.value || 'DOC003';

  const payload = {
    first_name: firstName,
    last_name: lastName,
    age: ageNum,
    gender: genderVal,
    ward: wardVal,
    room_no: roomVal,
    bed_no: bedVal,
    blood_group: bloodGroupVal,
    assigned_doctor_id: doctorVal,
    patient_id: customPid ? parseInt(customPid, 10) : null
  };

  const btnSubmit = document.getElementById('btnAddPatientSubmit');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Saving...';
  }

  try {
    const res = await fetch('/api/v1/patients', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (!res.ok) {
      const msg = data.detail || data.message || 'Failed to create patient.';
      showModalError(alertEl, msg);
    } else {
      closeModal('modalAddPatient');
      alert(`Patient ${data.patient_id || ''} added successfully.`);
      await refreshLiveVitals();
    }
  } catch (err) {
    showModalError(alertEl, `Network error: ${err.message}`);
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = 'Save Patient';
    }
  }
}

async function handleEditPatient(e) {
  e.preventDefault();
  const alertEl = document.getElementById('editPatientAlert');
  if (alertEl) alertEl.style.display = 'none';

  const select = document.getElementById('editPatientSelect');
  const pid = select?.value;
  if (!pid) {
    showModalError(alertEl, 'Please select a patient to edit.');
    return;
  }

  const payload = {
    first_name: (document.getElementById('editFirstName')?.value || '').trim(),
    last_name: (document.getElementById('editLastName')?.value || '').trim(),
    age: parseInt(document.getElementById('editAge')?.value, 10) || 45,
    gender: document.getElementById('editGender')?.value || 'Male',
    ward: document.getElementById('editWard')?.value || 'ICU',
    room_no: (document.getElementById('editRoomNo')?.value || '201').trim(),
    bed_no: (document.getElementById('editBedNo')?.value || '1').trim(),
    blood_group: document.getElementById('editBloodGroup')?.value || 'O+',
    assigned_doctor_id: document.getElementById('editDoctor')?.value || 'DOC003'
  };

  const btnSubmit = document.getElementById('btnEditPatientSubmit');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Updating...';
  }

  try {
    const res = await fetch(`/api/v1/patients/${pid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      showModalError(alertEl, data.detail || data.message || 'Update failed.');
    } else {
      closeModal('modalEditPatient');
      alert(`Patient ${pid} updated successfully.`);
      await refreshLiveVitals();
    }
  } catch (err) {
    showModalError(alertEl, `Network error: ${err.message}`);
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = 'Update Record';
    }
  }
}

async function handleDischargePatient(e) {
  e.preventDefault();
  const alertEl = document.getElementById('dischargePatientAlert');
  if (alertEl) alertEl.style.display = 'none';

  const inp = document.getElementById('dischargePatientIdInput');
  const pid = dischargePatientState.selectedPid || (inp ? inp.value : null);
  if (!pid) {
    showModalError(alertEl, 'Please select a patient to discharge.');
    return;
  }

  const btnSubmit = document.getElementById('btnDischargePatientSubmit');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Discharging...';
  }

  try {
    const res = await fetch(`/api/v1/patients/${pid}`, {
      method: 'DELETE'
    });

    const data = await res.json();
    if (!res.ok) {
      const msg = data.detail || data.message || 'Unable to discharge patient.';
      showModalError(alertEl, msg);
    } else {
      closeModal('dischargePatientModal');
      closeModal('modalDischargePatient');
      alert(`Patient P${pid} has been discharged successfully.`);
      await refreshLiveVitals();
    }
  } catch (err) {
    showModalError(alertEl, `Network error: ${err.message}`);
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = 'Confirm Discharge';
    }
  }
}

async function handleDeletePatient(e) {
  e.preventDefault();
  const alertEl = document.getElementById('deletePatientAlert');
  if (alertEl) alertEl.style.display = 'none';

  const pid = deletePatientState.selectedPid;
  if (!pid) {
    showModalError(alertEl, 'Please find and select a patient to delete first.');
    return;
  }

  const btnSubmit = document.getElementById('btnDeletePatientSubmit');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Deleting...';
  }

  try {
    const res = await fetch(`/api/v1/patients/${pid}`, {
      method: 'DELETE'
    });

    const data = await res.json();

    if (!res.ok) {
      const msg = data.detail || data.message || 'Unable to delete patient.';
      showModalError(alertEl, msg);
    } else {
      closeModal('deletePatientModal');
      closeModal('modalDeletePatient');
      alert(`Patient P${pid} deleted successfully.`);
      await refreshLiveVitals();
    }
  } catch (err) {
    showModalError(alertEl, `Network error: ${err.message}`);
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.textContent = 'Confirm Delete';
    }
  }
}

function showModalError(el, msg) {
  if (el) {
    el.textContent = msg;
    el.style.display = 'block';
  } else {
    alert(msg);
  }
}

// ============================================================
// 8. SIMULATOR CONTROLS (MOVED TO SYSTEM STATUS DEV TOOLS)
// ============================================================
function updateSimulatorUI(statusText, isRunning) {
  const pill = document.getElementById('simStatusPill');
  const sysSim = document.getElementById('sysSimState');
  const btnStart = document.getElementById('btnStartSim');
  const btnStop = document.getElementById('btnStopSim');

  if (pill) {
    pill.className = `sim-status-pill ${isRunning ? 'running' : 'stopped'}`;
    pill.innerHTML = `<span class="status-dot ${isRunning ? '' : 'red'}"></span> ${statusText || (isRunning ? 'RUNNING' : 'STOPPED')}`;
  }
  if (sysSim) {
    sysSim.textContent = isRunning ? 'RUNNING' : 'STOPPED';
    sysSim.style.color = isRunning ? 'var(--low)' : 'var(--text)';
  }
  if (btnStart) btnStart.disabled = isRunning;
  if (btnStop) btnStop.disabled = !isRunning;
}

async function startSimulator() {
  try {
    const res = await fetch('/api/v1/simulator/start', { method: 'POST' });
    if (res.ok) {
      simulatorRunning = true;
      updateSimulatorUI('RUNNING', true);
      refreshLiveVitals();
    }
  } catch (err) {
    alert('Failed to start simulator.');
  }
}

async function stopSimulator() {
  try {
    const res = await fetch('/api/v1/simulator/stop', { method: 'POST' });
    if (res.ok) {
      simulatorRunning = false;
      updateSimulatorUI('STOPPED', false);
    }
  } catch (err) {
    alert('Failed to stop simulator.');
  }
}

async function changeInterval(val) {
  updateIntervalSec = parseInt(val, 10);
  try {
    await fetch('/api/v1/update_interval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval_seconds: updateIntervalSec })
    });
  } catch (err) {
    console.error('Failed to set interval:', err);
  }
}

// Null-Guarded Legacy Pagination Stubs
function prevPatientPage() {}
function nextPatientPage() {}
function changePatientPageSize() {}

// Notification Test
function testDoctorNotification() {
  if ('Notification' in window) {
    Notification.requestPermission().then(permission => {
      if (permission === 'granted') {
        new Notification('CRITICAL MEDICAL ALERT — MEDINTEL', {
          body: 'P101 Nikita Bajwa (ICU Room 201 Bed 1) - SpO2 89%, Temp 40.1°C',
          icon: '/static/assets/favicon.svg'
        });
        alert('Web push notification dispatched to browser.');
      } else {
        alert('Browser notification permission denied.');
      }
    });
  } else {
    alert('Web push notification simulation triggered via FCM backend.');
  }
}

// Helper utilities
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
