import ARKit
import AVFoundation
import Foundation

/// Records the scan video on iOS from the AR session's own camera images:
/// ARKit owns the camera during the scan, so nothing else can record it.
/// One H.264 MP4 from the first frame to Done, whatever tracking says, at up
/// to 30 frames a second, in sensor orientation like the keyframes. Frame
/// times are the AR frames' own timestamps, so the server can line the video
/// up with the AR poses in the sensor log.
///
/// Used on the main thread (the AR session's delegate queue). Any failure
/// stops the video only: the scan and the rest of the package carry on.
final class ScanVideoWriter {
  static let maxFps = 30.0
  static let bitsPerSecond = 6_000_000

  private let url: URL
  private var writer: AVAssetWriter?
  private var input: AVAssetWriterInput?
  private var adaptor: AVAssetWriterInputPixelBufferAdaptor?
  private var lastSeconds = -1.0
  private var frames = 0
  private var finished = false
  /// "off", "recording", "saved (N KB)" or "failed: ...". Shown in the debug overlay.
  private(set) var status = "off"

  init(url: URL) {
    self.url = url
  }

  /// Offer every AR frame; frames closer together than the frame rate allows are skipped.
  func append(_ frame: ARFrame) {
    guard !finished, !status.hasPrefix("failed") else { return }
    let seconds = frame.timestamp
    guard seconds - lastSeconds >= 1.0 / Self.maxFps - 0.002 else { return }
    let buffer = frame.capturedImage
    if writer == nil {
      start(width: CVPixelBufferGetWidth(buffer), height: CVPixelBufferGetHeight(buffer), at: seconds)
    }
    guard let writer, let input, let adaptor else { return }
    guard writer.status == .writing else {
      if writer.status == .failed { fail(writer.error) }
      return
    }
    // The encoder is behind: drop this frame rather than hold up the AR session.
    guard input.isReadyForMoreMediaData else { return }
    let time = CMTime(seconds: seconds, preferredTimescale: 1_000_000)
    if adaptor.append(buffer, withPresentationTime: time) {
      frames += 1
      lastSeconds = seconds
    } else {
      fail(writer.error)
    }
  }

  private func start(width: Int, height: Int, at seconds: Double) {
    try? FileManager.default.removeItem(at: url)
    do {
      let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
      let compression: [String: Any] = [
        AVVideoAverageBitRateKey: Self.bitsPerSecond,
        AVVideoExpectedSourceFrameRateKey: Int(Self.maxFps),
        AVVideoMaxKeyFrameIntervalKey: Int(Self.maxFps),
      ]
      let settings: [String: Any] = [
        AVVideoCodecKey: AVVideoCodecType.h264,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: compression,
      ]
      guard writer.canApply(outputSettings: settings, forMediaType: .video) else {
        throw NSError(
          domain: "SajaoAr", code: 1,
          userInfo: [NSLocalizedDescriptionKey: "video settings not supported at \(width)x\(height)"])
      }
      let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
      input.expectsMediaDataInRealTime = true
      let adaptor = AVAssetWriterInputPixelBufferAdaptor(
        assetWriterInput: input, sourcePixelBufferAttributes: nil)
      guard writer.canAdd(input) else {
        throw NSError(
          domain: "SajaoAr", code: 2,
          userInfo: [NSLocalizedDescriptionKey: "video input could not be added"])
      }
      writer.add(input)
      guard writer.startWriting() else {
        throw writer.error
          ?? NSError(
            domain: "SajaoAr", code: 3,
            userInfo: [NSLocalizedDescriptionKey: "video writer did not start"])
      }
      writer.startSession(atSourceTime: CMTime(seconds: seconds, preferredTimescale: 1_000_000))
      self.writer = writer
      self.input = input
      self.adaptor = adaptor
      status = "recording"
    } catch {
      fail(error)
    }
  }

  private func fail(_ error: Error?) {
    let reason = error.map { String(describing: $0) } ?? "unknown"
    status = "failed: \(String(reason.prefix(300)))"
  }

  /// Close the file. Calls back on the main thread with the file's uri, or nil when nothing was recorded.
  func finish(completion: @escaping (String?) -> Void) {
    guard !finished, let writer, let input, writer.status == .writing, frames > 0 else {
      finished = true
      completion(nil)
      return
    }
    finished = true
    let url = self.url
    input.markAsFinished()
    writer.finishWriting { [weak self] in
      DispatchQueue.main.async {
        guard writer.status == .completed else {
          self?.fail(writer.error)
          completion(nil)
          return
        }
        let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
        let bytes = (attributes?[.size] as? NSNumber)?.intValue ?? 0
        self?.status = "saved (\(bytes / 1024) KB)"
        completion(bytes > 0 ? url.absoluteString : nil)
      }
    }
  }

  /// Stop without keeping the file: the view went away before Done.
  func cancel() {
    guard !finished else { return }
    finished = true
    input?.markAsFinished()
    writer?.cancelWriting()
    try? FileManager.default.removeItem(at: url)
  }
}
