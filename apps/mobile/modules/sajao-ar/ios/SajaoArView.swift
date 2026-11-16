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
  let onArSurfaces = EventDispatcher()
  let onArKeyframe = EventDispatcher()
  /// Records the capture package's native files while a capture id is set.
  private var recorder: CaptureRecorder?
  /// Records the scan video while a capture id is set.
  private var video: ScanVideoWriter?
  private var captureId = ""

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
  /// Coverage hits from planes and from tracked points, for the overlay.
  private var surfacePlaneHits = 0
  private var surfacePointHits = 0
  /// How placed detections were placed: floor, plane, points or size.
  private var placedCounts: [String: Int] = [:]
  private var lastDetectionMs: Double = 0
  private var lastPointsAt: TimeInterval = 0
  private var lastBrightnessAt: TimeInterval = 0
  private var lastSurfacesAt: TimeInterval = 0
  private var lastKeyframeAt: TimeInterval = 0
  private var brightness: Double = 128
  private var ambientIntensity: Double = 1000
  private var featureCount = 0
  /// Height of the lowest horizontal plane seen: the floor.
  private var floorY: Float?

  /// World-anchored feature points (phones without LiDAR), keyed by ARKit's identifier.
  private var pointCloud: [UInt64: SIMD3<Float>] = [:]
  private let pointNode = SCNNode()
  private let maxPoints = 5000
  /// Point ids oldest first, so a full cloud drops its oldest point and newly mapped areas keep appearing.
  private var pointOrder: [UInt64] = []
  /// Tracked points joined to their nearest neighbours: the wire mesh over non-flat things.
  private let linkNode = SCNNode()
  private var lastLinksAt: TimeInterval = 0
  private let maxLinkedPoints = 2500
  private let linkQueue = DispatchQueue(label: "app.sajao.ar.links", qos: .utility)
  private var linksBusy = false

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
    sceneView.scene.rootNode.addChildNode(linkNode)
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
    video?.cancel()
    displayLink?.invalidate()
    sceneView.session.pause()
  }

  // MARK: - Props

  /// Start recording a capture package into its own folder; an empty id records nothing.
  func setCaptureId(_ id: String) {
    guard id != captureId else { return }
    captureId = id
    video?.cancel()
    recorder = id.isEmpty
      ? nil
      : CaptureRecorder(dir: CaptureRecorder.folder(id)) { [weak self] payload in self?.onArKeyframe(payload) }
    // The recorder creates the folder the video is written into.
    video = id.isEmpty
      ? nil
      : ScanVideoWriter(url: CaptureRecorder.folder(id).appendingPathComponent("scan.mp4"))
  }

  /// Delete keyframe candidates the app's recorder dropped.
  func discardKeyframes(_ uris: [String]) {
    recorder?.discard(uris)
  }

  /// End the capture: planes and the LiDAR mesh from the session, depth for
  /// the chosen keyframes; resolves with the files' uris.
  func finishCapture(_ chosen: [String], completion: @escaping ([String: Any?]) -> Void) {
    guard let recorder else {
      completion(["planes": nil, "sceneMesh": nil, "depth": nil, "video": nil])
      return
    }
    let anchors = sceneView.session.currentFrame?.anchors ?? []
    let finishFiles: (String?) -> Void = { videoUri in
      recorder.finish(
        planes: anchors.compactMap { $0 as? ARPlaneAnchor },
        meshes: anchors.compactMap { $0 as? ARMeshAnchor },
        chosen: chosen
      ) { files in
        var result = files
        result.updateValue(videoUri, forKey: "video")
        completion(result)
      }
    }
    // The video is closed first, then the rest of the package is written.
    if let video {
      video.finish(completion: finishFiles)
    } else {
      finishFiles(nil)
    }
  }

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
    // LiDAR depth per frame, saved with each keyframe for the twin.
    if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
      config.frameSemantics.insert(.sceneDepth)
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
    // The scan video: every frame from the first to Done, whatever tracking says.
    video?.append(frame)
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
    if now - lastSurfacesAt > 0.25, case .normal = frame.camera.trackingState {
      lastSurfacesAt = now
      let sharpness = Self.sharpness(frame.capturedImage) ?? 0
      sendSurfaces(frame, sharpness: sharpness)
    }
    // Keyframes are offered whatever tracking says; without tracking they
    // are kept by time, without a pose.
    if let recorder, now - lastKeyframeAt > 0.25 {
      lastKeyframeAt = now
      let sharpness = Self.sharpness(frame.capturedImage) ?? 0
      let (yaw, pitch) = Self.yawPitch(frame.camera.transform)
      recorder.offer(frame, sharpness: sharpness, yaw: yaw, pitch: pitch)
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

  /// Where the camera points: yaw and pitch in degrees, gravity aligned.
  static func yawPitch(_ t: simd_float4x4) -> (Double, Double) {
    // The camera looks down its -Z axis. Gravity aligned: +Y is up.
    let forward = SIMD3<Float>(-t.columns.2.x, -t.columns.2.y, -t.columns.2.z)
    let yaw = atan2(-forward.x, -forward.z) * 180 / .pi
    let pitch = asin(max(-1, min(1, forward.y))) * 180 / .pi
    return (Double(yaw), Double(pitch))
  }

  private func sendPose(_ frame: ARFrame) {
    let t = frame.camera.transform
    let (yaw, pitch) = Self.yawPitch(t)
    onArPose([
      "yaw": yaw,
      "pitch": pitch,
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
      if let plane = anchor as? ARPlaneAnchor {
        planes += 1
        // The lowest horizontal plane is the floor.
        if plane.alignment == .horizontal {
          let y = plane.transform.columns.3.y
          floorY = min(floorY ?? y, y)
        }
      }
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
      "detectorStatus": detector.status,
      "cameraImage": "\(Int(frame.camera.imageResolution.width))x\(Int(frame.camera.imageResolution.height))",
      "planeStates": "tracking \(planes)",
      "surfaceHits": "planes \(surfacePlaneHits) points \(surfacePointHits)",
      "placedBy": ["floor", "plane", "points", "size"].map { "\($0) \(placedCounts[$0] ?? 0)" }.joined(separator: " "),
      "detectorError": detector.loadError ?? "",
      "video": video?.status ?? "off",
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
    // Each detection's ray is built from the camera as it was for this frame,
    // so a result that arrives after the phone moved still lands on its object.
    let camera = CaptureCamera(frame.camera)
    let cloud = lidar ? [] : Array(pointCloud.values)
    detector.detect(pixelBuffer: frame.capturedImage) { [weak self] found, milliseconds in
      guard let self else { return }
      self.detectionsDone += 1
      self.lastDetectionMs = milliseconds
      guard self.running else { return }
      var payload: [[String: Any]] = []
      for detection in found {
        // Centre of the box in the upright image, back to the sensor image
        // (turned 90 degrees clockwise), then a ray into the room.
        let upright = CGPoint(x: detection.box.midX, y: detection.box.midY)
        let sensor = CGPoint(x: upright.y, y: 1 - upright.x)
        let ray = camera.ray(throughNormalised: sensor)
        let bottom = camera.ray(throughNormalised: CGPoint(x: detection.box.maxY, y: 1 - upright.x))
        // The box's upright height runs along the sensor image's x axis.
        let sighting = self.locate(
          ray, cloud: cloud, detectorClass: detection.detectorClass, bottom: bottom,
          heightPx: Float(detection.box.height * camera.resolution.width),
          focalPx: camera.intrinsics.columns.0.x)
        var entry: [String: Any] = [
          "detectorClass": detection.detectorClass,
          "score": Double(detection.score),
          "surface": sighting.surface,
          // The upright box, for "step back" when a large object is cut off.
          "box": [
            "x": Double(detection.box.minX), "y": Double(detection.box.minY),
            "width": Double(detection.box.width), "height": Double(detection.box.height),
          ],
        ]
        self.detectionsFound += 1
        if let point = sighting.point {
          self.detectionsPlaced += 1
          self.placedCounts[sighting.placedBy, default: 0] += 1
          entry["placedBy"] = sighting.placedBy
          entry["world"] = ["x": Double(point.x), "y": Double(point.y), "z": Double(point.z)]
          entry["range"] = Double(sighting.range)
        }
        if let gap = sighting.gap { entry["gap"] = Double(gap) }
        payload.append(entry)
      }
      self.onArDetections(["detections": payload])
    }
  }

  private struct Sighting {
    var point: SIMD3<Float>?
    var range: Float = 0
    var surface = "none"
    var gap: Float?
    /// floor, points, plane or size: how the point was found.
    var placedBy = ""
  }

  /// Typical heights of the large objects the scan names, in metres: only for placing labels. Same as Android.
  private static let typicalHeight: [String: Float] = [
    "couch": 0.85, "bed": 0.6, "dining table": 0.76, "refrigerator": 1.7, "tv": 0.6,
    "chair": 0.9, "microwave": 0.3,
  ]
  private static let standsOnFloor: Set<String> = ["couch", "bed", "dining table", "refrigerator", "chair"]

  /// Distance along a ray to where it meets the floor, or nil when it points up or meets it out of range.
  private static func floorRange(_ ray: Ray, floorY: Float) -> Float? {
    guard ray.direction.y < -0.02 else { return nil }
    let t = (floorY - ray.origin.y) / ray.direction.y
    return (0.3...maxRange).contains(t) ? t : nil
  }

  /// Distance along a ray at which it is `horizontal` metres away on the floor plan.
  private static func rangeAtHorizontal(_ ray: Ray, _ horizontal: Float) -> Float? {
    let flat = simd_length(SIMD2(ray.direction.x, ray.direction.z))
    guard flat >= 0.05 else { return nil }
    let t = horizontal / flat
    return (0.3...maxRange).contains(t) ? t : nil
  }

  private static let maxRange: Float = 8
  /// Feature points within this angle of the ray belong to what it points at.
  private static let coneTan: Float = tanf(2.5 * Float.pi / 180)

  /// Where a detection is: the object's own point on the ray (scene mesh on
  /// LiDAR phones, tracked feature points elsewhere, an estimated plane as a
  /// last resort), plus the plane the same ray meets and the gap between
  /// them. A gap near zero means the "object" is the wall or floor itself.
  private func locate(
    _ ray: Ray, cloud: [SIMD3<Float>], detectorClass: String, bottom: Ray, heightPx: Float, focalPx: Float
  ) -> Sighting {
    var sighting = Sighting()
    var objectRange: Float?
    // A standing object: its footprint where the box bottom meets the floor,
    // so a fridge is placed in front of the wall, not on it.
    if Self.standsOnFloor.contains(detectorClass), let floorY,
      let t = Self.floorRange(bottom, floorY: floorY)
    {
      let horizontal = t * simd_length(SIMD2(bottom.direction.x, bottom.direction.z))
      if let range = Self.rangeAtHorizontal(ray, horizontal) {
        objectRange = range
        sighting.placedBy = "floor"
      }
    }
    if objectRange != nil {
      // Placed from the floor.
    } else if lidar && !lite {
      let end = ray.origin + ray.direction * Self.maxRange
      let hits = sceneView.scene.rootNode.hitTestWithSegment(
        from: SCNVector3(ray.origin.x, ray.origin.y, ray.origin.z),
        to: SCNVector3(end.x, end.y, end.z),
        options: [
          SCNHitTestOption.searchMode.rawValue: SCNHitTestSearchMode.all.rawValue,
          SCNHitTestOption.backFaceCulling.rawValue: false,
        ])
      objectRange = hits
        .filter { $0.node.name == "sajao-surface" }
        .map { hit -> Float in
          let w = hit.worldCoordinates
          return simd_dot(SIMD3<Float>(Float(w.x), Float(w.y), Float(w.z)) - ray.origin, ray.direction)
        }
        .filter { $0 > 0.1 }
        .min()
      if objectRange != nil { sighting.placedBy = "points" }
    }
    // Without LiDAR: detected planes, then tracked points around the ray,
    // then ARKit's estimated planes, then how tall the object looks.
    if objectRange == nil {
      let query = ARRaycastQuery(
        origin: ray.origin, direction: ray.direction, allowing: .existingPlaneGeometry, alignment: .any)
      if let hit = sceneView.session.raycast(query).first {
        let c = hit.worldTransform.columns.3
        objectRange = simd_dot(SIMD3<Float>(c.x, c.y, c.z) - ray.origin, ray.direction)
        sighting.placedBy = "plane"
      }
    }
    if objectRange == nil, !cloud.isEmpty, let range = Self.frontOfCone(ray, cloud: cloud) {
      objectRange = range
      sighting.placedBy = "points"
    }
    if objectRange == nil {
      let query = ARRaycastQuery(
        origin: ray.origin, direction: ray.direction, allowing: .estimatedPlane, alignment: .any)
      if let hit = sceneView.session.raycast(query).first {
        let c = hit.worldTransform.columns.3
        objectRange = simd_dot(SIMD3<Float>(c.x, c.y, c.z) - ray.origin, ray.direction)
        sighting.placedBy = "plane"
      }
    }
    if objectRange == nil, let height = Self.typicalHeight[detectorClass], heightPx >= 8 {
      let t = focalPx * height / heightPx
      if (0.3...Self.maxRange).contains(t) {
        objectRange = t
        sighting.placedBy = "size"
      }
    }
    if let range = objectRange {
      sighting.point = ray.origin + ray.direction * range
      sighting.range = range
    }

    let planeQuery = ARRaycastQuery(
      origin: ray.origin, direction: ray.direction, allowing: .existingPlaneGeometry, alignment: .any)
    if let hit = sceneView.session.raycast(planeQuery).first(where: { $0.anchor is ARPlaneAnchor }),
      let plane = hit.anchor as? ARPlaneAnchor
    {
      let c = hit.worldTransform.columns.3
      sighting.surface = surfaceKind(plane, hitY: c.y, cameraY: ray.origin.y)
      if let range = objectRange {
        let planeRange = simd_dot(SIMD3<Float>(c.x, c.y, c.z) - ray.origin, ray.direction)
        sighting.gap = max(0, planeRange - range)
      }
    }
    return sighting
  }

  /// The front of whatever the ray points at: the near quarter of the
  /// feature points inside a narrow cone around it. Needs three points.
  private static func frontOfCone(_ ray: Ray, cloud: [SIMD3<Float>]) -> Float? {
    var ranges: [Float] = []
    for point in cloud {
      let v = point - ray.origin
      let along = simd_dot(v, ray.direction)
      guard along > 0.2, along < maxRange else { continue }
      let off = simd_length(v - ray.direction * along)
      if off < along * coneTan { ranges.append(along) }
    }
    guard ranges.count >= 3 else { return nil }
    ranges.sort()
    return ranges[ranges.count / 4]
  }

  /// Walls, floor and ceiling from ARKit's plane classes where the phone has
  /// them; otherwise from the plane's size and height.
  private func surfaceKind(_ plane: ARPlaneAnchor, hitY: Float, cameraY: Float) -> String {
    if ARPlaneAnchor.isClassificationSupported {
      switch plane.classification {
      case .wall, .door, .window: return "wall"
      case .floor: return "floor"
      case .ceiling: return "ceiling"
      case .table, .seat: return "raised"
      default: break
      }
    }
    if plane.alignment == .vertical {
      return Self.longestSide(plane) >= 1.2 ? "wall" : "none"
    }
    if let floor = floorY, hitY <= floor + 0.15 { return "floor" }
    return hitY > cameraY + 0.3 ? "ceiling" : "raised"
  }

  private static func longestSide(_ plane: ARPlaneAnchor) -> Float {
    max(plane.planeExtent.width, plane.planeExtent.height)
  }

  // MARK: - Coverage on walls and floor

  /// Where the rays go, as normalised sensor image points: a 4 by 3 grid away from the edges.
  private static let surfaceGrid: [CGPoint] = [0.2, 0.4, 0.6, 0.8].flatMap { x in
    [0.25, 0.5, 0.75].map { y in CGPoint(x: x, y: y) }
  }

  /// A 4 by 3 grid of rays from the camera into the planes found so far,
  /// with the frame's sharpness. JavaScript decides whether the sample
  /// counts (slow turn, sharp frame). Same as Android.
  private func sendSurfaces(_ frame: ARFrame, sharpness: Double) {
    let camera = CaptureCamera(frame.camera)
    var hits: [[String: Any]] = []
    let cloud = lidar ? [] : Array(pointCloud.values)
    for point in Self.surfaceGrid {
      let ray = camera.ray(throughNormalised: point)
      // Without LiDAR ARKit finds only patches of a plain wall, so each
      // plane counts a little beyond its found outline: a frame then counts
      // toward every wall it sees.
      let query = ARRaycastQuery(
        origin: ray.origin, direction: ray.direction, allowing: .existingPlaneInfinite, alignment: .any)
      guard
        let hit = sceneView.session.raycast(query).first(where: { result in
          guard let plane = result.anchor as? ARPlaneAnchor else { return false }
          return Self.nearPlane(plane, result.worldTransform.columns.3)
        }),
        let plane = hit.anchor as? ARPlaneAnchor
      else {
        // Few planes found: tracked feature points on the ray still count.
        if let range = Self.frontOfCone(ray, cloud: cloud), let fromPoints = pointHit(ray, range: range) {
          surfacePointHits += 1
          hits.append(fromPoints)
        }
        continue
      }
      surfacePlaneHits += 1
      let c = hit.worldTransform.columns.3
      let kind = surfaceKind(plane, hitY: c.y, cameraY: ray.origin.y)
      guard kind == "wall" || kind == "floor" else { continue }
      // A plane's normal is its +Y axis.
      let n = plane.transform.columns.1
      let normalYaw = atan2(Double(n.x), Double(n.z)) * 180 / .pi
      let offset = Double(n.x * c.x + n.y * c.y + n.z * c.z)
      hits.append([
        "kind": kind, "normalYaw": normalYaw, "offset": offset,
        "x": Double(c.x), "y": Double(c.y), "z": Double(c.z),
      ])
    }
    var payload: [String: Any] = ["sharpness": sharpness, "hits": hits]
    if let floorY { payload["floorY"] = Double(floorY) }
    onArSurfaces(payload)
  }

  /// A coverage hit from tracked feature points, where no plane was found:
  /// at floor height as floor, otherwise a wall facing the camera; steeply
  /// up or down and not at the floor counts as nothing. Same as Android's
  /// `SurfaceSample.pointHit`, which is unit tested.
  private func pointHit(_ ray: Ray, range: Float) -> [String: Any]? {
    let p = ray.origin + ray.direction * range
    let atFloor = floorY.map { p.y <= $0 + 0.15 } ?? (p.y <= ray.origin.y - 1.1)
    let position: [String: Any] = ["x": Double(p.x), "y": Double(p.y), "z": Double(p.z)]
    if atFloor {
      return position.merging(["kind": "floor", "normalYaw": 0.0, "offset": 0.0]) { a, _ in a }
    }
    guard abs(ray.direction.y) <= 0.7 else { return nil }
    let n = SIMD2<Float>(-ray.direction.x, -ray.direction.z)
    guard simd_length(n) > 1e-3 else { return nil }
    let unit = simd_normalize(n)
    let normalYaw = atan2(Double(unit.x), Double(unit.y)) * 180 / .pi
    let offset = Double(unit.x * p.x + unit.y * p.z)
    return position.merging(["kind": "wall", "normalYaw": normalYaw, "offset": offset]) { a, _ in a }
  }

  /// How far past a plane's found outline a surface sample still counts, in metres.
  private static let planeReach: Float = 1.5

  /// True when a point on a plane's infinite extension is within reach of the part ARKit found.
  private static func nearPlane(_ plane: ARPlaneAnchor, _ point: SIMD4<Float>) -> Bool {
    let local = plane.transform.inverse * SIMD4(point.x, point.y, point.z, 1)
    let centre = plane.center
    let distance = simd_length(SIMD2(local.x - centre.x, local.z - centre.z))
    return distance <= max(plane.planeExtent.width, plane.planeExtent.height) / 2 + planeReach
  }

  /// Mean squared Laplacian of the luma on a 40 by 30 grid of pixels: motion
  /// blur flattens edges and drops it. Compared only with the same session's
  /// recent frames. Same as Android's `SurfaceSample.lumaSharpness`.
  private static func sharpness(_ buffer: CVPixelBuffer) -> Double? {
    guard CVPixelBufferGetPlaneCount(buffer) > 0 else { return nil }
    CVPixelBufferLockBaseAddress(buffer, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddressOfPlane(buffer, 0) else { return nil }
    let width = CVPixelBufferGetWidthOfPlane(buffer, 0)
    let height = CVPixelBufferGetHeightOfPlane(buffer, 0)
    let rowBytes = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
    guard width >= 8, height >= 8 else { return nil }
    let bytes = base.assumingMemoryBound(to: UInt8.self)
    func at(_ x: Int, _ y: Int) -> Double { Double(bytes[y * rowBytes + x]) }
    let columns = 40
    let rows = 30
    var sum = 0.0
    for row in 0..<rows {
      let y = height / 10 + (row * (height * 8 / 10)) / rows
      for column in 0..<columns {
        let x = width / 10 + (column * (width * 8 / 10)) / columns
        let laplacian = 4 * at(x, y) - at(x - 1, y) - at(x + 1, y) - at(x, y - 1) - at(x, y + 1)
        sum += laplacian * laplacian
      }
    }
    return sum / Double(columns * rows)
  }

  // MARK: - Feature points (no LiDAR)

  private func accumulatePoints(_ frame: ARFrame) {
    guard let cloud = frame.rawFeaturePoints, case .normal = frame.camera.trackingState else { return }
    for (index, id) in cloud.identifiers.enumerated() {
      if pointCloud[id] == nil {
        if pointCloud.count >= maxPoints, !pointOrder.isEmpty {
          pointCloud.removeValue(forKey: pointOrder.removeFirst())
        }
        pointOrder.append(id)
      }
      pointCloud[id] = cloud.points[index]
    }
    let ordered = pointOrder.compactMap { pointCloud[$0] }
    let vertices = ordered.map { SCNVector3($0.x, $0.y, $0.z) }
    guard !vertices.isEmpty else { return }
    if !lite && !linksBusy && frame.timestamp - lastLinksAt > 0.6 {
      lastLinksAt = frame.timestamp
      linksBusy = true
      let newest = Array(ordered.suffix(maxLinkedPoints))
      // Joining thousands of points takes a few milliseconds: off the main thread.
      linkQueue.async { [weak self] in
        let links = SurfaceMesh.links(newest)
        let geometry = MeshStyle.lineGeometry(newest.map { SCNVector3($0.x, $0.y, $0.z) }, indices: links)
        DispatchQueue.main.async {
          guard let self else { return }
          self.linksBusy = false
          self.linkNode.geometry = geometry
        }
      }
    }
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

/// A ray in world space, direction of unit length.
struct Ray {
  let origin: SIMD3<Float>
  let direction: SIMD3<Float>
}

/// The camera as it was when a frame was captured: pose and intrinsics.
struct CaptureCamera {
  let transform: simd_float4x4
  let intrinsics: simd_float3x3
  let resolution: CGSize

  init(_ camera: ARCamera) {
    transform = camera.transform
    intrinsics = camera.intrinsics
    resolution = camera.imageResolution
  }

  /// The ray through a point of the sensor image, normalised 0 to 1 with y
  /// down. ARKit's camera looks down -Z with +Y up, in sensor orientation.
  func ray(throughNormalised point: CGPoint) -> Ray {
    let u = Float(point.x * resolution.width)
    let v = Float(point.y * resolution.height)
    let fx = intrinsics.columns.0.x
    let fy = intrinsics.columns.1.y
    let cx = intrinsics.columns.2.x
    let cy = intrinsics.columns.2.y
    let local = SIMD4<Float>((u - cx) / fx, -(v - cy) / fy, -1, 0)
    let world = transform * local
    let origin = SIMD3<Float>(transform.columns.3.x, transform.columns.3.y, transform.columns.3.z)
    return Ray(origin: origin, direction: simd_normalize(SIMD3<Float>(world.x, world.y, world.z)))
  }
}
