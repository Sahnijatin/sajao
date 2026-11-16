package app.sajao.ar

import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.media.Image
import android.os.SystemClock
import com.google.ar.core.Plane
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Records the capture package's native files during an AR scan: full
 * resolution keyframe candidates (JPEG, sensor orientation) with the camera
 * pose and intrinsics, a depth image per keyframe where ARCore has depth,
 * and the planes at the end. The app's recorder (keyframes.ts) decides which
 * candidates are kept; files it drops are deleted on its say.
 *
 * Poses are ARCore camera poses in the AR world frame (metres, gravity
 * aligned, y up): +X right, +Y up, -Z forward relative to the stored image.
 * Nothing here sets a dimension; the twin measures on the server.
 */
class CaptureRecorder(
  private val dir: File,
  private val emit: (Map<String, Any>) -> Unit,
  private val onError: (Throwable) -> Unit,
) {
  private val startedAt = SystemClock.elapsedRealtime()
  private val gate = KeyframeGate()
  private val writer = Executors.newSingleThreadExecutor()
  private val busy = AtomicBoolean(false)
  private var count = 0

  init {
    dir.mkdirs()
  }

  /**
   * Offer a camera image. Saves it as a keyframe candidate when it is
   * clearly the sharpest yet for its cell: its direction when tracking
   * gives a pose, its time otherwise. Frames are kept whatever tracking
   * says and whether or not the detector runs. Called on the image worker;
   * encoding happens on the recorder's own thread.
   */
  fun offer(image: YuvCopy, sharpness: Double, frame: FrameSnapshot, depth: RawDepth?) {
    val elapsedMs = SystemClock.elapsedRealtime() - startedAt
    val cell = KeyframeGate.cellFor(frame.yaw, frame.pitch, elapsedMs)
    if (!gate.shouldSave(cell, sharpness) || !busy.compareAndSet(false, true)) return
    count += 1
    val name = "kf-%04d".format(count)
    writer.execute {
      try {
        val jpeg = File(dir, "$name.jpg")
        val nv21 = Nv21.from(
          image.width, image.height, image.y, image.yRowStride, image.u, image.v, image.uvRowStride, image.uvPixelStride,
        )
        FileOutputStream(jpeg).use { out ->
          YuvImage(nv21, ImageFormat.NV21, image.width, image.height, null)
            .compressToJpeg(Rect(0, 0, image.width, image.height), JPEG_QUALITY, out)
        }
        depth?.let { FileOutputStream(File(dir, "$name.depth")).use { out -> it.writeRaw(out) } }
        gate.saved(cell, sharpness)
        val payload = HashMap<String, Any>()
        payload["uri"] = "file://${jpeg.absolutePath}"
        payload["sharpness"] = sharpness
        payload["depth"] = depth != null
        payload["tracking"] = frame.tracking
        frame.yaw?.let { payload["yaw"] = it }
        frame.pitch?.let { payload["pitch"] = it }
        if (frame.position != null && frame.rotation != null) {
          payload["pose"] = mapOf(
            "position" to mapOf(
              "x_m" to frame.position[0].toDouble(),
              "y_m" to frame.position[1].toDouble(),
              "z_m" to frame.position[2].toDouble(),
            ),
            "rotation" to frame.rotation.map { it.toDouble() },
          )
        }
        payload["intrinsics"] = mapOf(
          "fx" to frame.focal[0].toDouble(),
          "fy" to frame.focal[1].toDouble(),
          "cx" to frame.principal[0].toDouble(),
          "cy" to frame.principal[1].toDouble(),
          "width_px" to image.width,
          "height_px" to image.height,
        )
        emit(payload)
      } catch (error: Throwable) {
        onError(error)
      } finally {
        busy.set(false)
      }
    }
  }

  /** Delete candidates the app's recorder dropped. */
  fun discard(uris: List<String>) {
    writer.execute {
      for (uri in uris) {
        val jpeg = File(uri.removePrefix("file://"))
        if (jpeg.parentFile == dir) {
          jpeg.delete()
          File(dir, jpeg.nameWithoutExtension + ".depth").delete()
        }
      }
    }
  }

  /** Plane snapshot taken on the GL thread at the end of the scan. */
  fun snapshotPlanes(session: Session): JSONArray {
    val planes = JSONArray()
    for (plane in session.getAllTrackables(Plane::class.java)) {
      if (plane.subsumedBy != null || plane.trackingState == TrackingState.STOPPED) continue
      val polygon = plane.polygon ?: continue
      val matrix = FloatArray(16)
      plane.centerPose.toMatrix(matrix, 0)
      val points = JSONArray()
      for (i in 0 until polygon.remaining()) points.put(polygon.get(i).toDouble())
      planes.put(
        JSONObject()
          .put("id", plane.hashCode().toString())
          .put(
            "type",
            when (plane.type) {
              Plane.Type.VERTICAL -> "vertical"
              Plane.Type.HORIZONTAL_DOWNWARD_FACING -> "horizontal_down"
              else -> "horizontal_up"
            },
          )
          .put("transform", JSONArray(matrix.map { it.toDouble() }))
          .put("extent", JSONArray(listOf(plane.extentX.toDouble(), plane.extentZ.toDouble())))
          .put("polygon_xz", points),
      )
    }
    return planes
  }

  /**
   * End of the scan: write the planes and the depth file for the chosen
   * keyframes (ids k1, k2, ... in the given order), delete every other
   * candidate, and return the files' uris. Runs on the writer thread, after
   * any keyframe still being written.
   */
  /** Where ARCore records the scan video (MP4 with AR data tracks). */
  val videoFile: File get() = File(dir, "scan.mp4")

  fun finish(planes: JSONArray, chosenUris: List<String>, video: String?, done: (Map<String, Any?>) -> Unit) {
    writer.execute {
      val result = HashMap<String, Any?>()
      result["video"] = video
      try {
        val planesFile = File(dir, "planes.json")
        planesFile.writeText(JSONObject().put("format", "sajao-planes-1").put("planes", planes).toString())
        result["planes"] = "file://${planesFile.absolutePath}"
        val chosen = chosenUris.map { File(it.removePrefix("file://")) }
        val entries = chosen.mapIndexedNotNull { index, jpeg ->
          readRaw(File(dir, jpeg.nameWithoutExtension + ".depth"), "k${index + 1}")
        }
        if (entries.isNotEmpty()) {
          val depthFile = File(dir, "depth.sjdepth")
          FileOutputStream(depthFile).use { DepthContainer.write(it, entries) }
          result["depth"] = "file://${depthFile.absolutePath}"
        }
        val keep = chosen.map { it.name }.toSet()
        dir.listFiles()?.forEach { file ->
          val candidate = file.name.startsWith("kf-")
          val jpegName = file.nameWithoutExtension + ".jpg"
          if (candidate && jpegName !in keep) file.delete()
        }
        // Depth now lives in the depth file.
        dir.listFiles { file -> file.name.endsWith(".depth") }?.forEach { it.delete() }
      } catch (error: Throwable) {
        result["error"] = error.message ?: "capture could not finish"
      }
      result["sceneMesh"] = null
      done(result)
    }
  }

  fun close() {
    writer.shutdown()
  }

  private fun readRaw(file: File, id: String): DepthEntry? {
    if (!file.exists()) return null
    val bytes = ByteBuffer.wrap(file.readBytes()).order(ByteOrder.LITTLE_ENDIAN)
    val width = bytes.int
    val height = bytes.int
    val millimetres = ShortArray(width * height)
    bytes.asShortBuffer().get(millimetres)
    bytes.position(8 + width * height * 2)
    val confidence = ByteArray(width * height)
    bytes.get(confidence)
    return DepthEntry(id, width, height, millimetres, confidence)
  }

  companion object {
    const val JPEG_QUALITY = 92

    /** Session folder for a capture, under the app's cache. */
    fun folder(cacheDir: File, captureId: String) = File(cacheDir, "sajao-capture/$captureId")
  }
}

/** What the GL thread read from one ARCore frame, safe to use on other threads. */
class FrameSnapshot(
  val tracking: Boolean,
  /** Camera pose when tracking: quaternion x, y, z, w and position; null otherwise. */
  val rotation: FloatArray?,
  val position: FloatArray?,
  val yaw: Double?,
  val pitch: Double?,
  val focal: FloatArray,
  val principal: FloatArray,
  /** For detection rays; null when not tracking. */
  val camera: CaptureCamera?,
)

/**
 * ARCore raw depth (millimetres, the full 16 bits) with its confidence
 * image (0 to 255), copied so both images can be closed at once. Raw depth
 * is sparser than smoothed depth but measured, with real confidence.
 */
class RawDepth(val width: Int, val height: Int, val millimetres: ShortArray, val confidence: ByteArray) {
  fun writeRaw(out: FileOutputStream) {
    val header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putInt(width).putInt(height)
    out.write(header.array())
    val body = ByteBuffer.allocate(millimetres.size * 2).order(ByteOrder.LITTLE_ENDIAN)
    body.asShortBuffer().put(millimetres)
    out.write(body.array())
    out.write(confidence)
  }

  companion object {
    fun from(depth: Image, confidence: Image): RawDepth {
      val width = depth.width
      val height = depth.height
      val depthPlane = depth.planes[0]
      val depthBuffer = depthPlane.buffer.order(ByteOrder.nativeOrder())
      val millimetres = ShortArray(width * height)
      for (y in 0 until height) {
        for (x in 0 until width) {
          millimetres[y * width + x] = depthBuffer.getShort(y * depthPlane.rowStride + x * depthPlane.pixelStride)
        }
      }
      val confidencePlane = confidence.planes[0]
      val confidenceBuffer = confidencePlane.buffer
      val values = ByteArray(width * height)
      if (confidence.width == width && confidence.height == height) {
        for (y in 0 until height) {
          for (x in 0 until width) {
            values[y * width + x] = confidenceBuffer.get(y * confidencePlane.rowStride + x * confidencePlane.pixelStride)
          }
        }
      }
      return RawDepth(width, height, millimetres, values)
    }
  }
}
