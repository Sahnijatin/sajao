package app.sajao.ar

import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.media.Image
import com.google.ar.core.Frame
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
) {
  private val gate = KeyframeGate()
  private val writer = Executors.newSingleThreadExecutor()
  private val busy = AtomicBoolean(false)
  private var count = 0

  init {
    dir.mkdirs()
  }

  /**
   * Offer the image the detector just copied. Saves it as a keyframe
   * candidate when it is clearly the sharpest yet for its direction.
   * Runs on the GL thread; encoding and writing happen on a worker thread.
   */
  fun offer(frame: Frame, image: YuvCopy, sharpness: Double, yaw: Double, pitch: Double) {
    if (frame.camera.trackingState != TrackingState.TRACKING) return
    if (!gate.shouldSave(yaw, pitch, sharpness) || !busy.compareAndSet(false, true)) return
    val pose = frame.camera.pose
    val rotation = FloatArray(4)
    pose.getRotationQuaternion(rotation, 0)
    val position = pose.translation
    val intrinsics = frame.camera.imageIntrinsics
    val focal = intrinsics.focalLength
    val principal = intrinsics.principalPoint
    val depth = try {
      frame.acquireDepthImage16Bits().use { depthCopy(it) }
    } catch (_: Throwable) {
      null
    }
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
        gate.saved(yaw, pitch, sharpness)
        emit(
          mapOf(
            "uri" to "file://${jpeg.absolutePath}",
            "sharpness" to sharpness,
            "yaw" to yaw,
            "pitch" to pitch,
            "depth" to (depth != null),
            "pose" to mapOf(
              "position" to mapOf(
                "x_m" to position[0].toDouble(),
                "y_m" to position[1].toDouble(),
                "z_m" to position[2].toDouble(),
              ),
              "rotation" to rotation.map { it.toDouble() },
            ),
            "intrinsics" to mapOf(
              "fx" to focal[0].toDouble(),
              "fy" to focal[1].toDouble(),
              "cx" to principal[0].toDouble(),
              "cy" to principal[1].toDouble(),
              "width_px" to image.width,
              "height_px" to image.height,
            ),
          ),
        )
      } catch (_: Throwable) {
        // A lost candidate is fine; the next sharp frame in this direction replaces it.
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
  fun finish(planes: JSONArray, chosenUris: List<String>, done: (Map<String, Any?>) -> Unit) {
    writer.execute {
      val result = HashMap<String, Any?>()
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

  /** A depth image copied out of ARCore so it can be closed at once. */
  private class RawDepth(val width: Int, val height: Int, val millimetres: ShortArray) {
    fun writeRaw(out: FileOutputStream) {
      val header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putInt(width).putInt(height)
      out.write(header.array())
      val body = ByteBuffer.allocate(millimetres.size * 2).order(ByteOrder.LITTLE_ENDIAN)
      body.asShortBuffer().put(millimetres)
      out.write(body.array())
    }
  }

  private fun depthCopy(image: Image): RawDepth {
    val plane = image.planes[0]
    val buffer = plane.buffer.order(ByteOrder.nativeOrder())
    val width = image.width
    val height = image.height
    val rowStride = plane.rowStride
    val out = ShortArray(width * height)
    for (y in 0 until height) {
      for (x in 0 until width) {
        // DEPTH16: the low 13 bits are millimetres.
        out[y * width + x] = (buffer.getShort(y * rowStride + x * 2).toInt() and 0x1FFF).toShort()
      }
    }
    return RawDepth(width, height, out)
  }

  private fun readRaw(file: File, id: String): DepthEntry? {
    if (!file.exists()) return null
    val bytes = ByteBuffer.wrap(file.readBytes()).order(ByteOrder.LITTLE_ENDIAN)
    val width = bytes.int
    val height = bytes.int
    val millimetres = ShortArray(width * height)
    bytes.asShortBuffer().get(millimetres)
    // ARCore's smoothed depth has no per-pixel confidence: full where there is a reading.
    val confidence = ByteArray(width * height) { if (millimetres[it].toInt() != 0) 255.toByte() else 0 }
    return DepthEntry(id, width, height, millimetres, confidence)
  }

  companion object {
    const val JPEG_QUALITY = 92

    /** Session folder for a capture, under the app's cache. */
    fun folder(cacheDir: File, captureId: String) = File(cacheDir, "sajao-capture/$captureId")
  }
}
