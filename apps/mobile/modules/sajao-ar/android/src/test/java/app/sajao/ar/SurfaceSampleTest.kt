package app.sajao.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SurfaceSampleTest {
  @Test
  fun aWallFacingPlusZAtMinusTwo() {
    val (yaw, offset) = SurfaceSample.wallFrame(floatArrayOf(0f, 0f, 1f), floatArrayOf(0.5f, 1f, -2f))
    assertEquals(0.0, yaw, 1e-6)
    assertEquals(-2.0, offset, 1e-6)
    val (side, _) = SurfaceSample.wallFrame(floatArrayOf(1f, 0f, 0f), floatArrayOf(-2f, 1f, 0f))
    assertEquals(90.0, side, 1e-6)
  }

  @Test
  fun twelveRaysAwayFromTheEdges() {
    assertEquals(12, SurfaceSample.GRID.size)
    assertTrue(SurfaceSample.GRID.all { (x, y) -> x in 0.1f..0.9f && y in 0.1f..0.9f })
  }

  @Test
  fun aBlurredImageIsLessSharp() {
    val width = 320
    val height = 240
    val sharp = ByteArray(width * height) { i -> if (((i % width) / 4 + (i / width) / 4) % 2 == 0) 20 else 220.toByte() }
    // A horizontal box blur, as a fast pan smears the picture.
    val blurred = ByteArray(width * height) { i ->
      val x = i % width
      var sum = 0
      for (d in -6..6) sum += sharp[i - x + (x + d).coerceIn(0, width - 1)].toInt() and 0xff
      (sum / 13).toByte()
    }
    val a = SurfaceSample.lumaSharpness(sharp, width, height, width)
    val b = SurfaceSample.lumaSharpness(blurred, width, height, width)
    assertTrue("sharp $a blurred $b", b < a * 0.55)
    assertEquals(0.0, SurfaceSample.lumaSharpness(ByteArray(width * height) { 90 }, width, height, width), 0.0)
  }

  @Test
  fun featurePointsCountAsWallOrFloorWhenThereAreNoPlanes() {
    val eye = floatArrayOf(0f, 1.4f, 0f)
    // Level, 3 m ahead: a wall facing the camera, at z = -3.
    val wall = SurfaceSample.pointHit(eye, floatArrayOf(0f, 0f, -1f), 3f, floorY = 0f)!!
    assertEquals(Surface.WALL, wall.kind)
    assertEquals(0.0, wall.normalYaw, 1e-6)
    assertEquals(-3.0, wall.offset, 1e-6)
    // Down to floor height: floor.
    val down = floatArrayOf(0f, -0.6f, -0.8f)
    assertEquals(Surface.FLOOR, SurfaceSample.pointHit(eye, down, 2.33f, floorY = 0f)!!.kind)
    // Steeply down to a table top: nothing.
    assertEquals(null, SurfaceSample.pointHit(eye, floatArrayOf(0f, -0.8f, -0.6f), 0.8f, floorY = 0f))
    // No floor plane yet: 1.1 m below the phone counts as floor.
    assertEquals(Surface.FLOOR, SurfaceSample.pointHit(eye, down, 2.33f, floorY = null)!!.kind)
  }
}
