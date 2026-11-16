import Foundation

/// Decides which AR camera frames go to the detector, so it sees a steady
/// stream (8 a second by default) instead of whatever is left over. Slots
/// are kept on a fixed grid from the first frame, so a late frame does not
/// push every later slot back; after a stall the grid restarts at once.
/// Pure and the same as `FramePacer.kt` on Android.
struct FramePacer {
  let interval: TimeInterval
  private var nextSlot: TimeInterval?

  /// Camera frames seen, frames sent to the detector, and frames skipped
  /// because the detector was still busy. Totals; the app turns them into rates.
  private(set) var frames = 0
  private(set) var submitted = 0
  private(set) var skippedBusy = 0

  init(fps: Double = 8) {
    interval = 1 / max(1, fps)
  }

  /// Call once per camera frame. True when this frame should be detected.
  mutating func shouldSubmit(at time: TimeInterval, busy: Bool) -> Bool {
    frames += 1
    guard let slot = nextSlot else {
      if busy { return false }
      nextSlot = time + interval
      submitted += 1
      return true
    }
    if time < slot { return false }
    if busy {
      skippedBusy += 1
      return false
    }
    // Stay on the grid unless more than a whole slot behind.
    nextSlot = time - slot > interval ? time + interval : slot + interval
    submitted += 1
    return true
  }

  mutating func reset() {
    nextSlot = nil
  }
}
