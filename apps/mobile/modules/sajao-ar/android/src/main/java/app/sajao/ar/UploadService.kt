package app.sajao.ar

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log

/**
 * Keeps the app's process alive while a scan uploads, so the upload carries
 * on when the person leaves the app. It does no work itself: the upload runs
 * in the app's own code, and this service only holds a "data sync" foreground
 * slot with a quiet notification that says what is happening.
 */
class UploadService : Service() {
  override fun onBind(intent: Intent?): IBinder? = null

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    val title = intent?.getStringExtra(EXTRA_TITLE) ?: ""
    val text = intent?.getStringExtra(EXTRA_TEXT) ?: ""
    val notification = notification(this, title, text)
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
      } else {
        startForeground(NOTIFICATION_ID, notification)
      }
    } catch (error: Throwable) {
      // Not allowed right now (started from the background): the upload still
      // runs while the app is open and resumes the next time it opens.
      Log.w(Detector.TAG, "upload service could not go to the foreground", error)
      stopSelf()
    }
    // Not restarted by the system: the app resumes the upload itself when it opens.
    return START_NOT_STICKY
  }

  companion object {
    private const val CHANNEL = "sajao.upload"
    private const val NOTIFICATION_ID = 4107
    private const val EXTRA_TITLE = "title"
    private const val EXTRA_TEXT = "text"

    fun start(context: Context, title: String, text: String) {
      val intent = Intent(context, UploadService::class.java)
        .putExtra(EXTRA_TITLE, title)
        .putExtra(EXTRA_TEXT, text)
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        context.startForegroundService(intent)
      } else {
        context.startService(intent)
      }
    }

    fun stop(context: Context) {
      context.stopService(Intent(context, UploadService::class.java))
    }

    private fun notification(context: Context, title: String, text: String): Notification {
      val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        val manager = context.getSystemService(NotificationManager::class.java)
        // Low importance: no sound, no heads-up.
        manager.createNotificationChannel(
          NotificationChannel(CHANNEL, title, NotificationManager.IMPORTANCE_LOW),
        )
        Notification.Builder(context, CHANNEL)
      } else {
        @Suppress("DEPRECATION")
        Notification.Builder(context)
      }
      return builder
        .setContentTitle(title)
        .setContentText(text)
        .setSmallIcon(context.applicationInfo.icon)
        .setOngoing(true)
        .setProgress(0, 0, true)
        .build()
    }
  }
}
