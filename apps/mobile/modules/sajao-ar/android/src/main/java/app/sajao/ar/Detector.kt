package app.sajao.ar

import android.content.Context
import android.graphics.Bitmap
import android.media.Image
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.objectdetector.ObjectDetector
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** One detection in the upright camera image; the box is normalised, 0 to 1. */
data class UprightDetection(
  val detectorClass: String,
  val score: Float,
  val centreX: Float,
  val centreY: Float,
  val left: Float,
  val top: Float,
  val width: Float,
  val height: Float,
)

/** A copy of a camera image's planes, so the image can be closed at once. */
class YuvCopy(
  val width: Int,
  val height: Int,
  val y: ByteArray,
  val yRowStride: Int,
  val u: ByteArray,
  val v: ByteArray,
  val uvRowStride: Int,
  val uvPixelStride: Int,
) {
  companion object {
    fun from(image: Image): YuvCopy {
      val planes = image.planes
      fun bytes(buffer: ByteBuffer): ByteArray {
        val copy = ByteArray(buffer.remaining())
        buffer.get(copy)
        return copy
      }
      return YuvCopy(
        image.width,
        image.height,
        bytes(planes[0].buffer),
        planes[0].rowStride,
        bytes(planes[1].buffer),
        bytes(planes[2].buffer),
        planes[1].rowStride,
        planes[1].pixelStride,
      )
    }
  }

  /** Mean of a coarse grid of luma samples, 0 to 255. */
  fun meanBrightness(): Double {
    val steps = 24
    var sum = 0
    for (row in 0 until steps) {
      val y = (row * height) / steps + height / (steps * 2)
      for (column in 0 until steps) {
        val x = (column * width) / steps + width / (steps * 2)
        sum += this.y[y * yRowStride + x].toInt() and 0xff
      }
    }
    return sum.toDouble() / (steps * steps)
  }

  /**
   * An upright RGB bitmap `outWidth` wide. The sensor image is landscape; the
   * phone is held in portrait, so the image is turned 90 degrees clockwise.
   */
  fun uprightBitmap(outWidth: Int): Bitmap {
    // Upright size: the sensor height becomes the width.
    val outHeight = (outWidth.toLong() * width / height).toInt()
    val pixels = IntArray(outWidth * outHeight)
    for (oy in 0 until outHeight) {
      // Upright (x, y) comes from sensor (u, v) = (y, 1 - x), normalised.
      val sx = ((oy + 0.5f) / outHeight * width).toInt().coerceIn(0, width - 1)
      for (ox in 0 until outWidth) {
        val sy = ((1f - (ox + 0.5f) / outWidth) * height).toInt().coerceIn(0, height - 1)
        val luma = (this.y[sy * yRowStride + sx].toInt() and 0xff).toFloat()
        val uvIndex = (sy / 2) * uvRowStride + (sx / 2) * uvPixelStride
        val cb = ((u.getOrElse(uvIndex) { 128.toByte() }.toInt() and 0xff) - 128).toFloat()
        val cr = ((v.getOrElse(uvIndex) { 128.toByte() }.toInt() and 0xff) - 128).toFloat()
        val r = (luma + 1.402f * cr).toInt().coerceIn(0, 255)
        val g = (luma - 0.344f * cb - 0.714f * cr).toInt().coerceIn(0, 255)
        val b = (luma + 1.772f * cb).toInt().coerceIn(0, 255)
        pixels[oy * outWidth + ox] = (0xff shl 24) or (r shl 16) or (g shl 8) or b
      }
    }
    return Bitmap.createBitmap(pixels, outWidth, outHeight, Bitmap.Config.ARGB_8888)
  }
}

/**
 * EfficientDet-Lite0 (COCO classes, Apache 2.0) through MediaPipe, one image
 * at a time on a background thread. Any failure means no detections: the
 * scan carries on without labels.
 */
class Detector(context: Context) {
  private val executor = Executors.newSingleThreadExecutor()
  private val busy = AtomicBoolean(false)

  /** Why the detector could not load, for the debug overlay; null when it loaded. */
  var loadError: String? = null
    private set

  private val detector: ObjectDetector? = try {
    val bytes = context.assets.open(MODEL).use { it.readBytes() }
    val buffer = ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder())
    buffer.put(bytes)
    buffer.rewind()
    val options = ObjectDetector.ObjectDetectorOptions.builder()
      .setBaseOptions(BaseOptions.builder().setModelAssetBuffer(buffer).build())
      .setRunningMode(RunningMode.IMAGE)
      .setMaxResults(10)
      .setScoreThreshold(0.3f)
      .build()
    ObjectDetector.createFromOptions(context, options)
  } catch (error: Throwable) {
    loadError = "${error.javaClass.simpleName}: ${error.message ?: ""}".take(120)
    null
  }

  val isAvailable: Boolean get() = detector != null
  val isBusy: Boolean get() = busy.get()

  /** Calls `done` on the detector thread with what was found and how long it took. */
  fun detect(image: YuvCopy, done: (List<UprightDetection>, Double) -> Unit) {
    val detector = detector ?: return
    if (!busy.compareAndSet(false, true)) return
    executor.execute {
      val started = System.nanoTime()
      val found = mutableListOf<UprightDetection>()
      try {
        val bitmap = image.uprightBitmap(INPUT_WIDTH)
        val result = detector.detect(BitmapImageBuilder(bitmap).build())
        for (detection in result.detections()) {
          val category = detection.categories().firstOrNull() ?: continue
          val box = detection.boundingBox()
          found.add(
            UprightDetection(
              category.categoryName(),
              category.score(),
              box.centerX() / bitmap.width,
              box.centerY() / bitmap.height,
              box.left / bitmap.width,
              box.top / bitmap.height,
              box.width() / bitmap.width,
              box.height() / bitmap.height,
            ),
          )
        }
      } catch (_: Throwable) {
        // No labels this time.
      } finally {
        busy.set(false)
      }
      done(found, (System.nanoTime() - started) / 1e6)
    }
  }

  fun close() {
    executor.shutdown()
    try {
      detector?.close()
    } catch (_: Throwable) {
    }
  }

  companion object {
    private const val MODEL = "efficientdet_lite0.tflite"
    private const val INPUT_WIDTH = 480
  }
}
