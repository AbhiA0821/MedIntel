import {
  LiveVitalsResponse,
  SimulatorStatus,
  PipelineStatusMetrics,
  ActiveAlert,
  DoctorInfo,
  DoctorDevice
} from '../types/medintel';

const API_BASE_URL = 'http://127.0.0.1:8000';

export async function fetchLiveVitals(): Promise<LiveVitalsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/live_vitals`);
  if (!res.ok) {
    throw new Error(`Failed to fetch live vitals: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSimulatorStatus(): Promise<SimulatorStatus> {
  const res = await fetch(`${API_BASE_URL}/api/v1/simulator/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch simulator status: ${res.statusText}`);
  }
  return res.json();
}

export async function startSimulator(): Promise<{ status: string; message: string; pid?: number }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/simulator/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.ok) {
    throw new Error(`Failed to start simulator: ${res.statusText}`);
  }
  return res.json();
}

export async function stopSimulator(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/simulator/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.ok) {
    throw new Error(`Failed to stop simulator: ${res.statusText}`);
  }
  return res.json();
}

export async function updateInterval(intervalSeconds: number): Promise<{ status: string; message: string; interval_seconds: number }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/update_interval`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_seconds: intervalSeconds })
  });
  if (!res.ok) {
    throw new Error(`Failed to update interval: ${res.statusText}`);
  }
  return res.json();
}

export async function triggerCycle(): Promise<{ status: string; generated_vitals_count: number; cycle_duration_seconds: number }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/trigger_cycle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  if (!res.ok) {
    throw new Error(`Failed to trigger cycle: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchPipelineStatus(): Promise<{ status: string; metrics: PipelineStatusMetrics }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/pipeline_status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch pipeline status: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchActiveAlerts(): Promise<{ status: string; active_alerts_count: number; alerts: ActiveAlert[] }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/alerts/active`);
  if (!res.ok) {
    throw new Error(`Failed to fetch active alerts: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchAlertHistory(): Promise<{ status: string; history: ActiveAlert[] }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/alerts/history`);
  if (!res.ok) {
    throw new Error(`Failed to fetch alert history: ${res.statusText}`);
  }
  return res.json();
}

export async function doctorLogin(email: string, firebaseUid?: string): Promise<{ status: string; message: string; doctor_info: DoctorInfo }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, firebase_uid: firebaseUid })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errData.detail || 'Doctor login failed');
  }
  return res.json();
}

export async function fetchDoctorDevices(doctorId?: string): Promise<{ status: string; devices: DoctorDevice[] }> {
  const url = doctorId ? `${API_BASE_URL}/api/v1/auth/devices?doctor_id=${doctorId}` : `${API_BASE_URL}/api/v1/auth/devices`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch doctor devices: ${res.statusText}`);
  }
  return res.json();
}

export async function deactivateDoctorDevice(fcmToken: string): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/deactivate_device`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fcm_token: fcmToken })
  });
  if (!res.ok) {
    throw new Error(`Failed to deactivate device: ${res.statusText}`);
  }
  return res.json();
}

export async function createDoctorNonce(doctorId: string): Promise<{ status: string; nonce: string }> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/create_nonce`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doctor_id: doctorId })
  });
  if (!res.ok) {
    throw new Error(`Failed to create nonce: ${res.statusText}`);
  }
  return res.json();
}
