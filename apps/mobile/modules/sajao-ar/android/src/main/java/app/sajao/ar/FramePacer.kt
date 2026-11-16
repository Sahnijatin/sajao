package app.sajao.ar

/**
 * Decides which AR camera frames go to the detector, so it sees a steady
 * stream (8 a second by default) instead of whatever is left over. Slots are
 * kept on a fixed grid from the first frame, so a late frame does not push
 * every later slot back; after a stall the grid restarts at once. Pure and
 * the same as `FramePacer.swift` on iOS.
 */
class FramePacer(fps: Double = 8.0) {
  val interval: Double = 1.0 / maxOf(1.0, fps)
  private var nextSlot: Double? = null

  /** Camera frames seen. Totals; the app turns them into rates. */
  var frames = 0
    private set

  /** Frames sent to the detector. */
  var submitted = 0
    private set

  /** Frames skipped because the detector was still busy. */
  var skippedBusy = 0
    private set

  /** Call once per camera frame, time in seconds. True when this frame should be detected. */
  fun shouldSubmit(time: Double, busy: Boolean): Boolean {
    frames += 1
    val slot = nextSlot
    if (slot == null) {
      if (busy) return false
      nextSlot = time + interval
      submitted += 1
      return true
    }
    if (time < slot) return false
    if (busy) {
      skippedBusy += 1
      return false
    }
    // Stay on the grid unless more than a whole slot behind.
    nextSlot = if (time - slot > interval) time + interval else slot + interval
    submitted += 1
    return true
  }

  fun reset() {
    nextSlot = null
  }
}
