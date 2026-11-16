package app.sajao.ar

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FramePacerTest {
  /** Feeds `seconds` of camera frames at `cameraFps` with a detector that takes `detectSeconds`. */
  private fun run(cameraFps: Double, detectSeconds: Double, seconds: Double = 10.0): FramePacer {
    val pacer = FramePacer()
    var busyUntil = -1.0
    val frames = (seconds * cameraFps).toInt()
    for (i in 0 until frames) {
      val t = i / cameraFps
      if (pacer.shouldSubmit(t, busy = t < busyUntil)) busyUntil = t + detectSeconds
    }
    return pacer
  }

  private fun detectorFps(pacer: FramePacer, seconds: Double = 10.0) = pacer.submitted / seconds

  @Test
  fun steadyEightPerSecondAtSixtyFps() {
    val fps = detectorFps(run(cameraFps = 60.0, detectSeconds = 0.04))
    assertTrue("detector fps $fps", fps in 7.5..8.5)
  }

  @Test
  fun steadyAtThirtyFps() {
    val fps = detectorFps(run(cameraFps = 30.0, detectSeconds = 0.04))
    assertTrue("detector fps $fps", fps in 7.0..8.5)
  }

  @Test
  fun aSlowDetectorStillGetsAtLeastFivePerSecond() {
    // A budget phone: 150 ms per detection.
    val fps = detectorFps(run(cameraFps = 30.0, detectSeconds = 0.15))
    assertTrue("detector fps $fps", fps in 5.0..7.0)
  }

  @Test
  fun neverMoreThanTenPerSecond() {
    val fps = detectorFps(run(cameraFps = 120.0, detectSeconds = 0.0))
    assertTrue("detector fps $fps", fps <= 10.0)
  }

  @Test
  fun busyFramesAreCountedNotSent() {
    val pacer = FramePacer()
    assertTrue(pacer.shouldSubmit(0.0, busy = false))
    assertFalse(pacer.shouldSubmit(0.2, busy = true))
    assertEquals(1, pacer.skippedBusy)
    assertTrue(pacer.shouldSubmit(0.21, busy = false))
    assertEquals(3, pacer.frames)
    assertEquals(2, pacer.submitted)
  }

  @Test
  fun aStallRestartsTheGridInsteadOfBursting() {
    val pacer = FramePacer()
    assertTrue(pacer.shouldSubmit(0.0, busy = false))
    // Two seconds with no frames (app in the background), then 30 fps again.
    assertTrue(pacer.shouldSubmit(2.0, busy = false))
    assertFalse(pacer.shouldSubmit(2.033, busy = false))
    assertFalse(pacer.shouldSubmit(2.066, busy = false))
  }
}
