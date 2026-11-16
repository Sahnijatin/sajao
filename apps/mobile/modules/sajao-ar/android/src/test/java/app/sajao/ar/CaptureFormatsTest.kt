package app.sajao.ar

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class CaptureFormatsTest {
  @Test
  fun cellsMatchTheAppsKeyframeCells() {
    // keyframes.ts: 30 degree sectors; bands split at -20 and 20 degrees.
    assertEquals("d0-1", KeyframeGate.cellOf(10.0, 0.0))
    assertEquals("d11-0", KeyframeGate.cellOf(-5.0, -30.0))
    assertEquals("d2-2", KeyframeGate.cellOf(75.0, 25.0))
  }

  @Test
  fun savesOnlyFramesClearlySharperThanTheCellsBest() {
    val gate = KeyframeGate()
    assertTrue(gate.shouldSave(10.0, 0.0, 100.0))
    gate.saved(10.0, 0.0, 100.0)
    assertFalse(gate.shouldSave(12.0, 1.0, 105.0))
    assertTrue(gate.shouldSave(12.0, 1.0, 111.0))
    // Another direction is a new cell.
    assertTrue(gate.shouldSave(50.0, 0.0, 20.0))
    assertFalse(gate.shouldSave(50.0, 0.0, 0.0))
  }

  @Test
  fun depthContainerLayout() {
    val entry = DepthEntry("k1", 2, 1, shortArrayOf(1500, 0), byteArrayOf(255.toByte(), 0))
    val out = ByteArrayOutputStream()
    DepthContainer.write(out, listOf(entry))
    val b = ByteBuffer.wrap(out.toByteArray()).order(ByteOrder.LITTLE_ENDIAN)
    val magic = ByteArray(8).also { b.get(it) }
    assertEquals("SJDEPTH1", String(magic, Charsets.US_ASCII))
    assertEquals(1, b.int)
    assertEquals(2, b.short.toInt())
    assertEquals("k1", String(ByteArray(2).also { b.get(it) }, Charsets.UTF_8))
    assertEquals(2, b.int)
    assertEquals(1, b.int)
    assertEquals(1500, b.short.toInt())
    assertEquals(0, b.short.toInt())
    assertEquals(255, b.get().toInt() and 0xff)
    assertEquals(0, b.get().toInt())
    assertEquals(0, b.remaining())
  }

  @Test
  fun nv21InterleavesVThenU() {
    // 2 by 2 image: four luma values, one chroma pair, padded rows.
    val y = byteArrayOf(1, 2, 9, 3, 4, 9)
    val u = byteArrayOf(50)
    val v = byteArrayOf(60)
    val nv21 = Nv21.from(2, 2, y, yRowStride = 3, u = u, v = v, uvRowStride = 1, uvPixelStride = 1)
    assertArrayEquals(byteArrayOf(1, 2, 3, 4, 60, 50), nv21)
  }
}
