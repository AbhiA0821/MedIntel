export type UserRole = 'DOCTOR' | 'RECEPTIONIST';

export interface DoctorInfo {
  doctor_id: string;
  doctor_name: string;
  email: string;
  firebase_uid?: string;
  specialty: string;
  role: string;
}

export interface Patient {
  patient_id: string;
  pid_raw: number;
  name: string;
  age: number;
  gender: string;
  ward: string;
  room_no: string;
  bed_no: string;
  heart_rate: number;
  spo2: number;
  temperature: number;
  systolic_bp: number;
  diastolic_bp: number;
  respiratory_rate: number;
  severity: 'CRITICAL' | 'MODERATE' | 'LOW';
  trend: 'WORSENING' | 'IMPROVING' | 'STABLE';
  reasons: string[];
  recommendation: string;
  assigned_specialty?: string;
  assigned_doctor?: string;
}

export interface LiveVitalsResponse {
  status: string;
  total_patients: number;
  total_vitals_count: number;
  critical_count: number;
  moderate_count: number;
  low_count: number;
  latest_db_update: string;
  patients: Patient[];
}

export interface SimulatorStatus {
  status: 'RUNNING' | 'STOPPED';
  running: boolean;
  pid: number | null;
  update_interval: number;
  last_cycle_duration: number;
}

export interface PipelineStatusMetrics {
  simulator_status: string;
  total_patients: number;
  total_vitals_count: number;
  latest_db_update: string;
  update_interval: number;
  last_cycle_duration: number;
  pipeline_health: string;
  heartbeat: string | null;
}

export interface ActiveAlert {
  alert_id: number;
  patient_id: string;
  severity: string;
  reason: string;
  recommendation: string;
  priority: string;
  ward: string;
  room_no: string;
  bed_no: string;
  specialty: string;
  assigned_doctor: string;
  created_at: string;
  notification_status: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
  resolved_at: string | null;
  active: boolean;
}

export interface DoctorDevice {
  device_id: number;
  doctor_id: string;
  firebase_uid: string;
  doctor_name: string;
  specialty: string;
  fcm_token: string;
  registered_at: string;
  active: boolean;
}
