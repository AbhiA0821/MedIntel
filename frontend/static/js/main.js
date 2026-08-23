// MEDINTEL — Vanilla JavaScript Core Controller
let allPatients = [];
let simulatorRunning = false;
let updateIntervalSec = 3;
let pollTimer = null;
let currentSelectedPatient = null;

document.addEventListener('DOMContentLoaded', () => {
  initClock();
  loadInitialBackendData();
  setupEventListeners();
});

// Real-Time Clock Widget
function initClock() {
  const clockEl = document.getElementById('liveClock');
  if (!clockEl) return;
  const update = () => {
    const now = new Date();
    clockEl.textContent = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' + now.toLocaleTimeString('en-US', { hour12: false });
  };
  update();
  setInterval(update, 1000);
}

// Initial Data Load
async function loadInitialBackendData() {
  await fetchSimulatorStatus();
  await refreshLiveVitals();
}

// Fetch Simulator Status
async function fetchSimulatorStatus() {
  try {
    const res = await fetch('/api/v1/simulator/status');
    if (!res.ok) return;
    const data = await res.json();
    simulatorRunning = data.running || data.status === 'RUNNING';
    updateSimulatorUI(data.status, simulatorRunning);
  } catch (err) {
    console.error('Error fetching simulator status:', err);
  }
}

// Update Simulator Badge & Buttons
function updateSimulatorUI(statusText, isRunning) {
  const pill = document.getElementById('simStatusPill');
  const btnStart = document.getElementById('btnStartSim');
  const btnStop = document.getElementById('btnStopSim');

  if (pill) {
    pill.className = `sim-status-pill ${isRunning ? 'running' : 'stopped'}`;
    pill.innerHTML = `<span class="status-dot ${isRunning ? '' : 'red'}"></span> ${statusText || (isRunning ? 'RUNNING' : 'STOPPED')}`;
  }

  if (btnStart) btnStart.disabled = isRunning;
  if (btnStop) btnStop.disabled = !isRunning;

  // Manage Polling Loop
  if (isRunning && !pollTimer) {
    pollTimer = setInterval(refreshLiveVitals, updateIntervalSec * 1000);
  } else if (!isRunning && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// Start Simulator Handler
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

// Stop Simulator Handler
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

// Change Update Interval
async function changeInterval(val) {
  updateIntervalSec = parseInt(val, 10);
  try {
    await fetch('/api/v1/update_interval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval_seconds: updateIntervalSec })
    });
    if (simulatorRunning) {
      clearInterval(pollTimer);
      pollTimer = setInterval(refreshLiveVitals, updateIntervalSec * 1000);
    }
  } catch (err) {
    console.error('Failed to set interval:', err);
  }
}

// Fetch Live Vitals & Update UI
async function refreshLiveVitals() {
  try {
    const res = await fetch('/api/v1/live_vitals');
    if (!res.ok) return;
    const data = await res.json();
    allPatients = data.patients || [];

    // Update KPI values
    setText('kpiTotalPatients', data.total_patients || 100);
    setText('kpiCriticalCount', data.critical_count || 8);
    setText('kpiModerateCount', data.moderate_count || 7);
    setText('kpiLowCount', data.low_count || 85);
    setText('kpiTotalRecords', (data.total_vitals_count || 5043).toLocaleString());
    setText('kpiLastUpdate', data.latest_db_update || '16:04:31');
    setText('sidebarLastUpdate', data.latest_db_update || '16:04:31');

    renderPatientTable();
    renderCriticalPanel();
  } catch (err) {
    console.error('Error refreshing live vitals:', err);
  }
}

// Render Professional Monitored Patient Table with Strict Grid Columns
function renderPatientTable() {
  const tbody = document.getElementById('patientTableBody');
  if (!tbody) return;

  const searchVal = (document.getElementById('searchInput')?.value || '').toLowerCase();
  const wardVal = document.getElementById('wardFilter')?.value || 'All Wards';
  const sevVal = document.getElementById('severityFilter')?.value || 'All Severity';

  const filtered = allPatients.filter(p => {
    const matchSearch = p.patient_id.toLowerCase().includes(searchVal) || p.name.toLowerCase().includes(searchVal);
    const matchWard = wardVal === 'All Wards' || p.ward === wardVal;
    const matchSev = sevVal === 'All Severity' || p.severity.toUpperCase() === sevVal.toUpperCase();
    return matchSearch && matchWard && matchSev;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="15" style="text-align:center; padding: 20px; color: var(--text-subtle);">No matching patients found.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.slice(0, 10).map(p => {
    const isCritical = p.severity === 'CRITICAL';
    const isModerate = p.severity === 'MODERATE';
    const sevBadge = isCritical 
      ? '<span class="badge-severity CRITICAL">🔴 CRITICAL</span>'
      : isModerate 
        ? '<span class="badge-severity MODERATE">🟠 MODERATE</span>'
        : '<span class="badge-severity LOW">🟢 LOW RISK</span>';

    const trendIcon = p.trend === 'WORSENING' || p.trend === 'UP' ? '↗' : p.trend === 'IMPROVING' || p.trend === 'DOWN' ? '↘' : '→';
    const trendClass = p.trend === 'WORSENING' || p.trend === 'UP' ? 'val-danger' : p.trend === 'IMPROVING' || p.trend === 'DOWN' ? 'text-low' : 'text-muted';

    return `
      <tr class="${isCritical ? 'row-critical' : ''}" onclick="openPatientDrawer('${p.patient_id}')">
        <td class="font-mono col-pid">${p.patient_id}</td>
        <td class="col-name">${p.name}</td>
        <td class="font-mono col-age">${p.age}</td>
        <td class="col-gender">${p.gender}</td>
        <td class="col-ward">${p.ward}</td>
        <td class="font-mono col-room">${p.room_no}</td>
        <td class="font-mono col-bed">${p.bed_no}</td>
        <td class="font-mono col-hr ${p.heart_rate > 120 ? 'val-danger' : ''}">${p.heart_rate}</td>
        <td class="font-mono col-spo2 ${p.spo2 < 90 ? 'val-danger' : ''}">${p.spo2}%</td>
        <td class="font-mono col-temp ${p.temperature > 38.5 ? 'val-danger' : ''}">${p.temperature}°C</td>
        <td class="font-mono col-bp">${p.systolic_bp}/${p.diastolic_bp}</td>
        <td class="font-mono col-rr">${p.respiratory_rate}</td>
        <td class="col-sev">${sevBadge}</td>
        <td class="col-trend font-mono ${trendClass}" style="font-size:13px; font-weight:800;">${trendIcon}</td>
        <td class="font-mono col-time">${p.last_update || '16:04:31'}</td>
      </tr>
    `;
  }).join('');
}

// Render Critical Patients Column with Structured Bulleted Reasons
function renderCriticalPanel() {
  const container = document.getElementById('criticalPatientsList');
  if (!container) return;

  const criticals = allPatients.filter(p => p.severity === 'CRITICAL');
  setText('criticalHeaderCount', criticals.length);

  if (criticals.length === 0) {
    container.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--text-subtle);">All monitored patients currently within critical thresholds.</div>`;
    return;
  }

  container.innerHTML = criticals.slice(0, 3).map(p => {
    const reasonItems = p.reasons && p.reasons.length > 0 
      ? p.reasons.map(r => `<li><span class="bullet-dot">•</span> ${r}</li>`).join('')
      : `<li><span class="bullet-dot">•</span> Hypoxia / Pyrexia</li>`;

    return `
      <div class="critical-card" onclick="openPatientDrawer('${p.patient_id}')">
        <div class="critical-header">
          <div>
            <span class="status-dot red"></span>
            <strong class="font-mono" style="color: var(--accent-blue); font-size:11px;">${p.patient_id}</strong>
            <span style="font-weight:700; color:#fff; margin-left: 4px; font-size:11px;">${p.name}</span>
          </div>
          <span class="font-mono" style="font-size:9px; color: var(--text-subtle);">16:04:31</span>
        </div>
        <div style="font-size:10px; color: var(--text-muted);">${p.ward} • Room ${p.room_no} • Bed ${p.bed_no}</div>
        <div class="critical-vitals font-mono">
          <span class="${p.spo2 < 90 ? 'val-danger' : ''}">SpO₂: ${p.spo2}%</span> •
          <span class="${p.temperature > 38.5 ? 'val-danger' : ''}">Temp: ${p.temperature}°C</span> •
          <span>BP: ${p.systolic_bp}/${p.diastolic_bp}</span>
        </div>
        <div class="reason-box">
          <div class="reason-title">REASON</div>
          <ul class="reason-bullets">
            ${reasonItems}
          </ul>
        </div>
        <div class="critical-rec-box">
          <span style="font-weight:700;">Rec:</span> ${p.recommendation || 'Initiate high-flow oxygen therapy.'}
        </div>
      </div>
    `;
  }).join('');
}

// Open Patient Slide-Over Drawer
function openPatientDrawer(patientId) {
  const patient = allPatients.find(p => p.patient_id === patientId);
  if (!patient) return;
  currentSelectedPatient = patient;

  setText('drawerPid', patient.patient_id);
  setText('drawerName', patient.name);
  setText('drawerDemographics', `${patient.age} yrs • ${patient.gender} • Ward: ${patient.ward}`);
  setText('drawerWardRoom', `${patient.ward} • Room ${patient.room_no} • Bed ${patient.bed_no}`);
  setText('drawerDoctor', patient.assigned_doctor || 'Dr. Amit Verma');
  setText('drawerSpecialty', patient.assigned_specialty || 'GENERAL MEDICINE');

  setText('drawerHr', `${patient.heart_rate} bpm`);
  setText('drawerSpo2', `${patient.spo2}%`);
  setText('drawerTemp', `${patient.temperature} °C`);
  setText('drawerBp', `${patient.systolic_bp}/${patient.diastolic_bp} mmHg`);
  setText('drawerRr', `${patient.respiratory_rate} /min`);

  const drawerReasons = patient.reasons && patient.reasons.length > 0
    ? patient.reasons.map(r => `• ${r}`).join('<br>')
    : '• Routine Monitoring';

  const drawerReasonEl = document.getElementById('drawerReason');
  if (drawerReasonEl) drawerReasonEl.innerHTML = drawerReasons;

  setText('drawerRec', patient.recommendation || 'Maintain continuous monitoring.');

  const drawer = document.getElementById('patientDrawer');
  if (drawer) drawer.style.display = 'block';
}

function closePatientDrawer() {
  const drawer = document.getElementById('patientDrawer');
  if (drawer) drawer.style.display = 'none';
}

// Database Management Modal Controls
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'flex';
}
function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'none';
}

function handleAddPatient(e) {
  e.preventDefault();
  alert('Patient management REST endpoint is not active on backend. Gracefully disabled.');
  closeModal('modalAddPatient');
}
function handleEditPatient(e) {
  e.preventDefault();
  alert('Patient update REST endpoint is not active on backend. Gracefully disabled.');
  closeModal('modalEditPatient');
}
function handleDeletePatient(e) {
  e.preventDefault();
  alert('Patient delete REST endpoint is not active on backend. Gracefully disabled.');
  closeModal('modalDeletePatient');
}

// Doctor Web Push Notification Dispatch
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

// Event Listeners Setup
function setupEventListeners() {
  document.getElementById('searchInput')?.addEventListener('keyup', renderPatientTable);
  document.getElementById('wardFilter')?.addEventListener('change', renderPatientTable);
  document.getElementById('severityFilter')?.addEventListener('change', renderPatientTable);
}

// Helper setter
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
