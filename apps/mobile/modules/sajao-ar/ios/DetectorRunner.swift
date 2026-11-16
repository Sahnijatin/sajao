import CoreImage
import Foundation
@_implementationOnly import MediaPipeTasksVision
import UIKit

/// One detection in the upright camera image. The box is normalised, 0 to 1.
struct UprightDetection {
  let detectorClass: String
  let score: Float
  let box: CGRect
}

/// Runs EfficientDet-Lite0 (COCO classes, Apache 2.0) through MediaPipe on a
/// background queue, one image at a time. Any failure means no detections:
/// the scan carries on without labels.
final class DetectorRunner {
  private var detector: ObjectDetector?
  private let queue = DispatchQueue(label: "app.sajao.ar.detector", qos: .userInitiated)
  private let context = CIContext(options: [.cacheIntermediates: false])
  /// Read and written on the main thread only.
  private(set) var busy = false

  /// The detector sees images this wide; plenty for room-scale objects.
  private let inputWidth: CGFloat = 480

  init() {
    guard let path = DetectorRunner.modelPath() else { return }
    let options = ObjectDetectorOptions()
    options.baseOptions.modelAssetPath = path
    options.runningMode = .image
    options.maxResults = 10
    options.scoreThreshold = 0.4
    detector = try? ObjectDetector(options: options)
  }

  var isAvailable: Bool { detector != nil }

  private static func modelPath() -> String? {
    let name = "efficientdet_lite0"
    let owner = Bundle(for: DetectorRunner.self)
    if let url = owner.url(forResource: "SajaoArAssets", withExtension: "bundle"),
      let assets = Bundle(url: url),
      let path = assets.path(forResource: name, ofType: "tflite")
    {
      return path
    }
    if let url = Bundle.main.url(forResource: "SajaoArAssets", withExtension: "bundle"),
      let assets = Bundle(url: url),
      let path = assets.path(forResource: name, ofType: "tflite")
    {
      return path
    }
    return owner.path(forResource: name, ofType: "tflite")
      ?? Bundle.main.path(forResource: name, ofType: "tflite")
  }

  /// Detect objects in a camera image (landscape sensor orientation). The
  /// image is turned upright first, so sofas and fridges look the way the
  /// model was trained on. Must be called on the main thread.
  func detect(
    pixelBuffer: CVPixelBuffer,
    completion: @escaping ([UprightDetection]) -> Void
  ) {
    guard let detector, !busy else { return }
    busy = true
    let image = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
    queue.async { [weak self] in
      guard let self else { return }
      var found: [UprightDetection] = []
      let extent = image.extent
      let scale = self.inputWidth / max(1, extent.width)
      let scaled = image
        .transformed(by: CGAffineTransform(translationX: -extent.origin.x, y: -extent.origin.y))
        .transformed(by: CGAffineTransform(scaleX: scale, y: scale))
      if let cgImage = self.context.createCGImage(scaled, from: scaled.extent),
        let mpImage = try? MPImage(uiImage: UIImage(cgImage: cgImage)),
        let result = try? detector.detect(image: mpImage)
      {
        let width = CGFloat(cgImage.width)
        let height = CGFloat(cgImage.height)
        for detection in result.detections {
          guard let category = detection.categories.first,
            let name = category.categoryName, width > 0, height > 0
          else { continue }
          let box = detection.boundingBox
          found.append(
            UprightDetection(
              detectorClass: name,
              score: category.score,
              box: CGRect(
                x: box.minX / width,
                y: box.minY / height,
                width: box.width / width,
                height: box.height / height
              )
            )
          )
        }
      }
      DispatchQueue.main.async {
        self.busy = false
        completion(found)
      }
    }
  }
}
