package app.sajao.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SurfaceMeshTest {
  @Test
  fun aOneMetreSquareGetsAGridInside() {
    val square = floatArrayOf(-0.5f, -0.5f, 0.5f, -0.5f, 0.5f, 0.5f, -0.5f, 0.5f)
    val lines = SurfaceMesh.gridLines(square)
    // x = -0.3, 0, 0.3 and z = -0.3, 0, 0.3: six lines of four numbers.
    assertEquals(24, lines.size)
    for (n in lines) assertTrue("inside: $n", n >= -0.5001f && n <= 0.5001f)
  }

  @Test
  fun gridLinesStayInsideATriangle() {
    val triangle = floatArrayOf(0f, 0f, 2f, 0f, 0f, 2f)
    val lines = SurfaceMesh.gridLines(triangle)
    assertTrue(lines.isNotEmpty())
    for (i in lines.indices step 2) assertTrue(lines[i] + lines[i + 1] <= 2.0001f)
  }

  @Test
  fun tinyPlanesGetNoGrid() {
    assertEquals(0, SurfaceMesh.gridLines(floatArrayOf(0f, 0f, 0.1f, 0f, 0.1f, 0.1f)).size)
  }

  @Test
  fun nearbyPointsJoinAndFarOnesDoNot() {
    val points = listOf(
      floatArrayOf(0f, 0f, 0f),
      floatArrayOf(0.1f, 0f, 0f),
      floatArrayOf(0.2f, 0f, 0f),
      floatArrayOf(5f, 0f, 0f),
    )
    val edges = SurfaceMesh.links(points)
    val pairs = edges.toList().chunked(2).map { it[0] to it[1] }.toSet()
    assertTrue((0 to 1) in pairs)
    assertTrue((1 to 2) in pairs)
    assertTrue(pairs.none { it.first == 3 || it.second == 3 })
    assertEquals(pairs.size * 2, edges.size)
  }

  @Test
  fun eachPointJoinsAFewNeighboursAndThousandsStayFast() {
    val points = (0 until 3000).map { i -> floatArrayOf((i % 30) * 0.1f, (i / 900) * 0.1f, ((i / 30) % 30) * 0.1f) }
    val started = System.nanoTime()
    val edges = SurfaceMesh.links(points)
    val ms = (System.nanoTime() - started) / 1e6
    assertTrue("edges ${edges.size / 2}", edges.size / 2 <= points.size * SurfaceMesh.LINKS_PER_POINT)
    assertTrue("took $ms ms", ms < 1000)
  }
}
