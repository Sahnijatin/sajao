package app.sajao.ar

import kotlin.math.sqrt

/**
 * The camera as it was when a frame was captured, for building detection
 * rays after the detector finishes. Pure: no ARCore types, so it is tested
 * on the JVM. ARCore's camera pose looks down -Z with +Y up, relative to the
 * image readout, so a sensor image pixel maps straight onto it.
 */
class CaptureCamera(
  /** Rotation quaternion x, y, z, w. */
  private val rotation: FloatArray,
  private val translation: FloatArray,
  private val focal: FloatArray,
  private val principal: FloatArray,
  private val size: IntArray,
) {
  /** Focal length along the sensor image's x axis, in pixels. */
  val focalX: Float get() = focal[0]

  /** Sensor image width in pixels. */
  val widthPx: Int get() = size[0]

  /** World-space origin and unit direction through a sensor image point, normalised 0 to 1 with y down. */
  fun ray(normalisedX: Float, normalisedY: Float): Pair<FloatArray, FloatArray> {
    val u = normalisedX * size[0]
    val v = normalisedY * size[1]
    val local = floatArrayOf((u - principal[0]) / focal[0], -(v - principal[1]) / focal[1], -1f)
    val world = rotate(rotation, local)
    val length = sqrt(world[0] * world[0] + world[1] * world[1] + world[2] * world[2])
    return translation.copyOf() to floatArrayOf(world[0] / length, world[1] / length, world[2] / length)
  }

  companion object {
    /** v rotated by unit quaternion q = (x, y, z, w). */
    fun rotate(q: FloatArray, v: FloatArray): FloatArray {
      val (qx, qy, qz, qw) = q
      // t = 2 * cross(q.xyz, v); v' = v + w * t + cross(q.xyz, t)
      val tx = 2f * (qy * v[2] - qz * v[1])
      val ty = 2f * (qz * v[0] - qx * v[2])
      val tz = 2f * (qx * v[1] - qy * v[0])
      return floatArrayOf(
        v[0] + qw * tx + (qy * tz - qz * ty),
        v[1] + qw * ty + (qz * tx - qx * tz),
        v[2] + qw * tz + (qx * ty - qy * tx),
      )
    }
  }
}

/** Feature points within this angle of a detection's ray belong to what it points at; same as iOS. */
private val CONE_TAN = kotlin.math.tan(Math.toRadians(2.5)).toFloat()
private const val MAX_RANGE_M = 8f

/**
 * The front of whatever a ray points at: the near quarter of the tracked
 * feature points inside a narrow cone around it, as a distance along the
 * ray. Null with fewer than three points. `points` holds x, y, z triples.
 */
fun frontOfCone(origin: FloatArray, direction: FloatArray, points: Collection<FloatArray>): Float? {
  val ranges = ArrayList<Float>()
  for (p in points) {
    val vx = p[0] - origin[0]
    val vy = p[1] - origin[1]
    val vz = p[2] - origin[2]
    val along = vx * direction[0] + vy * direction[1] + vz * direction[2]
    if (along <= 0.2f || along >= MAX_RANGE_M) continue
    val ox = vx - direction[0] * along
    val oy = vy - direction[1] * along
    val oz = vz - direction[2] * along
    if (sqrt(ox * ox + oy * oy + oz * oz) < along * CONE_TAN) ranges.add(along)
  }
  if (ranges.size < 3) return null
  ranges.sort()
  return ranges[ranges.size / 4]
}

/** Plane kinds the label rules understand; the same strings as iOS. */
object Surface {
  const val WALL = "wall"
  const val FLOOR = "floor"
  const val CEILING = "ceiling"
  const val RAISED = "raised"
  const val NONE = "none"

  /** A vertical plane at least this long is a wall, not the front of a cupboard or fridge. */
  const val WALL_SIDE_M = 1.2f

  /**
   * ARCore has no plane classes, so walls, floor and ceiling come from the
   * plane's type, size and height. The lowest upward plane is the floor.
   */
  fun kind(vertical: Boolean, facingDown: Boolean, longestSide: Float, hitY: Float, floorY: Float?): String = when {
    vertical -> if (longestSide >= WALL_SIDE_M) WALL else NONE
    facingDown -> CEILING
    floorY != null && hitY <= floorY + 0.15f -> FLOOR
    else -> RAISED
  }

  /** Metres from the object point to the plane behind it; never negative. */
  fun gap(objectRange: Float, planeRange: Float): Float = maxOf(0f, planeRange - objectRange)
}

/** Inputs for coverage on walls and floor; the same numbers as iOS. */
object SurfaceSample {
  /** Where the rays go, as normalised sensor image points: a 4 by 3 grid away from the edges. */
  val GRID: List<Pair<Float, Float>> =
    listOf(0.2f, 0.4f, 0.6f, 0.8f).flatMap { x -> listOf(0.25f, 0.5f, 0.75f).map { y -> x to y } }

  /** A wall's facing direction in degrees about the vertical, and its distance from the origin along that normal. */
  fun wallFrame(normal: FloatArray, point: FloatArray): Pair<Double, Double> {
    val yaw = Math.toDegrees(kotlin.math.atan2(normal[0].toDouble(), normal[2].toDouble()))
    val offset = normal[0] * point[0] + normal[1] * point[1] + normal[2] * point[2]
    return yaw to offset.toDouble()
  }

  /** A coverage hit from tracked feature points, where no plane was found. */
  class PointHit(val kind: String, val normalYaw: Double, val offset: Double, val point: FloatArray)

  /**
   * When few planes are found (common on Android), a grid ray that meets
   * tracked feature points still counts: at floor height as floor,
   * otherwise as a wall facing the camera. A ray pointing steeply up or
   * down that is not at the floor (a table top, the ceiling) counts as
   * nothing. Same as iOS.
   */
  fun pointHit(origin: FloatArray, direction: FloatArray, range: Float, floorY: Float?): PointHit? {
    val p = FloatArray(3) { origin[it] + direction[it] * range }
    val atFloor = if (floorY != null) p[1] <= floorY + 0.15f else p[1] <= origin[1] - 1.1f
    if (atFloor) return PointHit(Surface.FLOOR, 0.0, 0.0, p)
    if (kotlin.math.abs(direction[1]) > 0.7f) return null
    val nx = -direction[0]
    val nz = -direction[2]
    val length = kotlin.math.sqrt(nx * nx + nz * nz)
    if (length < 1e-3f) return null
    val (yaw, offset) = wallFrame(floatArrayOf(nx / length, 0f, nz / length), p)
    return PointHit(Surface.WALL, yaw, offset, p)
  }

  /**
   * How sharp a camera image is: the mean squared Laplacian of the luma on a
   * 40 by 30 grid of pixels. Motion blur flattens edges and drops it. The
   * scale depends on the phone and the room, so the app compares a frame
   * with the same session's recent frames, never with a fixed number.
   */
  fun lumaSharpness(y: ByteArray, width: Int, height: Int, rowStride: Int): Double {
    if (width < 8 || height < 8) return 0.0
    val columns = 40
    val rows = 30
    var sum = 0.0
    for (row in 0 until rows) {
      val py = height / 10 + (row * (height * 8 / 10)) / rows
      for (column in 0 until columns) {
        val px = width / 10 + (column * (width * 8 / 10)) / columns
        fun at(x: Int, yy: Int) = (y[yy * rowStride + x].toInt() and 0xff).toDouble()
        val laplacian = 4 * at(px, py) - at(px - 1, py) - at(px + 1, py) - at(px, py - 1) - at(px, py + 1)
        sum += laplacian * laplacian
      }
    }
    return sum / (columns * rows)
  }
}

/**
 * Placing a detection without LiDAR, where most rays hit nothing: from the
 * floor under a standing object, or from how tall the object looks. Used
 * for live labels only; nothing here sets a dimension. Same as Swift.
 */
object Placement {
  /** Typical heights of the large objects the scan names, in metres: only for placing labels. */
  val TYPICAL_HEIGHT_M = mapOf(
    "couch" to 0.85f,
    "bed" to 0.6f,
    "dining table" to 0.76f,
    "refrigerator" to 1.7f,
    "tv" to 0.6f,
    "chair" to 0.9f,
    "microwave" to 0.3f,
  )

  /** Objects that stand on the floor: their footprint can be found from the floor plane. */
  val STANDS_ON_FLOOR = setOf("couch", "bed", "dining table", "refrigerator", "chair")

  private const val MIN_RANGE_M = 0.3f
  private const val MAX_RANGE_M = 8f

  /** Distance along a ray to where it meets the floor, or null when it points up or meets it out of range. */
  fun floorRange(origin: FloatArray, direction: FloatArray, floorY: Float): Float? {
    if (direction[1] > -0.02f) return null
    val t = (floorY - origin[1]) / direction[1]
    return if (t in MIN_RANGE_M..MAX_RANGE_M) t else null
  }

  /** Distance along a ray at which it is `horizontal` metres away on the floor plan. */
  fun rangeAtHorizontal(direction: FloatArray, horizontal: Float): Float? {
    val flat = sqrt(direction[0] * direction[0] + direction[2] * direction[2])
    if (flat < 0.05f) return null
    val t = horizontal / flat
    return if (t in MIN_RANGE_M..MAX_RANGE_M) t else null
  }

  /** Distance from how tall the object looks: focal length times typical height over its height in pixels. */
  fun rangeFromSize(detectorClass: String, heightPx: Float, focalPx: Float): Float? {
    val height = TYPICAL_HEIGHT_M[detectorClass] ?: return null
    if (heightPx < 8f) return null
    val t = focalPx * height / heightPx
    return if (t in MIN_RANGE_M..MAX_RANGE_M) t else null
  }
}
