package org.medintel.doctor

import android.Manifest
import android.app.Dialog
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.text.method.PasswordTransformationMethod
import android.text.method.SingleLineTransformationMethod
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.medintel.doctor.data.AlertDeduplicator
import org.medintel.doctor.data.CriticalAlert
import org.medintel.doctor.data.CriticalPatient
import org.medintel.doctor.data.DoctorProfile
import org.medintel.doctor.data.DoctorSession
import org.medintel.doctor.data.MonitoringSummary
import org.medintel.doctor.network.MedIntelApiClient
import org.medintel.doctor.tts.MedIntelTTSManager
import java.text.SimpleDateFormat
import java.util.Date
import java.util.LinkedHashMap
import java.util.Locale

/**
 * Authoritative clinical patient card model for the real-time UI feed.
 * Keyed strictly by patient ID (e.g. pidRaw / P139) to guarantee zero card duplication.
 */
data class DisplayAlert(
    val alertId: String,
    val pidRaw: Int,
    val patientId: String,
    val patientName: String,
    val ward: String,
    val roomNo: String,
    val bedNo: String,
    val specialty: String,
    val assignedDoctor: String,
    val severity: String,
    val reason: String,
    val recommendation: String,
    val voiceText: String,
    val alertTime: String,
    val heartRate: Int? = null,
    val spo2: Double? = null,
    val systolicBp: Int? = null,
    val diastolicBp: Int? = null,
    val temperature: Double? = null,
    val respiratoryRate: Int? = null,
    val age: Int? = null,
    val gender: String? = null,
    val activeAlerts: List<CriticalAlert> = emptyList()
)

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "MedIntelMainActivity"
    }

    // Authoritative patient cards map: Keyed strictly by primary patient ID (e.g. 139)
    // Prevents duplicate cards for the same patient while unifying multiple alerts & vitals.
    private val patientCardsMap = LinkedHashMap<Int, DisplayAlert>()

    // Top Header & Status Views
    private lateinit var tvDoctorName: TextView
    private lateinit var tvDoctorRole: TextView
    private lateinit var btnSwitchDoctor: Button
    private lateinit var tvRegistrationStatus: TextView
    private lateinit var tvConnectionStatus: TextView
    private lateinit var viewConnectionDot: View
    private lateinit var llConnectionBadge: LinearLayout

    // Hospital & Specialty Summary Cards (Phase 2)
    private lateinit var tvTotalPatientsTitle: TextView
    private lateinit var tvTotalPatientsCount: TextView
    private lateinit var tvTotalPatientsSubtitle: TextView
    private lateinit var tvActiveAlertCount: TextView
    private lateinit var tvCriticalCount: TextView
    private lateinit var tvModerateCount: TextView
    private lateinit var tvStableCount: TextView

    // Voice Engine Controls
    private lateinit var tvVoiceEngineStatus: TextView
    private lateinit var btnTestVoice: Button
    private lateinit var btnRefreshTelemetry: Button

    // Latest Alert Banner
    private lateinit var tvLatestAlertBody: TextView
    private lateinit var tvLatestAlertTime: TextView

    // Critical Patient List Views
    private lateinit var tvLastSyncTime: TextView
    private lateinit var llCriticalPatientsContainer: LinearLayout
    private lateinit var llEmptyState: LinearLayout

    // Background Telemetry Polling Job
    private var telemetryJob: Job? = null

    private val alertReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent == null) return
            val alertId = intent.getStringExtra("alert_id") ?: "ALT-${System.currentTimeMillis()}"
            val targetDoctorId = intent.getStringExtra("doctor_id") ?: ""
            val specialty = intent.getStringExtra("specialty") ?: ""
            val patientIdStr = intent.getStringExtra("patient_id") ?: ""
            val pidRaw = patientIdStr.filter { it.isDigit() }.toIntOrNull() ?: 0
            val patientName = intent.getStringExtra("patient_name") ?: if (patientIdStr.isNotBlank()) "Patient $patientIdStr" else "Patient"
            val ward = intent.getStringExtra("ward") ?: "Ward"
            val roomNo = intent.getStringExtra("room_no") ?: ""
            val bedNo = intent.getStringExtra("bed_no") ?: ""
            val severity = intent.getStringExtra("severity") ?: "CRITICAL"
            val reason = intent.getStringExtra("reason") ?: "Critical threshold exceeded"
            val recommendation = intent.getStringExtra("recommendation") ?: "Immediate clinical attention required."
            val body = intent.getStringExtra("body") ?: "Critical alert: $patientName, $ward"
            val spokenText = intent.getStringExtra("spoken_text") ?: MedIntelTTSManager.buildConciseAlertText(patientName, ward, roomNo, bedNo, severity)

            val currentDoctorId = DoctorSession.getDoctorId(this@MainActivity) ?: ""
            val currentSpecialty = DoctorSession.getSpecialty(this@MainActivity) ?: ""
            val isReceptionist = DoctorSession.isReceptionist(this@MainActivity)

            // Strict Doctor Isolation check (Receptionist REC001 receives all hospital alerts)
            val isTargetDoctor = targetDoctorId.equals(currentDoctorId, ignoreCase = true)
            val isTargetSpecialty = specialty.equals(currentSpecialty, ignoreCase = true)
            if (!isReceptionist && !isTargetDoctor && !isTargetSpecialty && targetDoctorId.isNotBlank()) {
                Log.w(TAG, "Ignored alert $alertId: target=$targetDoctorId ($specialty) vs current=$currentDoctorId ($currentSpecialty)")
                return
            }

            Log.i(TAG, "Broadcast received in MainActivity: alert_id=$alertId, patient=$patientName (ID: $pidRaw)")
            val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            tvLatestAlertBody.text = body
            tvLatestAlertTime.text = timeStr

            // Deduplicated Voice Speech upon receiving critical broadcast
            if (severity.equals("CRITICAL", ignoreCase = true) && AlertDeduplicator.shouldProcessAlert(alertId)) {
                MedIntelTTSManager.getInstance(this@MainActivity).speakAlert(alertId, spokenText)
            }

            // Unify into patientCardsMap using authoritative primary key pidRaw
            synchronized(patientCardsMap) {
                val existing = patientCardsMap[pidRaw]
                val normalizedPid = if (patientIdStr.startsWith("P")) patientIdStr else "P$pidRaw"
                if (existing != null) {
                    val updatedReasons = if (existing.reason.isNotBlank() && !existing.reason.contains(reason)) "${existing.reason}, $reason" else reason
                    patientCardsMap[pidRaw] = existing.copy(
                        alertId = alertId,
                        reason = updatedReasons,
                        recommendation = recommendation,
                        alertTime = timeStr,
                        voiceText = spokenText
                    )
                } else {
                    patientCardsMap[pidRaw] = DisplayAlert(
                        alertId = alertId,
                        pidRaw = pidRaw,
                        patientId = normalizedPid,
                        patientName = patientName,
                        ward = ward,
                        roomNo = roomNo,
                        bedNo = bedNo,
                        specialty = specialty,
                        assignedDoctor = DoctorSession.getDoctorName(this@MainActivity) ?: "Doctor",
                        severity = severity,
                        reason = reason,
                        recommendation = recommendation,
                        voiceText = spokenText,
                        alertTime = timeStr
                    )
                }
            }

            renderAllAlertsAndPatients()

            // Trigger full telemetry refresh to enrich vitals and summary
            refreshDoctorTelemetry()
        }
    }

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            Log.i(TAG, "POST_NOTIFICATIONS permission granted.")
        } else {
            Log.w(TAG, "POST_NOTIFICATIONS permission denied by user.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        setupListeners()

        // Request POST_NOTIFICATIONS on Android 13+ (API 33+)
        checkNotificationPermission()

        // Initialize Android Native TextToSpeech Engine
        MedIntelTTSManager.getInstance(this)

        // Strict Authentication Gate: Prompt for login if no active session exists
        if (!DoctorSession.isLoggedIn(this)) {
            updateDoctorHeaderUI()
            showLoginDialog(isCancellable = false)
        } else {
            updateDoctorHeaderUI()
            fetchAndRegisterFcmToken()
            refreshDoctorTelemetry(isManualRefresh = false)
        }

        // Automatic connection health check on launch
        performAutoConnectionCheck()

        // Handle alert from notification intent if launched via notification click
        handleNotificationIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        updateTtsStatusIndicator()
        performAutoConnectionCheck()
        if (DoctorSession.isLoggedIn(this)) {
            fetchAndRegisterFcmToken()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleNotificationIntent(intent)
    }

    private fun initViews() {
        tvDoctorName = findViewById(R.id.tvDoctorName)
        tvDoctorRole = findViewById(R.id.tvDoctorRole)
        btnSwitchDoctor = findViewById(R.id.btnSwitchDoctor)
        tvRegistrationStatus = findViewById(R.id.tvRegistrationStatus)
        tvConnectionStatus = findViewById(R.id.tvConnectionStatus)
        viewConnectionDot = findViewById(R.id.viewConnectionDot)
        llConnectionBadge = findViewById(R.id.llConnectionBadge)

        tvTotalPatientsTitle = findViewById(R.id.tvTotalPatientsTitle)
        tvTotalPatientsCount = findViewById(R.id.tvTotalPatientsCount)
        tvTotalPatientsSubtitle = findViewById(R.id.tvTotalPatientsSubtitle)
        tvActiveAlertCount = findViewById(R.id.tvActiveAlertCount)
        tvCriticalCount = findViewById(R.id.tvCriticalCount)
        tvModerateCount = findViewById(R.id.tvModerateCount)
        tvStableCount = findViewById(R.id.tvStableCount)

        tvVoiceEngineStatus = findViewById(R.id.tvVoiceEngineStatus)
        btnTestVoice = findViewById(R.id.btnTestVoice)
        btnRefreshTelemetry = findViewById(R.id.btnRefreshTelemetry)

        tvLatestAlertBody = findViewById(R.id.tvLatestAlertBody)
        tvLatestAlertTime = findViewById(R.id.tvLatestAlertTime)

        tvLastSyncTime = findViewById(R.id.tvLastSyncTime)
        llCriticalPatientsContainer = findViewById(R.id.llCriticalPatientsContainer)
        llEmptyState = findViewById(R.id.llEmptyState)
    }

    private fun setupListeners() {
        btnSwitchDoctor.setOnClickListener {
            showLogoutOrSwitchDialog()
        }

        llConnectionBadge.setOnClickListener {
            showServerSettingsDialog()
        }

        btnRefreshTelemetry.setOnClickListener {
            refreshDoctorTelemetry(isManualRefresh = true)
        }

        btnTestVoice.setOnClickListener {
            val specialty = DoctorSession.getSpecialty(this) ?: "CARDIOLOGY"
            val ward = if (specialty == "CARDIOLOGY") "Cardiology Ward" else if (specialty == "PULMONOLOGY") "Pulmonology ICU" else "General Medicine Ward"
            val sampleAlert = MedIntelTTSManager.buildConciseAlertText("Rahul Patil", ward, "201", "1", "Critical")

            val testAlertId = "TEST-ALT-${System.currentTimeMillis()}"
            val spoken = MedIntelTTSManager.getInstance(this).speakAlert(testAlertId, sampleAlert)
            val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            tvLatestAlertBody.text = "TEST VOICE ALERT: $sampleAlert"
            tvLatestAlertTime.text = timeStr

            if (spoken) {
                Toast.makeText(this, "Voice alert enqueued to native TTS", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "TTS engine initializing or busy", Toast.LENGTH_SHORT).show()
            }
            updateTtsStatusIndicator()
        }
    }

    private fun updateTtsStatusIndicator() {
        val ttsReady = MedIntelTTSManager.getInstance(this).isEngineReady()
        if (ttsReady) {
            tvVoiceEngineStatus.text = "TTS: READY"
            tvVoiceEngineStatus.setTextColor(ContextCompat.getColor(this, R.color.low_green))
        } else {
            tvVoiceEngineStatus.text = "TTS: STANDBY"
            tvVoiceEngineStatus.setTextColor(ContextCompat.getColor(this, R.color.moderate_amber))
        }
    }

    private fun performAutoConnectionCheck() {
        CoroutineScope(Dispatchers.Main).launch {
            val isHealthy = MedIntelApiClient.checkBackendHealth(this@MainActivity)
            if (isHealthy) {
                tvConnectionStatus.text = "ONLINE"
                tvConnectionStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                viewConnectionDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
            } else {
                tvConnectionStatus.text = "OFFLINE"
                tvConnectionStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                viewConnectionDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
            }
        }
    }

    private fun updateDoctorHeaderUI() {
        val isLoggedIn = DoctorSession.isLoggedIn(this)
        if (isLoggedIn) {
            val doctorName = DoctorSession.getDoctorName(this) ?: "Doctor"
            val doctorId = DoctorSession.getDoctorId(this) ?: "DOC001"
            val specialty = DoctorSession.getSpecialty(this) ?: "CARDIOLOGY"
            val isReceptionist = DoctorSession.isReceptionist(this)

            tvDoctorName.text = doctorName
            if (isReceptionist) {
                tvDoctorRole.text = "$doctorId • HOSPITAL RECEPTION"
                tvDoctorRole.setTextColor(ContextCompat.getColor(this, R.color.info_cyan))
                tvTotalPatientsTitle.text = "HOSPITAL CENSUS"
                tvTotalPatientsSubtitle.text = "All active inpatients"
            } else {
                tvDoctorRole.text = "$doctorId • $specialty"
                tvDoctorRole.setTextColor(ContextCompat.getColor(this, R.color.accent_blue))
                tvTotalPatientsTitle.text = "ASSIGNED PATIENTS"
                tvTotalPatientsSubtitle.text = "Assigned to your care"
            }
            btnSwitchDoctor.text = "Sign Out / Switch"
        } else {
            tvDoctorName.text = "Not Authenticated"
            tvDoctorRole.text = "Sign in to access patient records"
            tvDoctorRole.setTextColor(ContextCompat.getColor(this, R.color.text_muted))
            btnSwitchDoctor.text = "Sign In"
            tvTotalPatientsTitle.text = "ASSIGNED PATIENTS"
            tvTotalPatientsSubtitle.text = "Sign in required"
        }
        updateTtsStatusIndicator()
    }

    /**
     * Professional Clinical Login Dialog (Phase 3).
     * Provides quick selection for authoritative doctors and receptionist, PIN show/hide toggle,
     * progress indicator, and automatic connection testing without requiring manual test button clicks.
     */
    private fun showLoginDialog(isCancellable: Boolean = true) {
        val dialog = Dialog(this)
        dialog.setContentView(R.layout.dialog_login)
        dialog.window?.setLayout(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        dialog.setCancelable(isCancellable)

        // View bindings
        val viewServerDot = dialog.findViewById<View>(R.id.viewServerDot)
        val tvServerStatusPill = dialog.findViewById<TextView>(R.id.tvServerStatusPill)
        val chipDoc1 = dialog.findViewById<Button>(R.id.chipDoc1)
        val chipDoc2 = dialog.findViewById<Button>(R.id.chipDoc2)
        val chipDoc3 = dialog.findViewById<Button>(R.id.chipDoc3)
        val chipRec1 = dialog.findViewById<Button>(R.id.chipRec1)
        val etDoctorId = dialog.findViewById<EditText>(R.id.etDoctorId)
        val etPassword = dialog.findViewById<EditText>(R.id.etPassword)
        val btnTogglePassword = dialog.findViewById<Button>(R.id.btnTogglePassword)
        val tvLoginError = dialog.findViewById<TextView>(R.id.tvLoginError)
        val btnLoginSubmit = dialog.findViewById<Button>(R.id.btnLoginSubmit)
        val pbLoginProgress = dialog.findViewById<ProgressBar>(R.id.pbLoginProgress)

        // Expandable Server Settings
        val llServerSettingsHeader = dialog.findViewById<LinearLayout>(R.id.llServerSettingsHeader)
        val tvServerSettingsToggle = dialog.findViewById<TextView>(R.id.tvServerSettingsToggle)
        val llServerSettingsContent = dialog.findViewById<LinearLayout>(R.id.llServerSettingsContent)
        val etServerUrl = dialog.findViewById<EditText>(R.id.etServerUrl)
        val btnTestServer = dialog.findViewById<Button>(R.id.btnTestServer)
        val tvServerStatus = dialog.findViewById<TextView>(R.id.tvServerStatus)

        val activeUrl = DoctorSession.getBackendUrl(this)
        etServerUrl.setText(activeUrl)

        // Automatic connection verification on dialog launch
        CoroutineScope(Dispatchers.Main).launch {
            val isOnline = MedIntelApiClient.checkBackendHealth(this@MainActivity, activeUrl)
            if (isOnline) {
                viewServerDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                tvServerStatusPill.text = "Online"
                tvServerStatusPill.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                tvServerStatus.text = "Status: Connected ($activeUrl)"
                tvServerStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
            } else {
                viewServerDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                tvServerStatusPill.text = "Offline"
                tvServerStatusPill.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                tvServerStatus.text = "Status: Unreachable ($activeUrl)"
                tvServerStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
            }
        }

        // Toggle Password Show / Hide
        var isPasswordVisible = false
        btnTogglePassword.setOnClickListener {
            isPasswordVisible = !isPasswordVisible
            if (isPasswordVisible) {
                etPassword.transformationMethod = SingleLineTransformationMethod.getInstance()
                btnTogglePassword.text = "HIDE"
            } else {
                etPassword.transformationMethod = PasswordTransformationMethod.getInstance()
                btnTogglePassword.text = "SHOW"
            }
            etPassword.setSelection(etPassword.text.length)
        }

        // Quick Clinical Identity Selection Chips
        chipDoc1.setOnClickListener {
            etDoctorId.setText("DOC001")
            etPassword.setText("1025")
            tvLoginError.visibility = View.GONE
        }
        chipDoc2.setOnClickListener {
            etDoctorId.setText("DOC002")
            etPassword.setText("4912")
            tvLoginError.visibility = View.GONE
        }
        chipDoc3.setOnClickListener {
            etDoctorId.setText("DOC003")
            etPassword.setText("1503")
            tvLoginError.visibility = View.GONE
        }
        chipRec1.setOnClickListener {
            etDoctorId.setText("REC001")
            etPassword.setText("0821")
            tvLoginError.visibility = View.GONE
        }

        // Expandable Server Settings Toggle
        var isServerSettingsExpanded = false
        llServerSettingsHeader.setOnClickListener {
            isServerSettingsExpanded = !isServerSettingsExpanded
            llServerSettingsContent.visibility = if (isServerSettingsExpanded) View.VISIBLE else View.GONE
            tvServerSettingsToggle.text = if (isServerSettingsExpanded) "▲ Close" else "▼ Configure"
        }

        btnTestServer.setOnClickListener {
            val candidateUrl = etServerUrl.text.toString().trim()
            if (candidateUrl.isBlank()) {
                tvServerStatus.text = "Error: Address cannot be empty."
                tvServerStatus.setTextColor(ContextCompat.getColor(this, R.color.critical_red))
                return@setOnClickListener
            }
            tvServerStatus.text = "Testing connection..."
            tvServerStatus.setTextColor(ContextCompat.getColor(this, R.color.moderate_amber))

            CoroutineScope(Dispatchers.Main).launch {
                val ok = MedIntelApiClient.checkBackendHealth(this@MainActivity, candidateUrl)
                if (ok) {
                    DoctorSession.setBackendUrl(this@MainActivity, candidateUrl)
                    viewServerDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                    tvServerStatusPill.text = "Online"
                    tvServerStatusPill.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                    tvServerStatus.text = "✓ Server Online ($candidateUrl)"
                    tvServerStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                } else {
                    viewServerDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                    tvServerStatusPill.text = "Offline"
                    tvServerStatusPill.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                    tvServerStatus.text = "✗ Unreachable (Ensure 'adb reverse tcp:8000 tcp:8000' is active)"
                    tvServerStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                }
            }
        }

        // Primary Sign In Click Handler (Direct login without mandatory manual testing)
        btnLoginSubmit.setOnClickListener {
            val docId = etDoctorId.text.toString().trim()
            val password = etPassword.text.toString().trim()
            val candidateServer = etServerUrl.text.toString().trim()

            if (docId.isBlank() || password.isBlank()) {
                tvLoginError.text = "Please enter Clinical Account ID and PIN."
                tvLoginError.visibility = View.VISIBLE
                return@setOnClickListener
            }

            if (candidateServer.isNotBlank()) {
                DoctorSession.setBackendUrl(this, candidateServer)
            }

            tvLoginError.visibility = View.GONE
            btnLoginSubmit.isEnabled = false
            pbLoginProgress.visibility = View.VISIBLE

            CoroutineScope(Dispatchers.Main).launch {
                val result = MedIntelApiClient.loginDoctor(this@MainActivity, docId, password)
                btnLoginSubmit.isEnabled = true
                pbLoginProgress.visibility = View.GONE

                if (result.isSuccess) {
                    val profile = result.getOrThrow()
                    Toast.makeText(this@MainActivity, "Authenticated as ${profile.name}", Toast.LENGTH_SHORT).show()
                    dialog.dismiss()

                    updateDoctorHeaderUI()
                    fetchAndRegisterFcmToken()
                    refreshDoctorTelemetry(isManualRefresh = true)
                } else {
                    val err = result.exceptionOrNull()?.message ?: "Authentication failed"
                    tvLoginError.text = "Login Failed: $err"
                    tvLoginError.visibility = View.VISIBLE
                }
            }
        }

        dialog.show()
    }

    private fun showLogoutOrSwitchDialog() {
        val isLoggedIn = DoctorSession.isLoggedIn(this)
        val items = if (isLoggedIn) {
            arrayOf("Switch Account", "Server Address Settings", "Sign Out")
        } else {
            arrayOf("Sign In", "Server Address Settings")
        }

        AlertDialog.Builder(this)
            .setTitle(if (isLoggedIn) "Clinical Session Management" else "Access Portal")
            .setItems(items) { _, which ->
                val choice = items[which]
                when {
                    choice.contains("Sign In") || choice.contains("Switch") -> {
                        showLoginDialog(isCancellable = true)
                    }
                    choice.contains("Server Address") -> {
                        showServerSettingsDialog()
                    }
                    choice.contains("Sign Out") -> {
                        // Phase 7: Clear all session, alert, and clinical patient data on logout
                        DoctorSession.clearSession(this)
                        synchronized(patientCardsMap) {
                            patientCardsMap.clear()
                        }
                        AlertDeduplicator.clearAll()
                        MedIntelTTSManager.getInstance(this).stop()
                        MedIntelTTSManager.getInstance(this).clearSpokenHistory()

                        llCriticalPatientsContainer.removeAllViews()
                        tvTotalPatientsCount.text = "--"
                        tvCriticalCount.text = "0"
                        tvModerateCount.text = "0"
                        tvStableCount.text = "0"
                        tvActiveAlertCount.text = "0"
                        tvLatestAlertBody.text = "User signed out. Patient data cleared."
                        updateDoctorHeaderUI()
                        renderAllAlertsAndPatients()
                        Toast.makeText(this, "Signed out successfully", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showServerSettingsDialog() {
        val input = EditText(this).apply {
            setText(DoctorSession.getBackendUrl(this@MainActivity))
            typeface = android.graphics.Typeface.MONOSPACE
            setSingleLine(true)
        }

        AlertDialog.Builder(this)
            .setTitle("FastAPI Server Address")
            .setMessage("Configure server URL (USB: http://127.0.0.1:8000 via adb reverse, or Wi-Fi IP):")
            .setView(input)
            .setPositiveButton("Save & Connect") { _, _ ->
                val newUrl = input.text.toString().trim()
                if (newUrl.isNotBlank()) {
                    DoctorSession.setBackendUrl(this, newUrl)
                    performAutoConnectionCheck()
                    refreshDoctorTelemetry(isManualRefresh = true)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /**
     * Refreshes hospital summary, active alerts, and critical patient census.
     * Enforces strict doctor specialty isolation and prevents patient card duplication.
     */
    private fun refreshDoctorTelemetry(isManualRefresh: Boolean = false) {
        if (!DoctorSession.isLoggedIn(this)) {
            tvConnectionStatus.text = "LOCKED"
            tvConnectionStatus.setTextColor(ContextCompat.getColor(this, R.color.text_muted))
            viewConnectionDot.setBackgroundColor(ContextCompat.getColor(this, R.color.text_faint))
            llCriticalPatientsContainer.removeAllViews()
            llEmptyState.visibility = View.VISIBLE
            return
        }

        CoroutineScope(Dispatchers.Main).launch {
            val isHealthy = MedIntelApiClient.checkBackendHealth(this@MainActivity)
            if (isHealthy) {
                tvConnectionStatus.text = "ONLINE"
                tvConnectionStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                viewConnectionDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
            } else {
                tvConnectionStatus.text = "OFFLINE"
                tvConnectionStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                viewConnectionDot.setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.critical_red))
                if (isManualRefresh) {
                    Toast.makeText(this@MainActivity, "Server offline at ${DoctorSession.getBackendUrl(this@MainActivity)}", Toast.LENGTH_LONG).show()
                }
                return@launch
            }

            val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            tvLastSyncTime.text = timeStr

            // Parallel async requests: Summary counts, critical patients, active alerts
            val summaryResult = MedIntelApiClient.fetchHospitalSummary(this@MainActivity)
            val patientResult = MedIntelApiClient.fetchCriticalPatients(this@MainActivity)
            val alertResult = MedIntelApiClient.fetchActiveAlerts(this@MainActivity)

            // 1. Phase 2: Update Hospital Summary Cards with backend values
            if (summaryResult.isSuccess) {
                val summary = summaryResult.getOrThrow()
                val isReceptionist = DoctorSession.isReceptionist(this@MainActivity)
                if (isReceptionist) {
                    tvTotalPatientsCount.text = summary.hospitalTotalPatients.toString()
                    tvCriticalCount.text = summary.hospitalCriticalCount.toString()
                    tvModerateCount.text = summary.hospitalModerateCount.toString()
                    tvStableCount.text = summary.hospitalLowCount.toString()
                    tvActiveAlertCount.text = summary.activeAlertsCount.toString()
                } else {
                    tvTotalPatientsCount.text = summary.totalAssigned.toString()
                    tvCriticalCount.text = summary.criticalCount.toString()
                    tvModerateCount.text = summary.moderateCount.toString()
                    tvStableCount.text = summary.lowCount.toString()
                    tvActiveAlertCount.text = summary.activeAlertsCount.toString()
                }
            }

            // 2. Sequential FIFO voice processing for active critical alerts
            val backendAlerts = if (alertResult.isSuccess) alertResult.getOrDefault(emptyList()) else emptyList()
            val sortedAlerts = backendAlerts.sortedBy { it.createdAt }
            for (a in sortedAlerts) {
                if (a.severity.equals("CRITICAL", ignoreCase = true) && a.alertId.isNotBlank()) {
                    if (AlertDeduplicator.shouldProcessAlert(a.alertId)) {
                        val spokenText = if (a.voiceText.isNotBlank()) a.voiceText else MedIntelTTSManager.buildConciseAlertText(
                            patientName = a.patientName,
                            ward = a.ward,
                            roomNo = a.roomNo,
                            bedNo = a.bedNo,
                            severity = a.severity
                        )
                        val nowMs = System.currentTimeMillis()
                        Log.i(TAG, "[ANDROID TTS POLLING] Enqueuing critical alert for speech: alert_id = ${a.alertId}, patient = ${a.patientName}, received_at = $nowMs")
                        MedIntelTTSManager.getInstance(this@MainActivity).speakAlert(
                            alertId = a.alertId,
                            text = spokenText,
                            alertCreatedAt = a.createdAt
                        )
                    }
                }
            }

            // 3. Phase 1: Unify critical patients and active alerts by primary key pidRaw
            val newPatientCards = LinkedHashMap<Int, DisplayAlert>()
            val alertsByPid = backendAlerts.groupBy { if (it.pidRaw > 0) it.pidRaw else it.patientId.filter { ch -> ch.isDigit() }.toIntOrNull() ?: 0 }

            // A. Populate from critical patients (authoritative patient records with live vitals)
            if (patientResult.isSuccess) {
                val patients = patientResult.getOrDefault(emptyList())
                for (p in patients) {
                    val pid = p.pidRaw
                    val patientAlerts = alertsByPid[pid] ?: emptyList()
                    val primaryAlert = patientAlerts.firstOrNull()
                    val effectiveAlertId = primaryAlert?.alertId ?: "ALT-P$pid"
                    val spokenText = primaryAlert?.voiceText?.ifBlank { null }
                        ?: MedIntelTTSManager.buildConciseAlertText(p.name, p.ward, p.roomNo, p.bedNo, p.severity)
                    val mergedReason = if (primaryAlert != null && p.reasons.isNotEmpty()) {
                        val combined = (p.reasons + primaryAlert.reason).distinct().filter { it.isNotBlank() }
                        combined.joinToString(", ")
                    } else if (p.reasons.isNotEmpty()) {
                        p.reasons.joinToString(", ")
                    } else {
                        primaryAlert?.reason ?: "Critical vital signs threshold breached"
                    }

                    newPatientCards[pid] = DisplayAlert(
                        alertId = effectiveAlertId,
                        pidRaw = pid,
                        patientId = p.patientId,
                        patientName = p.name, // Authoritative name from database (e.g. "Ronith Chander")
                        ward = p.ward,
                        roomNo = p.roomNo,
                        bedNo = p.bedNo,
                        specialty = p.specialty,
                        assignedDoctor = p.assignedDoctorName,
                        severity = p.severity,
                        reason = mergedReason,
                        recommendation = if (p.recommendations.isNotEmpty()) p.recommendations.first() else (primaryAlert?.recommendation ?: "Immediate bedside evaluation recommended."),
                        voiceText = spokenText,
                        alertTime = primaryAlert?.createdAt?.takeLast(8) ?: timeStr,
                        heartRate = p.heartRate,
                        spo2 = p.spo2,
                        systolicBp = p.systolicBp,
                        diastolicBp = p.diastolicBp,
                        temperature = p.temperature,
                        respiratoryRate = p.respiratoryRate,
                        age = p.age,
                        gender = p.gender,
                        activeAlerts = patientAlerts
                    )
                }
            }

            // B. Enrich with active alerts from backend not in critical list (e.g. recovering vitals)
            for (a in backendAlerts) {
                val pid = if (a.pidRaw > 0) a.pidRaw else a.patientId.filter { it.isDigit() }.toIntOrNull() ?: 0
                if (!newPatientCards.containsKey(pid)) {
                    val pName = if (a.patientName.isNotBlank()) a.patientName else "Patient ${a.patientId}"
                    val normPid = if (a.patientId.startsWith("P")) a.patientId else "P$pid"
                    newPatientCards[pid] = DisplayAlert(
                        alertId = a.alertId,
                        pidRaw = pid,
                        patientId = normPid,
                        patientName = pName,
                        ward = a.ward,
                        roomNo = a.roomNo,
                        bedNo = a.bedNo,
                        specialty = a.specialty,
                        assignedDoctor = a.assignedDoctor,
                        severity = a.severity,
                        reason = a.reason,
                        recommendation = a.recommendation,
                        voiceText = a.voiceText,
                        alertTime = if (a.createdAt.isNotBlank()) a.createdAt.takeLast(8) else timeStr,
                        activeAlerts = listOf(a)
                    )
                }
            }

            synchronized(patientCardsMap) {
                patientCardsMap.clear()
                patientCardsMap.putAll(newPatientCards)
            }

            renderAllAlertsAndPatients()

            if (isManualRefresh) {
                Toast.makeText(this@MainActivity, "Telemetry updated: ${patientCardsMap.size} critical patient(s)", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun renderAllAlertsAndPatients() {
        llCriticalPatientsContainer.removeAllViews()

        if (patientCardsMap.isEmpty()) {
            llEmptyState.visibility = View.VISIBLE
            return
        }

        llEmptyState.visibility = View.GONE
        val inflater = LayoutInflater.from(this)

        for ((_, item) in patientCardsMap) {
            val cardView = inflater.inflate(R.layout.item_critical_patient, llCriticalPatientsContainer, false)

            val tvCardPatientName = cardView.findViewById<TextView>(R.id.tvCardPatientName)
            val tvCardPatientMeta = cardView.findViewById<TextView>(R.id.tvCardPatientMeta)
            val tvCardSeverityBadge = cardView.findViewById<TextView>(R.id.tvCardSeverityBadge)
            val tvCardWardSpecialty = cardView.findViewById<TextView>(R.id.tvCardWardSpecialty)
            val tvCardVitalHr = cardView.findViewById<TextView>(R.id.tvCardVitalHr)
            val tvCardVitalSpo2 = cardView.findViewById<TextView>(R.id.tvCardVitalSpo2)
            val tvCardVitalBp = cardView.findViewById<TextView>(R.id.tvCardVitalBp)
            val tvCardVitalTemp = cardView.findViewById<TextView>(R.id.tvCardVitalTemp)
            val tvCardVitalRr = cardView.findViewById<TextView>(R.id.tvCardVitalRr)
            val tvCardReasons = cardView.findViewById<TextView>(R.id.tvCardReasons)
            val tvCardRecommendation = cardView.findViewById<TextView>(R.id.tvCardRecommendation)

            tvCardPatientName.text = item.patientName
            val loc = if (item.roomNo.isNotBlank() && item.bedNo.isNotBlank()) "Room ${item.roomNo} Bed ${item.bedNo}" else item.ward
            val ageGender = if (item.age != null && item.gender != null) "${item.age}Y ${item.gender} • " else ""
            tvCardPatientMeta.text = "ID: ${item.patientId} • $ageGender$loc"
            tvCardSeverityBadge.text = "▲ ${item.severity.uppercase()}"
            tvCardWardSpecialty.text = "${item.ward} • Assigned: ${item.assignedDoctor}"

            if (item.heartRate != null) {
                tvCardVitalHr.text = "${item.heartRate}"
                tvCardVitalSpo2.text = "${item.spo2?.toInt() ?: "--"}%"
                tvCardVitalBp.text = "${item.systolicBp ?: "--"}/${item.diastolicBp ?: "--"}"
                tvCardVitalTemp.text = item.temperature?.let { String.format(Locale.US, "%.1f°", it) } ?: "--"
                tvCardVitalRr.text = "${item.respiratoryRate ?: "--"}"
            } else {
                tvCardVitalHr.text = "--"
                tvCardVitalSpo2.text = "--"
                tvCardVitalBp.text = "--"
                tvCardVitalTemp.text = "--"
                tvCardVitalRr.text = "--"
            }

            tvCardReasons.text = item.reason.ifBlank { "Critical vital thresholds breached" }
            tvCardRecommendation.text = item.recommendation.ifBlank { "Immediate clinical evaluation required." }

            cardView.setOnClickListener {
                showDisplayAlertReviewDialog(item)
            }

            llCriticalPatientsContainer.addView(cardView)
        }
    }

    private fun handleNotificationIntent(intent: Intent?) {
        if (intent == null) return
        val alertId = intent.getStringExtra("alert_id") ?: return
        val patientIdStr = intent.getStringExtra("patient_id") ?: return
        val pidRaw = patientIdStr.filter { it.isDigit() }.toIntOrNull() ?: 0
        val patientName = intent.getStringExtra("patient_name") ?: "Patient $patientIdStr"
        val ward = intent.getStringExtra("ward") ?: "ICU"
        val roomNo = intent.getStringExtra("room_no") ?: "201"
        val bedNo = intent.getStringExtra("bed_no") ?: "1"
        val severity = intent.getStringExtra("severity") ?: "CRITICAL"
        val reason = intent.getStringExtra("reason") ?: "Critical threshold exceeded"
        val recommendation = intent.getStringExtra("recommendation") ?: "Immediate clinical attention required."
        val voiceText = intent.getStringExtra("voice_text") ?: MedIntelTTSManager.buildConciseAlertText(patientName, ward, roomNo, bedNo, severity)
        val timeStr = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())

        val displayAlert = DisplayAlert(
            alertId = alertId,
            pidRaw = pidRaw,
            patientId = patientIdStr,
            patientName = patientName,
            ward = ward,
            roomNo = roomNo,
            bedNo = bedNo,
            specialty = intent.getStringExtra("specialty") ?: "CARDIOLOGY",
            assignedDoctor = DoctorSession.getDoctorName(this) ?: "Doctor",
            severity = severity,
            reason = reason,
            recommendation = recommendation,
            voiceText = voiceText,
            alertTime = timeStr
        )

        synchronized(patientCardsMap) {
            patientCardsMap[pidRaw] = displayAlert
        }
        renderAllAlertsAndPatients()
        showDisplayAlertReviewDialog(displayAlert)
    }

    private fun showDisplayAlertReviewDialog(item: DisplayAlert) {
        val dialog = Dialog(this)
        dialog.setContentView(R.layout.dialog_patient_detail)
        dialog.window?.setLayout(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)

        val tvModalPatientName = dialog.findViewById<TextView>(R.id.tvModalPatientName)
        val tvModalPatientLocation = dialog.findViewById<TextView>(R.id.tvModalPatientLocation)
        val tvModalSeverity = dialog.findViewById<TextView>(R.id.tvModalSeverity)
        val tvModalVitals = dialog.findViewById<TextView>(R.id.tvModalVitals)
        val tvModalAlertTime = dialog.findViewById<TextView>(R.id.tvModalAlertTime)
        val tvModalReason = dialog.findViewById<TextView>(R.id.tvModalReason)
        val tvModalRecommendation = dialog.findViewById<TextView>(R.id.tvModalRecommendation)
        val tvModalVoiceText = dialog.findViewById<TextView>(R.id.tvModalVoiceText)
        val btnModalSpeak = dialog.findViewById<Button>(R.id.btnModalSpeak)
        val btnModalDismiss = dialog.findViewById<Button>(R.id.btnModalDismiss)

        tvModalPatientName.text = item.patientName
        val loc = if (item.roomNo.isNotBlank() && item.bedNo.isNotBlank()) "Room ${item.roomNo} Bed ${item.bedNo}" else item.ward
        tvModalPatientLocation.text = "${item.ward} • $loc • ID: ${item.patientId}"
        tvModalSeverity.text = item.severity.uppercase()
        tvModalVitals.text = if (item.heartRate != null) {
            "HR: ${item.heartRate} bpm • SpO2: ${item.spo2?.toInt() ?: "--"}% • BP: ${item.systolicBp ?: "--"}/${item.diastolicBp ?: "--"} mmHg • Temp: ${item.temperature?.let { String.format(Locale.US, "%.1f°", it) } ?: "--"} • RR: ${item.respiratoryRate ?: "--"}/min"
        } else {
            "Emergency critical alert dispatched via FCM real-time channel."
        }
        tvModalAlertTime.text = "Alert Time: ${item.alertTime}"
        tvModalReason.text = item.reason.ifBlank { "Critical vital signs threshold breached" }
        tvModalRecommendation.text = item.recommendation.ifBlank { "Immediate clinical attention required." }
        tvModalVoiceText.text = "Voice: \"${item.voiceText}\""

        btnModalSpeak.setOnClickListener {
            MedIntelTTSManager.getInstance(this).speakAlert("REPEAT-${System.currentTimeMillis()}", item.voiceText)
        }

        btnModalDismiss.setOnClickListener {
            dialog.dismiss()
        }

        dialog.show()
    }

    private fun checkNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun fetchAndRegisterFcmToken() {
        if (!DoctorSession.isLoggedIn(this)) return

        try {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    val token = task.result
                    val masked = if (token.length > 10) "${token.take(6)}...${token.takeLast(4)}" else "***"
                    DoctorSession.saveFcmToken(this, token)

                    CoroutineScope(Dispatchers.Main).launch {
                        val regResult = MedIntelApiClient.registerDevice(applicationContext, token)
                        if (regResult.isSuccess) {
                            tvRegistrationStatus.text = "FCM Status: Active ($masked)"
                            tvRegistrationStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.low_green))
                        } else {
                            tvRegistrationStatus.text = "FCM Status: Standby ($masked)"
                            tvRegistrationStatus.setTextColor(ContextCompat.getColor(this@MainActivity, R.color.moderate_amber))
                        }
                    }
                } else {
                    tvRegistrationStatus.text = "FCM Status: Offline Mode"
                    tvRegistrationStatus.setTextColor(ContextCompat.getColor(this, R.color.text_muted))
                    Log.w(TAG, "FCM token retrieval note: ${task.exception?.message}")
                }
            }
        } catch (e: Exception) {
            tvRegistrationStatus.text = "FCM Status: Standby"
            tvRegistrationStatus.setTextColor(ContextCompat.getColor(this, R.color.text_muted))
            Log.i(TAG, "FCM initialization note: ${e.message}")
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter("org.medintel.doctor.CRITICAL_ALERT")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(alertReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(alertReceiver, filter)
        }

        // Start background polling every 5 seconds while activity is in foreground
        telemetryJob = CoroutineScope(Dispatchers.Main).launch {
            while (isActive) {
                if (DoctorSession.isLoggedIn(this@MainActivity)) {
                    refreshDoctorTelemetry()
                }
                delay(5000)
            }
        }
    }

    override fun onStop() {
        super.onStop()
        telemetryJob?.cancel()
        try {
            unregisterReceiver(alertReceiver)
        } catch (e: Exception) {
            // Safe ignore
        }
    }
}
