package org.medintel.doctor.fcm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.medintel.doctor.MainActivity
import org.medintel.doctor.R
import org.medintel.doctor.data.AlertDeduplicator
import org.medintel.doctor.data.DoctorSession
import org.medintel.doctor.network.MedIntelApiClient
import org.medintel.doctor.tts.MedIntelTTSManager

/**
 * MedIntel Doctor Firebase Cloud Messaging Service.
 * Handles background & foreground CRITICAL_ALERT pushes, enforces doctor isolation,
 * generates high-priority notifications, and triggers immediate local Android Native TextToSpeech.
 */
class MedIntelFirebaseMessagingService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "MedIntelFCM"
        const val CHANNEL_ID = "medintel_critical_alerts"
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        val masked = if (token.length > 10) "${token.take(6)}...${token.takeLast(4)}" else "***"
        Log.i(TAG, "New FCM Registration Token obtained: $masked")
        DoctorSession.saveFcmToken(applicationContext, token)
        if (DoctorSession.isLoggedIn(applicationContext)) {
            CoroutineScope(Dispatchers.IO).launch {
                MedIntelApiClient.registerDevice(applicationContext, token)
            }
        }
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)
        Log.i(TAG, "FCM Message received from: ${remoteMessage.from}")

        val data = remoteMessage.data
        if (data.isEmpty()) {
            Log.w(TAG, "Received FCM message without data payload.")
            return
        }

        val type = data["type"] ?: "CRITICAL_ALERT"
        if (type != "CRITICAL_ALERT") {
            Log.i(TAG, "Ignored non-critical message type: $type")
            return
        }

        // Check if device has an authenticated session
        if (!DoctorSession.isLoggedIn(applicationContext)) {
            Log.w(TAG, "[DOCTOR ISOLATION] Suppressed alert push: Device has no authenticated doctor session.")
            return
        }

        // 1. Extract verified payload fields
        val alertId = data["alert_id"] ?: "ALT-${data["patient_id"] ?: System.currentTimeMillis()}"
        val targetDoctorId = data["doctor_id"]?.trim()?.uppercase() ?: "DOC001"
        val specialty = data["specialty"]?.trim()?.uppercase() ?: "CARDIOLOGY"
        val patientId = data["patient_id"] ?: "Unknown"
        val patientName = data["patient_name"] ?: "Patient $patientId"
        val ward = data["ward"] ?: "ICU"
        val roomNo = data["room_no"] ?: "201"
        val bedNo = data["bed_no"] ?: "1"
        val severity = data["severity"] ?: "Critical"
        val reason = data["reason"] ?: ""
        val recommendation = data["recommendation"] ?: ""

        val currentDoctorId = DoctorSession.getDoctorId(applicationContext)?.trim()?.uppercase() ?: ""
        val currentSpecialty = DoctorSession.getSpecialty(applicationContext)?.trim()?.uppercase() ?: ""
        val isReceptionist = DoctorSession.isReceptionist(applicationContext)

        // 2. Doctor Isolation Enforcement:
        // Do not broadcast or process a doctor's alert if targeted to another doctor.
        val matchesDoctor = targetDoctorId.equals(currentDoctorId, ignoreCase = true)
        val matchesSpecialty = specialty.equals(currentSpecialty, ignoreCase = true)
        if (!isReceptionist && !matchesDoctor && !matchesSpecialty) {
            Log.w(
                TAG,
                "[DOCTOR ISOLATION] Suppressed alert $alertId. Target is $targetDoctorId ($specialty), but device is logged in as $currentDoctorId ($currentSpecialty)."
            )
            return
        }

        val wardClean = if (!ward.lowercase().contains("ward") && !ward.lowercase().contains("icu")) "$ward Ward" else ward
        val location = data["location"] ?: "$wardClean Room $roomNo Bed $bedNo"

        // Logging: Required Android FCM receipt log
        Log.i(TAG, "[ANDROID FCM] Device received: alert_id = $alertId, doctor_id = $targetDoctorId, patient = $patientName")

        // 3. Prevent duplicate processing of the same alert_id
        if (!AlertDeduplicator.shouldProcessAlert(alertId)) {
            Log.i(TAG, "Alert $alertId already handled on device. Skipping duplicate notification/speech.")
            return
        }

        // 4. Build & display high-priority critical notification
        val notifTitle = "🚨 MEDINTEL Critical Alert"
        val notifBody = "Patient $patientName, $location, $severity"

        showCriticalNotification(alertId, notifTitle, notifBody, data)

        // 5. Extract concise voice text directly from FCM or deterministic builder (Patient [NAME], [LOCATION], Critical.)
        val spokenText = data["voice_text"] ?: MedIntelTTSManager.buildConciseAlertText(
            patientName = patientName,
            ward = ward,
            roomNo = roomNo,
            bedNo = bedNo,
            severity = severity
        )

        // 6. Enqueue in serialized FIFO Android Native TTS Queue
        MedIntelTTSManager.getInstance(applicationContext).speakAlert(alertId, spokenText)

        // 7. Broadcast to MainActivity if active
        val intent = Intent("org.medintel.doctor.CRITICAL_ALERT").apply {
            setPackage(packageName)
            putExtra("alert_id", alertId)
            putExtra("doctor_id", targetDoctorId)
            putExtra("specialty", specialty)
            putExtra("patient_id", patientId)
            putExtra("patient_name", patientName)
            putExtra("ward", ward)
            putExtra("room_no", roomNo)
            putExtra("bed_no", bedNo)
            putExtra("severity", severity)
            putExtra("reason", reason)
            putExtra("recommendation", recommendation)
            putExtra("body", notifBody)
            putExtra("spoken_text", spokenText)
        }
        sendBroadcast(intent)
    }

    private fun showCriticalNotification(alertId: String, title: String, body: String, data: Map<String, String>) {
        createNotificationChannel()

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            for ((k, v) in data) {
                putExtra(k, v)
            }
        }

        val pendingIntent = PendingIntent.getActivity(
            this,
            alertId.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)

        val notificationBuilder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setSound(soundUri)
            .setVibrate(longArrayOf(0, 500, 200, 500))
            .setContentIntent(pendingIntent)
            .setFullScreenIntent(pendingIntent, true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)

        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val notifId = alertId.hashCode()
        notificationManager.notify(notifId, notificationBuilder.build())
        Log.i(TAG, "[ANDROID FCM] Critical notification posted to system: alert_id = $alertId (notification_id = $notifId)")
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val soundUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            val audioAttributes = AudioAttributes.Builder()
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .setUsage(AudioAttributes.USAGE_ALARM)
                .build()

            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.channel_critical_name),
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = getString(R.string.channel_critical_description)
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 500, 200, 500)
                setSound(soundUri, audioAttributes)
                setBypassDnd(true)
                lockscreenVisibility = NotificationCompat.VISIBILITY_PUBLIC
            }

            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }
}
