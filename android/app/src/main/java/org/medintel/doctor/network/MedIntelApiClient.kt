package org.medintel.doctor.network

import android.content.Context
import android.os.Build
import android.provider.Settings
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import org.medintel.doctor.data.CriticalAlert
import org.medintel.doctor.data.CriticalPatient
import org.medintel.doctor.data.DoctorProfile
import org.medintel.doctor.data.DoctorSession
import org.medintel.doctor.data.MonitoringSummary
import java.util.concurrent.TimeUnit

/**
 * Communicates with the MEDINTEL FastAPI Backend.
 * Handles doctor authentication, device registration, critical patient telemetry,
 * active alerts, and individual patient record retrieval with backend-enforced doctor isolation.
 */
object MedIntelApiClient {
    private const val TAG = "MedIntelApiClient"

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .writeTimeout(8, TimeUnit.SECONDS)
        .build()

    private fun getBaseUrl(context: Context): String {
        return DoctorSession.getBackendUrl(context)
    }

    /**
     * Authenticates doctor credentials against POST /api/v1/auth/login.
     * Enforces clinical verification on backend; does not treat ID alone as authentication.
     */
    suspend fun loginDoctor(context: Context, identifier: String, password: String): Result<DoctorProfile> = withContext(Dispatchers.IO) {
        val baseUrl = getBaseUrl(context)
        val url = "$baseUrl/api/v1/auth/login"

        val json = JSONObject().apply {
            put("email", identifier.trim())
            put("password", password.trim())
        }

        val requestBody = json.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
        val request = Request.Builder()
            .url(url)
            .post(requestBody)
            .build()

        try {
            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: ""

            if (!response.isSuccessful) {
                val errorDetail = try {
                    JSONObject(body).optString("detail", "HTTP ${response.code}")
                } catch (e: Exception) {
                    "HTTP ${response.code}: $body"
                }
                Log.w(TAG, "Doctor login rejected: $errorDetail")
                return@withContext Result.failure(Exception(errorDetail))
            }

            val respJson = JSONObject(body)
            val docInfo = respJson.optJSONObject("doctor_info")
                ?: return@withContext Result.failure(Exception("Missing doctor_info in response"))

            val docId = docInfo.getString("doctor_id")
            val name = docInfo.getString("doctor_name")
            val specialty = docInfo.getString("specialty")
            val role = docInfo.optString("role", if (docId.equals("REC001", ignoreCase = true)) "RECEPTIONIST" else "DOCTOR")

            val profile = DoctorProfile(
                doctorId = docId,
                name = name,
                specialty = specialty,
                role = role
            )
            DoctorSession.saveSession(context, docId, name, specialty, role)
            Log.i(TAG, "Successfully authenticated as $docId ($name - $specialty, $role)")
            Result.success(profile)
        } catch (e: Exception) {
            Log.e(TAG, "Network exception during login to $url: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Checks if the MEDINTEL backend is online and responding at the active base URL
     * or at an explicit test candidate URL.
     */
    suspend fun checkBackendHealth(context: Context, testUrl: String? = null): Boolean = withContext(Dispatchers.IO) {
        val targetUrl = testUrl?.trim()?.removeSuffix("/") ?: getBaseUrl(context)
        val request = Request.Builder()
            .url("$targetUrl/health")
            .get()
            .build()
        try {
            val response = client.newCall(request).execute()
            if (response.isSuccessful) {
                return@withContext true
            }
        } catch (e: Exception) {
            Log.w(TAG, "Backend health check failed for $targetUrl: ${e.message}")
        }
        false
    }

    /**
     * Registers the doctor's device and FCM token with the backend.
     * Masked logging ensures sensitive tokens are never exposed in logs.
     */
    suspend fun registerDevice(context: Context, fcmToken: String): Result<Boolean> = withContext(Dispatchers.IO) {
        val doctorId = DoctorSession.getDoctorId(context)
            ?: return@withContext Result.failure(IllegalStateException("No authenticated doctor to register device"))
        val doctorName = DoctorSession.getDoctorName(context) ?: "Doctor $doctorId"
        val specialty = DoctorSession.getSpecialty(context) ?: "GENERAL MEDICINE"
        val baseUrl = getBaseUrl(context)

        val maskedToken = if (fcmToken.length > 10) "${fcmToken.take(6)}...${fcmToken.takeLast(4)}" else "***"
        Log.i(TAG, "Registering device for $doctorId with token: $maskedToken")

        val deviceId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
            ?: "Android_${Build.MODEL}_${doctorId}"

        val json = JSONObject().apply {
            put("device_id", deviceId)
            put("doctor_id", doctorId)
            put("doctor_name", doctorName)
            put("specialty", specialty)
            put("fcm_token", fcmToken)
            put("firebase_uid", "FB-$doctorId")
        }

        val requestBody = json.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
        val request = Request.Builder()
            .url("$baseUrl/api/v1/auth/register_device")
            .post(requestBody)
            .build()

        try {
            val response = client.newCall(request).execute()
            val responseBody = response.body?.string() ?: ""
            if (response.isSuccessful) {
                Log.i(TAG, "Device registered successfully with backend for doctor $doctorId (HTTP ${response.code})")
                DoctorSession.saveFcmToken(context, fcmToken)
                Result.success(true)
            } else {
                Log.w(TAG, "Device registration failed: HTTP ${response.code} - $responseBody")
                Result.failure(Exception("HTTP ${response.code}: $responseBody"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Network error during device registration: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Fetches critical patients under the care of the authenticated doctor.
     * Uses doctor_id and specialty query parameters to enforce doctor isolation.
     */
    suspend fun fetchCriticalPatients(context: Context): Result<List<CriticalPatient>> = withContext(Dispatchers.IO) {
        val doctorId = DoctorSession.getDoctorId(context)
            ?: return@withContext Result.failure(SecurityException("Session required: Doctor is not logged in."))
        val specialty = DoctorSession.getSpecialty(context) ?: "GENERAL MEDICINE"
        val baseUrl = getBaseUrl(context)

        val url = "$baseUrl/api/v1/patients/critical?doctor_id=$doctorId&specialty=$specialty"
        val request = Request.Builder().url(url).get().build()

        try {
            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: ""
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("HTTP ${response.code}: $body"))
            }

            val json = JSONObject(body)
            val patientsArray = json.optJSONArray("critical_patients") ?: JSONArray()
            val list = mutableListOf<CriticalPatient>()

            for (i in 0 until patientsArray.length()) {
                val p = patientsArray.getJSONObject(i)
                val reasonsList = mutableListOf<String>()
                val rArr = p.optJSONArray("reasons")
                if (rArr != null) {
                    for (j in 0 until rArr.length()) {
                        reasonsList.add(rArr.getString(j))
                    }
                }

                val recList = mutableListOf<String>()
                val recArr = p.optJSONArray("recommendations")
                if (recArr != null) {
                    for (k in 0 until recArr.length()) {
                        recList.add(recArr.getString(k))
                    }
                }

                list.add(
                    CriticalPatient(
                        patientId = p.optString("patient_id", "P0"),
                        pidRaw = p.optInt("pid_raw", 0),
                        name = p.optString("name", "Unknown Patient"),
                        heartRate = p.optInt("heart_rate", 0),
                        spo2 = p.optDouble("spo2", 0.0),
                        temperature = p.optDouble("temperature", 0.0),
                        systolicBp = p.optInt("systolic_bp", 0),
                        diastolicBp = p.optInt("diastolic_bp", 0),
                        respiratoryRate = p.optInt("respiratory_rate", 0),
                        ward = p.optString("ward", "General Ward"),
                        roomNo = p.optString("room_no", "101"),
                        bedNo = p.optString("bed_no", "1"),
                        age = p.optInt("age", 40),
                        gender = p.optString("gender", "Unknown"),
                        severity = p.optString("severity", "CRITICAL"),
                        reasons = reasonsList,
                        recommendations = recList,
                        specialty = p.optString("specialty", specialty),
                        assignedDoctorId = p.optString("assigned_doctor_id", doctorId),
                        assignedDoctorName = p.optString("assigned_doctor_name", DoctorSession.getDoctorName(context) ?: "Doctor")
                    )
                )
            }
            Result.success(list)
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching critical patients: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Fetches active critical alerts for the current doctor.
     */
    suspend fun fetchActiveAlerts(context: Context): Result<List<CriticalAlert>> = withContext(Dispatchers.IO) {
        val doctorId = DoctorSession.getDoctorId(context)
            ?: return@withContext Result.failure(SecurityException("Session required: Doctor is not logged in."))
        val specialty = DoctorSession.getSpecialty(context) ?: "GENERAL MEDICINE"
        val baseUrl = getBaseUrl(context)

        val url = "$baseUrl/api/v1/alerts/active?doctor_id=$doctorId&specialty=$specialty"
        val request = Request.Builder().url(url).get().build()

        try {
            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: ""
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("HTTP ${response.code}: $body"))
            }

            val json = JSONObject(body)
            val alertsArray = json.optJSONArray("alerts") ?: JSONArray()
            val list = mutableListOf<CriticalAlert>()

            for (i in 0 until alertsArray.length()) {
                val a = alertsArray.getJSONObject(i)
                list.add(
                    CriticalAlert(
                        alertId = a.optString("alert_id", ""),
                        patientId = a.optString("patient_id", ""),
                        severity = a.optString("severity", "CRITICAL"),
                        reason = a.optString("reason", ""),
                        recommendation = a.optString("recommendation", ""),
                        ward = a.optString("ward", "General Ward"),
                        roomNo = a.optString("room_no", ""),
                        bedNo = a.optString("bed_no", ""),
                        specialty = a.optString("specialty", specialty),
                        assignedDoctor = a.optString("assigned_doctor", ""),
                        createdAt = a.optString("created_at", ""),
                        patientName = a.optString("patient_name", if (a.optString("patient_id").isNotBlank()) "Patient ${a.optString("patient_id")}" else "Patient"),
                        voiceText = a.optString("voice_text", ""),
                        pidRaw = a.optInt("pid_raw", 0)
                    )
                )
            }
            Result.success(list)
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching active alerts: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Fetches individual patient details with backend-enforced doctor specialty authorization.
     */
    suspend fun fetchPatientDetails(context: Context, patientId: String): Result<CriticalPatient> = withContext(Dispatchers.IO) {
        val doctorId = DoctorSession.getDoctorId(context)
            ?: return@withContext Result.failure(SecurityException("Session required: Doctor is not logged in."))
        val baseUrl = getBaseUrl(context)

        val url = "$baseUrl/api/v1/patients/$patientId?doctor_id=$doctorId"
        val request = Request.Builder().url(url).get().build()

        try {
            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: ""
            if (response.code == 403) {
                return@withContext Result.failure(SecurityException("403 Forbidden: Patient is not under authorized care of doctor $doctorId."))
            }
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("HTTP ${response.code}: $body"))
            }

            val json = JSONObject(body)
            val p = json.optJSONObject("patient")
                ?: return@withContext Result.failure(Exception("Missing patient object in response"))

            val reasonsList = mutableListOf<String>()
            val rArr = p.optJSONArray("reasons")
            if (rArr != null) {
                for (j in 0 until rArr.length()) reasonsList.add(rArr.getString(j))
            }

            val recList = mutableListOf<String>()
            val recArr = p.optJSONArray("recommendations")
            if (recArr != null) {
                for (k in 0 until recArr.length()) recList.add(recArr.getString(k))
            }

            val patient = CriticalPatient(
                patientId = p.optString("patient_id", patientId),
                pidRaw = p.optInt("pid_raw", 0),
                name = "${p.optString("first_name", "")} ${p.optString("last_name", "")}".trim(),
                heartRate = p.optInt("heart_rate", 0),
                spo2 = p.optDouble("spo2", 0.0),
                temperature = p.optDouble("temperature", 0.0),
                systolicBp = p.optInt("systolic_bp", 0),
                diastolicBp = p.optInt("diastolic_bp", 0),
                respiratoryRate = p.optInt("respiratory_rate", 0),
                ward = p.optString("ward", "General Ward"),
                roomNo = p.optString("room_no", "101"),
                bedNo = p.optString("bed_no", "1"),
                age = p.optInt("age", 40),
                gender = p.optString("gender", "Unknown"),
                severity = p.optString("severity", "NORMAL"),
                reasons = reasonsList,
                recommendations = recList,
                specialty = p.optString("specialty", "GENERAL MEDICINE"),
                assignedDoctorId = p.optString("assigned_doctor_id", doctorId),
                assignedDoctorName = p.optString("assigned_doctor_name", DoctorSession.getDoctorName(context) ?: "Doctor")
            )
            Result.success(patient)
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching patient details for $patientId: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Fetches authoritative monitoring summary metrics.
     * When doctor_id is provided, includes both doctor-scoped assigned metrics and hospital-wide totals.
     */
    suspend fun fetchHospitalSummary(context: Context): Result<MonitoringSummary> = withContext(Dispatchers.IO) {
        val doctorId = DoctorSession.getDoctorId(context) ?: "DOC001"
        val baseUrl = getBaseUrl(context)
        val url = "$baseUrl/api/v1/hospital/summary?doctor_id=$doctorId"
        val request = Request.Builder().url(url).get().build()

        try {
            val response = client.newCall(request).execute()
            val body = response.body?.string() ?: ""
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("HTTP ${response.code}: $body"))
            }

            val json = JSONObject(body)
            val assignedObj = json.optJSONObject("assigned_summary")
            val hospObj = json.optJSONObject("hospital_summary")

            val totalAssigned = assignedObj?.optInt("total_assigned", json.optInt("total_assigned", json.optInt("total_patients", 0)))
                ?: json.optInt("total_assigned", json.optInt("total_patients", 0))
            val criticalCount = assignedObj?.optInt("critical_count", json.optInt("critical_count", 0))
                ?: json.optInt("critical_count", 0)
            val moderateCount = assignedObj?.optInt("moderate_count", json.optInt("moderate_count", 0))
                ?: json.optInt("moderate_count", 0)
            val lowCount = assignedObj?.optInt("low_count", json.optInt("low_count", 0))
                ?: json.optInt("low_count", 0)
            val activeAlerts = assignedObj?.optInt("active_alerts_count", json.optInt("active_alerts_count", 0))
                ?: json.optInt("active_alerts_count", 0)

            val hospTotal = hospObj?.optInt("total_patients", json.optInt("total_patients", totalAssigned)) ?: totalAssigned
            val hospCritical = hospObj?.optInt("critical_count", criticalCount) ?: criticalCount
            val hospModerate = hospObj?.optInt("moderate_count", moderateCount) ?: moderateCount
            val hospLow = hospObj?.optInt("low_count", lowCount) ?: lowCount

            Result.success(
                MonitoringSummary(
                    totalAssigned = totalAssigned,
                    criticalCount = criticalCount,
                    moderateCount = moderateCount,
                    lowCount = lowCount,
                    activeAlertsCount = activeAlerts,
                    hospitalTotalPatients = hospTotal,
                    hospitalCriticalCount = hospCritical,
                    hospitalModerateCount = hospModerate,
                    hospitalLowCount = hospLow
                )
            )
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching hospital summary: ${e.message}")
            Result.failure(e)
        }
    }
}
