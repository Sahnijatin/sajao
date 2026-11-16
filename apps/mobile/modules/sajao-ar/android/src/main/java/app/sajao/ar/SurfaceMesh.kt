package app.sajao.ar

import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

/**
 * The live surface effect on phones without LiDAR, built from what ARCore
 * tracks: planes drawn as a grid mesh, and tracked feature points joined to
 * their nearest neighbours so non-flat things (a sofa, a table edge) read as
 * a wire mesh. Pure, so it is tested on the JVM; `SurfaceMesh.swift` mirrors
 * it. Drawing only: nothing here sets a dimension.
 */
object SurfaceMesh {
  /** Grid spacing on planes, in metres. */
  const val GRID_M = 0.3f
  /** Points closer than this are joined, in metres. */
  const val LINK_M = 0.22f
  /** Each point joins at most this many nearest neighbours. */
  const val LINKS_PER_POINT = 3

  /**
   * Grid lines inside a convex plane polygon, in the plane's local x and z:
   * lines of constant x and of constant z every `spacing`, clipped to the
   * polygon. `polygon` holds x, z pairs. Returns x0, z0, x1, z1 per line.
   */
  fun gridLines(polygon: FloatArray, spacing: Float = GRID_M): FloatArray {
    val corners = polygon.size / 2
    if (corners < 3) return FloatArray(0)
    var minX = Float.MAX_VALUE
    var maxX = -Float.MAX_VALUE
    var minZ = Float.MAX_VALUE
    var maxZ = -Float.MAX_VALUE
    for (i in 0 until corners) {
      minX = min(minX, polygon[i * 2])
      maxX = max(maxX, polygon[i * 2])
      minZ = min(minZ, polygon[i * 2 + 1])
      maxZ = max(maxZ, polygon[i * 2 + 1])
    }
    val out = ArrayList<Float>()
    for (axis in 0..1) {
      val lo = if (axis == 0) minX else minZ
      val hi = if (axis == 0) maxX else maxZ
      var step = floor(lo / spacing).toInt() + 1
      while (step * spacing < hi) {
        val value = step * spacing
        val span = clip(polygon, axis, value)
        if (span != null) {
          if (axis == 0) {
            out.add(value); out.add(span.first); out.add(value); out.add(span.second)
          } else {
            out.add(span.first); out.add(value); out.add(span.second); out.add(value)
          }
        }
        step += 1
      }
    }
    return out.toFloatArray()
  }

  /** Where the line with coordinate `axis` fixed at `value` crosses a convex polygon: the other coordinate's range. */
  private fun clip(polygon: FloatArray, axis: Int, value: Float): Pair<Float, Float>? {
    val corners = polygon.size / 2
    var lo = Float.MAX_VALUE
    var hi = -Float.MAX_VALUE
    for (i in 0 until corners) {
      val j = (i + 1) % corners
      val a = polygon[i * 2 + axis]
      val b = polygon[j * 2 + axis]
      if (a == b || value < min(a, b) || value > max(a, b)) continue
      val t = (value - a) / (b - a)
      val from = polygon[i * 2 + 1 - axis]
      val other = from + t * (polygon[j * 2 + 1 - axis] - from)
      lo = min(lo, other)
      hi = max(hi, other)
    }
    return if (hi > lo) lo to hi else null
  }

  /**
   * Joins each point to its nearest neighbours within `link` metres, at most
   * `perPoint` each, using cells `link` wide so thousands of points stay
   * fast. Returns index pairs, each edge once.
   */
  fun links(points: List<FloatArray>, link: Float = LINK_M, perPoint: Int = LINKS_PER_POINT): IntArray {
    fun cell(v: Float) = floor(v / link).toInt()
    fun key(x: Int, y: Int, z: Int): Long =
      ((x.toLong() and 0x1FFFFF) shl 42) or ((y.toLong() and 0x1FFFFF) shl 21) or (z.toLong() and 0x1FFFFF)
    val cells = HashMap<Long, MutableList<Int>>()
    points.forEachIndexed { i, p -> cells.getOrPut(key(cell(p[0]), cell(p[1]), cell(p[2]))) { ArrayList() }.add(i) }
    val seen = HashSet<Long>()
    val out = ArrayList<Int>()
    val limit = link * link
    val near = ArrayList<Pair<Float, Int>>()
    points.forEachIndexed { i, p ->
      near.clear()
      val cx = cell(p[0])
      val cy = cell(p[1])
      val cz = cell(p[2])
      for (dx in -1..1) for (dy in -1..1) for (dz in -1..1) {
        val bucket = cells[key(cx + dx, cy + dy, cz + dz)] ?: continue
        for (j in bucket) {
          if (j == i) continue
          val q = points[j]
          val d = (p[0] - q[0]) * (p[0] - q[0]) + (p[1] - q[1]) * (p[1] - q[1]) + (p[2] - q[2]) * (p[2] - q[2])
          if (d <= limit) near.add(d to j)
        }
      }
      near.sortBy { it.first }
      for (n in 0 until min(perPoint, near.size)) {
        val j = near[n].second
        val a = min(i, j)
        val b = max(i, j)
        if (seen.add((a.toLong() shl 32) or b.toLong())) {
          out.add(a)
          out.add(b)
        }
      }
    }
    return out.toIntArray()
  }
}
