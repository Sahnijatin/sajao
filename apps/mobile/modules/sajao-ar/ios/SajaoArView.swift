import ARKit
import AVFoundation
import ExpoModulesCore
import SceneKit
import UIKit

struct ArLabel: Equatable {
  let id: String
  let text: String
  let x: Double
  let y: Double
  let z: Double
}

/// The live AR scan. ARKit world tracking renders the camera and a mapping
/// overlay that is anchored to the room: on LiDAR phones the classified scene
/// mesh, elsewhere detected planes plus world-anchored feature points. An
/// on-device detector names objects; their positions are raycast into the
/// scene and sent to JavaScript, which decides the labels and sends them back
/// to be pinned here. Nothing drawn here sets a dimension.
final class SajaoArView: ExpoView, ARSCNViewDelegate, ARSessionDelegate {
  let onArStatus = EventDispatcher()
  let onArPose = EventDispatcher()
  let onArDetections = EventDispatcher()

  var lite = false
  var reducedMotion = false

  private let sceneView = ARSCNView(frame: .zero)
  private let labelLayer = UIView()
  private var labelViews: [String: GlassLabel] = [:]
  private var labels: [ArLabel] = []
  private let detector = DetectorRunner()
  private let lidar = ARWorldTrackingConfiguration.supportsSceneReconstruction(.meshWithClassification)

  private var wantsActive = false
  private var running = false
  private var hasRunOnce = false
  private var torchOn = false
  private var bloomConfigured = false
  private var displayLink: CADisplayLink?

  private var lastPoseAt: TimeInterval = 0
  private var lastStatusAt: TimeInterval = 0
  /// Paces AR frames to the detector: a steady 8 a second while it keeps up.
  private var pacer = FramePacer()
  private var detectionsDone = 0
  /// Detections the detector returned, and how many were placed in the room.
  private var detectionsFound = 0
  private var detectionsPlaced = 0
  private var lastDetectionMs: Double = 0
  private var lastPointsAt: TimeInterval = 0
  private var lastBrightnessAt: TimeInterval = 0
  private var brightness: Double = 128
  private var ambientIntensity: Double = 1000
  private var featureCount = 0

  /// World-anchored feature points (phones without LiDAR), keyed by ARKit's identifier.
  private var pointCloud: [UInt64: SIMD3<Float>] = [:]
  private let pointNode = SCNNode()
  private let maxPoints = 5000

  required init(appContext: AppContext? = nil) {
    super.init(appContext: appContext)
    clipsToBounds = true
    backgroundColor = .black
    sceneView.delegate = self
    sceneView.session.delegate = self
    sceneView.automaticallyUpdatesLighting = false
    sceneView.autoenablesDefaultLighting = false
    sceneView.antialiasingMode = .multisampling2X
    sceneView.scene.rootNode.addChildNode(pointNode)
    addSubview(sceneView)
    labelLayer.isUserInteractionEnabled = false
    addSubview(labelLayer)
  }

  override func layoutSubviews() {
    super.layoutSubviews()
    sceneView.frame = bounds
    labelLayer.frame = bounds
  }

  override func didMoveToWindow() {
    super.didMoveToWindow()
    if window == nil {
      stop()
    } else if wantsActive {
      start()
    }
  }

  deinit {
    displayLink?.invalidate()
    sceneView.session.pause()
  }

  // MARK: - Props

  func setActive(_ active: Bool) {
    wantsActive = active
    if active && window != nil {
      start()
    } else if !active {
      stop()
    }
  }

  func setTorch(_ on: Bool) {
    torchOn = on
    applyTorch()
  }

  func setLabels(_ next: [ArLabel]) {
    labels = next
    let ids = Set(next.map(\.id))
    for (id, view) in labelViews where !ids.contains(id) {
      view.removeFromSuperview()
      labelViews.removeValue(forKey: id)
    }
    for label in next {
      if let view = labelViews[label.id] {
        view.setText(label.text)
      } else {
        let view = GlassLabel(text: label.text)
        view.alpha = 0
        labelLayer.addSubview(view)
        labelViews[label.id] = view
      }
    }
  }

  // MARK: - Session

  private func start() {
    guard !running, ARWorldTrackingConfiguration.isSupported else { return }
    let config = ARWorldTrackingConfiguration()
    config.worldAlignment = .gravity
    config.planeDetection = [.horizontal, .vertical]
    config.isLightEstimationEnabled = true
    if lidar {
      config.sceneReconstruction = .meshWithClassification
    }
    // Resuming keeps what was mapped; only the first start resets.
    let options: ARSession.RunOptions = hasRunOnce ? [] : [.resetTracking, .removeExistingAnchors]
    sceneView.session.run(config, options: options)
    pacer.reset()
    hasRunOnce = true
    running = true
    let link = CADisplayLink(target: DisplayLinkProxy(self), selector: #selector(DisplayLinkProxy.tick))
    link.add(to: .main, forMode: .common)
    displayLink = link
    applyTorch()
  }

  private func stop() {
    guard running else { return }
    displayLink?.invalidate()
    displayLink = nil
    sceneView.session.pause()
    running = false
    setTorchHardware(false)
  }

  private func applyTorch() {
    guard running else { return }
    setTorchHardware(torchOn)
  }

  private func setTorchHardware(_ on: Bool) {
    guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else { return }
    do {
      try device.lockForConfiguration()
      device.torchMode = on ? .on : .off
      device.unlockForConfiguration()
    } catch {
      // The torch is a convenience; the scan works without it.
    }
  }

  // MARK: - Frames (main thread)

  func session(_ session: ARSession, didUpdate frame: ARFrame) {
    let now = frame.timestamp
    featureCount = frame.rawFeaturePoints?.points.count ?? 0
    if let estimate = frame.lightEstimate {
      ambientIntensity = Double(estimate.ambientIntensity)
    }
    if now - lastBrightnessAt > 0.25 {
      lastBrightnessAt = now
      brightness = meanBrightness(frame.capturedImage) ?? brightness
    }
    if now - lastPoseAt > 0.1 {
      lastPoseAt = now
      sendPose(frame)
    }
    if now - lastStatusAt > 0.25 {
      lastStatusAt = now
      sendStatus(frame)
    }
    if !lidar && now - lastPointsAt > 0.2 {
      lastPointsAt = now
      accumulatePoints(frame)
    }
    // The detector is fed from the AR session's own frames: ARKit owns the
    // camera during the scan, so nothing else can supply them.
    if detector.isAvailable && pacer.shouldSubmit(at: now, busy: detector.busy) {
      runDetector(frame)
    }
  }

  private func trackingName(_ state: ARCamera.TrackingState) -> String {
    switch state {
    case .normal: return "normal"
    case .notAvailable: return "notAvailable"
    case .limited(.initializing): return "initializing"
    case .limited: return "limited"
    }
  }

  private func sendPose(_ frame: ARFrame) {
    let t = frame.camera.transform
    // The camera looks down its -Z axis. Gravity aligned: +Y is up.
    let forward = SIMD3<Float>(-t.columns.2.x, -t.columns.2.y, -t.columns.2.z)
    let yaw = atan2(-forward.x, -forward.z) * 180 / .pi
    let pitch = asin(max(-1, min(1, forward.y))) * 180 / .pi
    onArPose([
      "yaw": Double(yaw),
      "pitch": Double(pitch),
      "x": Double(t.columns.3.x),
      "y": Double(t.columns.3.y),
      "z": Double(t.columns.3.z),
      "tracking": trackingName(frame.camera.trackingState),
    ])
  }

  private func sendStatus(_ frame: ARFrame) {
    var planes = 0
    var triangles = 0
    for anchor in frame.anchors {
      if anchor is ARPlaneAnchor { planes += 1 }
      if let mesh = anchor as? ARMeshAnchor { triangles += mesh.geometry.faces.count }
    }
    if !lidar { triangles = 0 }
    onArStatus([
      "tracking": trackingName(frame.camera.trackingState),
      "lidar": lidar,
      "planes": planes,
      "meshTriangles": triangles,
      "featurePoints": featureCount,
      "mappedPoints": pointCloud.count,
      "brightness": brightness,
      "ambientIntensity": ambientIntensity,
      "detector": detector.isAvailable,
      "labels": labels.count,
      "frames": pacer.frames,
      "detectorRuns": detectionsDone,
      "detectorSkipped": pacer.skippedBusy,
      "detectorMs": lastDetectionMs,
      "detectionsFound": detectionsFound,
      "detectionsPlaced": detectionsPlaced,
      "detectorError": detector.loadError ?? "",
    ])
  }

  /// Mean of a coarse grid of luma samples: cheap and enough for the light check.
  private func meanBrightness(_ buffer: CVPixelBuffer) -> Double? {
    guard CVPixelBufferGetPlaneCount(buffer) > 0 else { return nil }
    CVPixelBufferLockBaseAddress(buffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddressOfPlane(buffer, 0) else { return nil }
    let width = CVPixelBufferGetWidthOfPlane(buffer, 0)
    let height = CVPixelBufferGetHeightOfPlane(buffer, 0)
    let rowBytes = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
    let bytes = base.assumingMemoryBound(to: UInt8.self)
    let steps = 24
    var sum = 0
    for row in 0..<steps {
      let y = (row * height) / steps + height / (steps * 2)
      for column in 0..<steps {
        let x = (column * width) / steps + width / (steps * 2)
        sum += Int(bytes[y * rowBytes + x])
      }
    }
    return Double(sum) / Double(steps * steps)
  }

  // MARK: - Detector

  private func runDetector(_ frame: ARFrame) {
    let viewport = bounds.size
    guard viewport.width > 0, viewport.height > 0 else { return }
    let toView = frame.displayTransform(for: .portrait, viewportSize: viewport)
    detector.detect(pixelBuffer: frame.capturedImage) { [weak self] found, milliseconds in
      guard let self else { return }
      self.detectionsDone += 1
      self.lastDetectionMs = milliseconds
      guard self.running else { return }
      var payload: [[String: Any]] = []
      for detection in found {
        // Centre of the box in the upright image, back to the sensor image
        // (turned 90 degrees clockwise), then to view coordinates.
        let upright = CGPoint(x: detection.box.midX, y: detection.box.midY)
        let sensor = CGPoint(x: upright.y, y: 1 - upright.x)
        let normalised = sensor.applying(toView)
        let point = CGPoint(x: normalised.x * viewport.width, y: normalised.y * viewport.height)
        var entry: [String: Any] = [
          "detectorClass": detection.detectorClass,
          "score": Double(detection.score),
        ]
        self.detectionsFound += 1
        if let world = self.worldPoint(at: point) {
          self.detectionsPlaced += 1
          entry["world"] = ["x": Double(world.x), "y": Double(world.y), "z": Double(world.z)]
        }
        payload.append(entry)
      }
      self.onArDetections(["detections": payload])
    }
  }

  /// Where a screen point meets the room: the scene mesh or planes first,
  /// then estimated planes (which use depth on LiDAR phones).
  private func worldPoint(at point: CGPoint) -> SIMD3<Float>? {
    let hits = sceneView.hitTest(point, options: [.searchMode: SCNHitTestSearchMode.closest.rawValue])
    if let hit = hits.first(where: { $0.node.name == "sajao-surface" }) {
      let w = hit.worldCoordinates
      return SIMD3<Float>(Float(w.x), Float(w.y), Float(w.z))
    }
    guard
      let query = sceneView.raycastQuery(from: point, allowing: .estimatedPlane, alignment: .any),
      let result = sceneView.session.raycast(query).first
    else { return nil }
    let c = result.worldTransform.columns.3
    return SIMD3<Float>(c.x, c.y, c.z)
  }

  // MARK: - Feature points (no LiDAR)

  private func accumulatePoints(_ frame: ARFrame) {
    guard let cloud = frame.rawFeaturePoints, case .normal = frame.camera.trackingState else { return }
    for (index, id) in cloud.identifiers.enumerated() where pointCloud.count < maxPoints {
      pointCloud[id] = cloud.points[index]
    }
    let vertices = pointCloud.values.map { SCNVector3($0.x, $0.y, $0.z) }
    guard !vertices.isEmpty else { return }
    let source = SCNGeometrySource(vertices: vertices)
    let element = SCNGeometryElement(
      indices: Array(0..<UInt32(vertices.count)), primitiveType: .point)
    element.pointSize = 4
    element.minimumPointScreenSpaceRadius = 1.5
    element.maximumPointScreenSpaceRadius = 3
    let geometry = SCNGeometry(sources: [source], elements: [element])
    geometry.materials = [MeshStyle.dotMaterial()]
    pointNode.geometry = geometry
  }

  // MARK: - Scene nodes (render thread)

  func renderer(_ renderer: SCNSceneRenderer, nodeFor anchor: ARAnchor) -> SCNNode? {
    if let mesh = anchor as? ARMeshAnchor {
      let node = SCNNode()
      node.addChildNode(MeshStyle.meshNode(mesh.geometry, lite: lite))
      return node
    }
    if !lidar, let plane = anchor as? ARPlaneAnchor, let device = sceneView.device {
      let node = SCNNode()
      MeshStyle.addPlaneNodes(to: node, plane: plane, device: device, lite: lite)
      return node
    }
    return nil
  }

  func renderer(_ renderer: SCNSceneRenderer, didUpdate node: SCNNode, for anchor: ARAnchor) {
    if let mesh = anchor as? ARMeshAnchor {
      node.childNodes.forEach { $0.removeFromParentNode() }
      let child = MeshStyle.meshNode(mesh.geometry, lite: lite)
      node.addChildNode(child)
      if !reducedMotion { MeshStyle.brighten(child) }
      return
    }
    if !lidar, let plane = anchor as? ARPlaneAnchor {
      MeshStyle.updatePlaneNodes(node, plane: plane)
    }
  }

  func renderer(_ renderer: SCNSceneRenderer, updateAtTime time: TimeInterval) {
    guard !bloomConfigured, !lite, let camera = sceneView.pointOfView?.camera else { return }
    bloomConfigured = true
    camera.wantsHDR = true
    camera.wantsExposureAdaptation = false
    camera.exposureOffset = 0
    camera.bloomIntensity = 0.9
    camera.bloomThreshold = 0.55
    camera.bloomBlurRadius = 8
  }

  // MARK: - Labels (main thread, every display frame)

  @objc fileprivate func tick() {
    guard running else { return }
    let size = bounds.size
    for label in labels {
      guard let view = labelViews[label.id] else { continue }
      let projected = sceneView.projectPoint(SCNVector3(label.x, label.y, label.z))
      let onScreen =
        projected.z > 0 && projected.z < 1
        && projected.x > -40 && projected.x < Float(size.width) + 40
        && projected.y > -40 && projected.y < Float(size.height) + 40
      view.center = CGPoint(x: CGFloat(projected.x), y: CGFloat(projected.y) - 20)
      let target: CGFloat = onScreen ? 1 : 0
      view.alpha += (target - view.alpha) * (reducedMotion ? 1 : 0.25)
    }
  }
}

/// CADisplayLink keeps a strong reference to its target; this keeps the view free.
private final class DisplayLinkProxy {
  weak var view: SajaoArView?
  init(_ view: SajaoArView) { self.view = view }
  @objc func tick() { view?.tick() }
}

/// A frosted label pinned over an object: a dot and its name.
final class GlassLabel: UIView {
  private let blur = UIVisualEffectView(effect: UIBlurEffect(style: .systemUltraThinMaterialDark))
  private let label = UILabel()
  private let dot = UIView()

  init(text: String) {
    super.init(frame: .zero)
    isUserInteractionEnabled = false
    blur.layer.cornerRadius = 14
    blur.layer.masksToBounds = true
    blur.layer.borderWidth = 0.5
    blur.layer.borderColor = UIColor(white: 1, alpha: 0.35).cgColor
    addSubview(blur)
    dot.backgroundColor = MeshStyle.cyan
    dot.layer.cornerRadius = 3.5
    dot.layer.shadowColor = MeshStyle.cyan.cgColor
    dot.layer.shadowOpacity = 0.9
    dot.layer.shadowRadius = 4
    dot.layer.shadowOffset = .zero
    addSubview(dot)
    label.font = UIFont.systemFont(ofSize: 13, weight: .semibold)
    label.textColor = .white
    addSubview(label)
    setText(text)
  }

  required init?(coder: NSCoder) { fatalError("not used") }

  func setText(_ text: String) {
    guard label.text != text else { return }
    label.text = text
    label.sizeToFit()
    let width = label.bounds.width + 34
    bounds = CGRect(x: 0, y: 0, width: width, height: 28)
    blur.frame = bounds
    dot.frame = CGRect(x: 11, y: 10.5, width: 7, height: 7)
    label.frame = CGRect(x: 24, y: 0, width: label.bounds.width, height: 28)
  }
}
