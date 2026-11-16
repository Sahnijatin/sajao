package app.sajao.ar

import java.io.DataOutputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Decides which camera frames are worth saving as keyframe candidates: the
 * same direction cells as the app's `keyframes.ts` (30 degree yaw sectors,
 * three pitch bands), and only a frame clearly sharper than the best one
 * saved for its cell. The app still decides which candidates are kept; this
 * only avoids encoding frames that cannot win. Pure; mirrored in Swift.
 */
class KeyframeGate {
  private val best = HashMap<String, Double>()

  fun shouldSave(yaw: Double, pitch: Double, sharpness: Double): Boolean {
    if (!(sharpness > 0)) return false
    val current = best[cellOf(yaw, pitch)] ?: return true
    return sharpness >= current * REPLACE_MARGIN
  }

  fun saved(yaw: Double, pitch: Double, sharpness: Double) {
    best[cellOf(yaw, pitch)] = sharpness
  }

  fun reset() = best.clear()

  companion object {
    const val YAW_CELL_DEGREES = 30.0
    const val REPLACE_MARGIN = 1.1

    /** "d<sector>-<band>", as `cellOf` in keyframes.ts. */
    fun cellOf(yaw: Double, pitch: Double): String {
      val turned = ((yaw % 360) + 360) % 360
      val sector = (turned / YAW_CELL_DEGREES).toInt()
      val band = listOf(-20.0, 20.0).count { pitch > it }
      return "d$sector-$band"
    }
  }
}

/** One depth image aligned to a keyframe: millimetres (0 = no reading) and confidence 0 to 255, row-major. */
class DepthEntry(val id: String, val width: Int, val height: Int, val millimetres: ShortArray, val confidence: ByteArray) {
  init {
    require(millimetres.size == width * height && confidence.size == width * height) { "depth size mismatch" }
  }
}

/**
 * The capture package's depth file, format SJDEPTH1 (docs/06), little
 * endian: magic "SJDEPTH1", uint32 count, then per entry uint16 id length,
 * the id in UTF-8, uint32 width, uint32 height, uint16 millimetres per pixel,
 * uint8 confidence per pixel. Ids are the keyframe ids (k1, k2, ...); each
 * image is aligned to its keyframe in the sensor orientation the keyframe
 * is stored in, so its intrinsics are the keyframe's scaled by width.
 */
object DepthContainer {
  const val MAGIC = "SJDEPTH1"

  fun write(out: OutputStream, entries: List<DepthEntry>) {
    val data = DataOutputStream(out)
    data.write(MAGIC.toByteArray(Charsets.US_ASCII))
    data.write(le32(entries.size))
    for (entry in entries) {
      val id = entry.id.toByteArray(Charsets.UTF_8)
      data.write(le16(id.size))
      data.write(id)
      data.write(le32(entry.width))
      data.write(le32(entry.height))
      val depth = ByteBuffer.allocate(entry.millimetres.size * 2).order(ByteOrder.LITTLE_ENDIAN)
      depth.asShortBuffer().put(entry.millimetres)
      data.write(depth.array())
      data.write(entry.confidence)
    }
    data.flush()
  }

  private fun le32(v: Int) = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(v).array()
  private fun le16(v: Int) = ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(v.toShort()).array()
}

/** YUV 4:2:0 planes to NV21 (Y, then interleaved V and U), which Android's JPEG encoder takes. */
object Nv21 {
  fun from(
    width: Int,
    height: Int,
    y: ByteArray,
    yRowStride: Int,
    u: ByteArray,
    v: ByteArray,
    uvRowStride: Int,
    uvPixelStride: Int,
  ): ByteArray {
    val out = ByteArray(width * height * 3 / 2)
    for (row in 0 until height) {
      System.arraycopy(y, row * yRowStride, out, row * width, width)
    }
    var o = width * height
    for (row in 0 until height / 2) {
      for (column in 0 until width / 2) {
        val index = row * uvRowStride + column * uvPixelStride
        out[o++] = v.getOrElse(index) { 128.toByte() }
        out[o++] = u.getOrElse(index) { 128.toByte() }
      }
    }
    return out
  }
}
