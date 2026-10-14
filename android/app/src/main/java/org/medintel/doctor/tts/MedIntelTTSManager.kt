package org.medintel.doctor.tts

import android.content.Context
import android.media.AudioAttributes
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.util.ArrayDeque
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

/**
 * Utterance payload for FIFO TTS queue with latency measurement metadata.
 */
data class AlertUtterance(
    val alertId: String,
    val text: String,
    val enqueuedTime: Long = System.currentTimeMillis(),
    val alertCreatedAt: String? = null
)

/**
 * Native Android TextToSpeech Engine for MEDINTEL Doctor Mobile.
 * Maintains a serialized FIFO queue of critical alerts with an automatic watchdog
 * to prevent deadlocks from dropped onDone callbacks.
 * Synthesizes voice alerts strictly from verified payload fields:
 * Patient Name, Location, Risk Level. Zero LLM improvisation.
 */
class MedIntelTTSManager private constructor(context: Context) : TextToSpeech.OnInitListener {

    companion object {
        private const val TAG = "MedIntelTTS"
        private const val TTS_DEDUPLICATION_WINDOW_MS = 2 * 60 * 60 * 1000L // 2-hour window
        private const val UTTERANCE_TIMEOUT_MS = 12_000L // 12-second watchdog timeout per utterance

        @Volatile
        private var INSTANCE: MedIntelTTSManager? = null

        fun getInstance(context: Context): MedIntelTTSManager {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: MedIntelTTSManager(context.applicationContext).also { INSTANCE = it }
            }
        }

        /**
         * Builds concise spoken alert text containing ONLY:
         * Patient name, Location, Risk level.
         * Example:
         * "Patient Rahul Patil, Cardiology Ward Room 201 Bed 1, Critical."
         */
        fun buildConciseAlertText(
            patientName: String?,
            ward: String?,
            roomNo: String?,
            bedNo: String?,
            severity: String? = "Critical"
        ): String {
            var name = if (!patientName.isNullOrBlank()) patientName.trim() else "monitored patient"
            if (name.lowercase().startsWith("patient ")) {
                name = name.substring(8).trim()
            }

            val w = if (!ward.isNullOrBlank()) ward.trim() else "General Ward"
            val wardWithSuffix = if (!w.lowercase().contains("ward") && !w.lowercase().contains("icu")) "$w Ward" else w

            val locParts = mutableListOf<String>()
            locParts.add(wardWithSuffix)
            if (!roomNo.isNullOrBlank()) locParts.add("Room ${roomNo.trim()}")
            if (!bedNo.isNullOrBlank()) locParts.add("Bed ${bedNo.trim()}")
            val location = locParts.joinToString(" ")

            val sev = if (!severity.isNullOrBlank()) severity.trim().lowercase().replaceFirstChar { it.uppercase() } else "Critical"

            return "Patient $name, $location, $sev."
        }

        @Suppress("UNUSED_PARAMETER")
        fun buildSpokenAlertText(
            patientName: String?,
            ward: String?,
            roomNo: String?,
            bedNo: String?,
            criticalVital: String? = null,
            vitalValue: String? = null,
            clinicalReason: String? = null
        ): String {
            return buildConciseAlertText(patientName, ward, roomNo, bedNo, "Critical")
        }
    }

    private val appContext = context.applicationContext
    private var tts: TextToSpeech? = null
    private var isInitialized = false

    // Strict FIFO alert queue
    private val ttsQueue = ArrayDeque<AlertUtterance>()
    private var isSpeaking = false
    private var currentSpeakingAlertId: String? = null
    private var currentSpeakingUtterance: AlertUtterance? = null
    private var currentSpeechStartTime: Long = 0L

    // Watchdog handler to prevent queue stall if TTS fails to fire onDone
    private val mainHandler = Handler(Looper.getMainLooper())
    private var watchdogRunnable: Runnable? = null

    // Tracks spoken alert IDs with timestamp to prevent duplicate speech
    private val spokenAlertTimes = ConcurrentHashMap<String, Long>()

    init {
        try {
            tts = TextToSpeech(appContext, this)
        } catch (e: Exception) {
            Log.e(TAG, "Exception initializing TextToSpeech engine: ${e.message}")
            isInitialized = false
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            try {
                val result = tts?.setLanguage(Locale.US)
                if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                    Log.w(TAG, "Locale US not supported; falling back to default locale.")
                    tts?.setLanguage(Locale.getDefault())
                }

                // High importance audio attributes for urgent clinical alerts
                val audioAttributes = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
                tts?.setAudioAttributes(audioAttributes)

                tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) {
                        currentSpeechStartTime = System.currentTimeMillis()
                        val enqTime = currentSpeakingUtterance?.enqueuedTime ?: currentSpeechStartTime
                        val queueLatencyMs = currentSpeechStartTime - enqTime
                        Log.i(TAG, "[ANDROID TTS] Playback started: alert_id = $utteranceId, queue_latency = ${queueLatencyMs}ms")
                    }

                    override fun onDone(utteranceId: String?) {
                        val durationMs = System.currentTimeMillis() - currentSpeechStartTime
                        Log.i(TAG, "[ANDROID TTS] Playback completed: alert_id = $utteranceId, duration = ${durationMs}ms")
                        cancelWatchdog()
                        onPlaybackFinished()
                    }

                    @Deprecated("Deprecated in Java")
                    override fun onError(utteranceId: String?) {
                        Log.e(TAG, "[ANDROID TTS] Playback error: alert_id = $utteranceId")
                        cancelWatchdog()
                        onPlaybackFinished()
                    }

                    override fun onError(utteranceId: String?, errorCode: Int) {
                        Log.e(TAG, "[ANDROID TTS] Playback error ($errorCode): alert_id = $utteranceId")
                        cancelWatchdog()
                        onPlaybackFinished()
                    }
                })

                isInitialized = true
                Log.i(TAG, "Android Native TextToSpeech successfully initialized.")

                // Drain any alerts queued while TTS was initializing
                synchronized(ttsQueue) {
                    processNextInQueueLocked()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error configuring TTS engine: ${e.message}")
                isInitialized = false
            }
        } else {
            Log.e(TAG, "TTS initialization failed with code: $status")
            isInitialized = false
        }
    }

    /**
     * Enqueues an alert into the FIFO queue and initiates sequential speech.
     * Prevents duplicate speech for the same alert_id within the window.
     * Distinct re-critical alerts with a new alert_id pass and are spoken in FIFO order.
     */
    fun speakAlert(alertId: String, text: String, alertCreatedAt: String? = null): Boolean {
        if (alertId.isBlank() || text.isBlank()) return false
        val cleanId = alertId.trim()
        val now = System.currentTimeMillis()
        val lastSpoken = spokenAlertTimes[cleanId]
        if (lastSpoken != null && (now - lastSpoken) < TTS_DEDUPLICATION_WINDOW_MS) {
            Log.i(TAG, "[ANDROID TTS] Alert $cleanId was spoken recently. Skipping duplicate speech.")
            return false
        }
        spokenAlertTimes[cleanId] = now
        if (spokenAlertTimes.size > 300) {
            spokenAlertTimes.entries.removeIf { (now - it.value) > TTS_DEDUPLICATION_WINDOW_MS }
        }

        val utterance = AlertUtterance(cleanId, text, now, alertCreatedAt)
        Log.i(TAG, "[ANDROID TTS] Queue FIFO: alert_id = $cleanId, text = '$text', queued_at = $now")
        synchronized(ttsQueue) {
            ttsQueue.addLast(utterance)
            processNextInQueueLocked()
        }
        return true
    }

    fun speak(text: String) {
        val alertId = "ALT-${System.currentTimeMillis()}"
        speakAlert(alertId, text)
    }

    private fun cancelWatchdog() {
        watchdogRunnable?.let { mainHandler.removeCallbacks(it) }
        watchdogRunnable = null
    }

    private fun onPlaybackFinished() {
        synchronized(ttsQueue) {
            isSpeaking = false
            currentSpeakingAlertId = null
            currentSpeakingUtterance = null
            processNextInQueueLocked()
        }
    }

    private fun processNextInQueueLocked() {
        if (!isInitialized || isSpeaking || ttsQueue.isEmpty()) {
            return
        }

        val next = ttsQueue.removeFirst()
        isSpeaking = true
        currentSpeakingAlertId = next.alertId
        currentSpeakingUtterance = next
        currentSpeechStartTime = System.currentTimeMillis()

        // Arm the 12-second watchdog to auto-recover if TTS hangs or drops onDone
        cancelWatchdog()
        watchdogRunnable = Runnable {
            synchronized(ttsQueue) {
                if (isSpeaking && currentSpeakingAlertId == next.alertId) {
                    Log.w(TAG, "[ANDROID TTS WATCHDOG] Alert ${next.alertId} speech timed out after ${UTTERANCE_TIMEOUT_MS}ms. Forcing queue advancement.")
                    onPlaybackFinished()
                }
            }
        }
        mainHandler.postDelayed(watchdogRunnable!!, UTTERANCE_TIMEOUT_MS)

        try {
            val params = Bundle()
            params.putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, next.alertId)
            val result = tts?.speak(next.text, TextToSpeech.QUEUE_FLUSH, params, next.alertId)
            if (result != TextToSpeech.SUCCESS) {
                Log.e(TAG, "tts.speak returned error code $result for alert ${next.alertId}")
                cancelWatchdog()
                isSpeaking = false
                currentSpeakingAlertId = null
                currentSpeakingUtterance = null
                processNextInQueueLocked()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error executing TTS speech: ${e.message}", e)
            cancelWatchdog()
            isSpeaking = false
            currentSpeakingAlertId = null
            currentSpeakingUtterance = null
            processNextInQueueLocked()
        }
    }

    fun isCurrentlySpeaking(): Boolean {
        synchronized(ttsQueue) {
            return isSpeaking
        }
    }

    fun getQueueSize(): Int {
        synchronized(ttsQueue) {
            return ttsQueue.size
        }
    }

    fun hasSpoken(alertId: String): Boolean {
        val cleanId = alertId.trim()
        val now = System.currentTimeMillis()
        val lastSpoken = spokenAlertTimes[cleanId] ?: return false
        return (now - lastSpoken) < TTS_DEDUPLICATION_WINDOW_MS
    }

    fun clearSpokenHistory() {
        spokenAlertTimes.clear()
    }

    fun clearQueue() {
        synchronized(ttsQueue) {
            ttsQueue.clear()
        }
    }

    fun isEngineReady(): Boolean {
        return isInitialized
    }

    fun stop() {
        cancelWatchdog()
        synchronized(ttsQueue) {
            ttsQueue.clear()
            isSpeaking = false
            currentSpeakingAlertId = null
            currentSpeakingUtterance = null
        }
        try {
            tts?.stop()
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping TTS: ${e.message}")
        }
    }

    fun shutdown() {
        stop()
        try {
            tts?.shutdown()
        } catch (e: Exception) {
            Log.w(TAG, "Error shutting down TTS: ${e.message}")
        }
        INSTANCE = null
    }
}
