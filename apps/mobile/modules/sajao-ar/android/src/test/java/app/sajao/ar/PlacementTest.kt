package app.sajao.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import kotlin.math.sqrt

class PlacementTest {
  private val eye = floatArrayOf(0f, 1.4f, 0f)

  private fun unit(x: Float, y: Float, z: Float): FloatArray {
    val n = sqrt(x * x + y * y + z * z)
    return floatArrayOf(x / n, y / n, z / n)
  }

  @Test
  fun aRayDownToTheFloor() {
    // Looking 1.4 m down over 2 m ahead: meets the floor at 2 m on the plan.
    val down = unit(0f, -1.4f, -2f)
    val t = Placement.floorRange(eye, down, floorY = 0f)!!
    assertEquals(2f, t * sqrt(down[0] * down[0] + down[2] * down[2]), 1e-4f)
    assertNull(Placement.floorRange(eye, unit(0f, 0.2f, -1f), 0f))
  }

  @Test
  fun aFridgeIsPlacedAboveItsFootprintNotOnTheWallBehind() {
    // The box bottom meets the floor 2 m ahead; the box centre ray is level.
    val bottom = unit(0f, -1.4f, -2f)
    val footprint = Placement.floorRange(eye, bottom, 0f)!!
    val horizontal = footprint * sqrt(bottom[0] * bottom[0] + bottom[2] * bottom[2])
    val centre = unit(0f, -0.2f, -1f)
    val range = Placement.rangeAtHorizontal(centre, horizontal)!!
    // 2 m ahead on the plan, so short of a wall 3 m away.
    assertEquals(2f, range * sqrt(centre[0] * centre[0] + centre[2] * centre[2]), 1e-4f)
  }

  @Test
  fun distanceFromHowTallTheObjectLooks() {
    // A 1.7 m fridge 850 px tall with a 1500 px focal length is 3 m away.
    assertEquals(3f, Placement.rangeFromSize("refrigerator", 850f, 1500f)!!, 1e-4f)
    assertNull(Placement.rangeFromSize("person", 850f, 1500f))
    assertNull(Placement.rangeFromSize("couch", 2f, 1500f))
  }
}
