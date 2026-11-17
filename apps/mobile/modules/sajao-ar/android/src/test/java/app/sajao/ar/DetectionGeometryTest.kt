package app.sajao.ar

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.math.sqrt

class DetectionGeometryTest {
  private val identity = floatArrayOf(0f, 0f, 0f, 1f)
  private val intrinsics = Triple(floatArrayOf(500f, 500f), floatArrayOf(320f, 240f), intArrayOf(640, 480))

  private fun camera(rotation: FloatArray = identity, at: FloatArray = floatArrayOf(0f, 1.5f, 0f)) =
    CaptureCamera(rotation, at, intrinsics.first, intrinsics.second, intrinsics.third)

  @Test
  fun theImageCentreLooksStraightAhead() {
    val (origin, direction) = camera().ray(0.5f, 0.5f)
    assertArrayEquals(floatArrayOf(0f, 1.5f, 0f), origin, 1e-6f)
    assertArrayEquals(floatArrayOf(0f, 0f, -1f), direction, 1e-6f)
  }

  @Test
  fun theTopOfTheImageLooksUpAndTheRightLooksRight() {
    val (_, up) = camera().ray(0.5f, 0f)
    assertEquals(true, up[1] > 0f)
    val (_, right) = camera().ray(1f, 0.5f)
    assertEquals(true, right[0] > 0f)
  }

  @Test
  fun aTurnedCameraTurnsItsRays() {
    // 90 degrees about +Y: looking down -Z becomes looking down -X.
    val half = (sqrt(2.0) / 2).toFloat()
    val (_, direction) = camera(rotation = floatArrayOf(0f, half, 0f, half)).ray(0.5f, 0.5f)
    assertArrayEquals(floatArrayOf(-1f, 0f, 0f), direction, 1e-5f)
  }

  @Test
  fun wallsFloorsAndCeilings() {
    assertEquals(Surface.WALL, Surface.kind(vertical = true, facingDown = false, longestSide = 2.5f, hitY = 1f, floorY = 0f))
    // The front of a fridge is a small vertical plane, not a wall.
    assertEquals(Surface.NONE, Surface.kind(vertical = true, facingDown = false, longestSide = 0.7f, hitY = 1f, floorY = 0f))
    assertEquals(Surface.FLOOR, Surface.kind(vertical = false, facingDown = false, longestSide = 3f, hitY = 0.05f, floorY = 0f))
    assertEquals(Surface.RAISED, Surface.kind(vertical = false, facingDown = false, longestSide = 1f, hitY = 0.75f, floorY = 0f))
    assertEquals(Surface.CEILING, Surface.kind(vertical = false, facingDown = true, longestSide = 3f, hitY = 2.7f, floorY = 0f))
    assertEquals(0f, Surface.gap(objectRange = 2.1f, planeRange = 2f), 0f)
    assertEquals(0.6f, Surface.gap(objectRange = 1.4f, planeRange = 2f), 1e-6f)
  }

  @Test
  fun aConeOfFeaturePointsFindsTheFrontOfAnObject() {
    val origin = floatArrayOf(0f, 1.5f, 0f)
    val ahead = floatArrayOf(0f, 0f, -1f)
    // A sofa front 2 m ahead, its back 2.8 m ahead, and a point well off to the side.
    val points = listOf(
      floatArrayOf(0.02f, 1.5f, -2f), floatArrayOf(-0.03f, 1.48f, -2.02f), floatArrayOf(0f, 1.52f, -2.05f),
      floatArrayOf(0.01f, 1.5f, -2.8f), floatArrayOf(0f, 1.49f, -2.82f), floatArrayOf(1f, 1.5f, -2f),
    )
    val range = frontOfCone(origin, ahead, points)
    assertEquals(2.02f, range!!, 0.05f)
    assertEquals(null, frontOfCone(origin, ahead, points.take(2)))
  }
}
