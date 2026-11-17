import ARKit
import CoreImage
import Foundation
import ImageIO
import QuartzCore

/// Decides which frames are worth saving as keyframe candidates: the same
/// direction cells as the app's `keyframes.ts`, and only a frame clearly
/// sharper than the best saved for its cell. Same as `KeyframeGate` in
/// `CaptureFormats.kt`, which is unit tested.
struct KeyframeGate {
  static let yawCellDegrees = 30.0
  static let replaceMargin = 1.1
  private var best: [String: Double] = [:]

  static func cellOf(yaw: Double, pitch: Double) -> String {
    let turned = (yaw.truncatingRemainder(dividingBy: 360) + 360).truncatingRemainder(dividingBy: 360)
    let sector = Int(turned / yawCellDegrees)
    let band = [-20.0, 20.0].filter { pitch > $0 }.count
    return "d\(sector)-\(band)"
  }

  /// Without a pose, one cell per this many milliseconds, as keyframes.ts.
  static let timeCellMs = 1500.0

  /// By direction when tracking gives a pose, by time otherwise: frames are kept whatever tracking says.
  static func cellFor(yaw: Double?, pitch: Double?, elapsedMs: Double, x: Float? = nil, z: Float? = nil) -> String {
    guard let yaw, let pitch else { return "t\(Int(elapsedMs / timeCellMs))" }
    guard let x, let z else { return cellOf(yaw: yaw, pitch: pitch) }
    return "\(placeOf(x: x, z: z))-\(cellOf(yaw: yaw, pitch: pitch))"
  }

  /// Side of a square of floor that counts as one place to stand, as `PLACE_CELL_M` in keyframes.ts.
  static let placeCellM: Float = 0.5

  /// "p<column>_<row>": where the camera stood. A keyframe is a new viewpoint
  /// when it is taken from a new place or looks a new way, so walking the
  /// room keeps adding keyframes that turning on one spot cannot.
  static func placeOf(x: Float, z: Float) -> String {
    "p\(Int((x / placeCellM).rounded(.down)))_\(Int((z / placeCellM).rounded(.down)))"
  }

  func shouldSave(cell: String, sharpness: Double) -> Bool {
    guard sharpness > 0 else { return false }
    guard let current = best[cell] else { return true }
    return sharpness >= current * Self.replaceMargin
  }

  mutating func saved(cell: String, sharpness: Double) {
    best[cell] = sharpness
  }
}

/// One depth image aligned to a keyframe: millimetres (0 = no reading) and confidence 0 to 255.
struct DepthEntry {
  let id: String
  let width: Int
  let height: Int
  let millimetres: [UInt16]
  let confidence: [UInt8]
}

/// The capture package's depth file, format SJDEPTH1 (docs/06). Same layout
/// as `DepthContainer` in `CaptureFormats.kt`, read by the twin worker's
/// `capture_depth.py`.
enum DepthContainer {
  static func data(_ entries: [DepthEntry]) -> Data {
    var out = Data("SJDEPTH1".utf8)
    func le<T: FixedWidthInteger>(_ value: T) {
      withUnsafeBytes(of: value.littleEndian) { out.append(contentsOf: $0) }
    }
    le(UInt32(entries.count))
    for entry in entries {
      let id = Data(entry.id.utf8)
      le(UInt16(id.count))
      out.append(id)
      le(UInt32(entry.width))
      le(UInt32(entry.height))
      for value in entry.millimetres { le(value) }
      out.append(contentsOf: entry.confidence)
    }
    return out
  }
}

/// Records the capture package's native files during an AR scan: full
/// resolution keyframe candidates (JPEG, sensor orientation) with the camera
/// pose and intrinsics, LiDAR depth per keyframe, and at the end the planes
/// and the LiDAR scene mesh. The app's recorder decides which candidates are
/// kept; files it drops are deleted on its say.
///
/// Poses are ARKit camera transforms in the AR world frame (metres, gravity
/// aligned, y up): +X right, +Y up, -Z forward relative to the stored
/// image. Nothing here sets a dimension; the twin measures on the server.
final class CaptureRecorder {
  /// Up to 200 keyframes are uploaded: at 0.8 a full-resolution frame is about
  /// half the size it was at 0.92, with no visible loss for the server.
  static let jpegQuality = 0.8

  private let dir: URL
  private let emit: ([String: Any]) -> Void
  private var gate = KeyframeGate()
  private let writer = DispatchQueue(label: "app.sajao.ar.capture", qos: .utility)
  private let context = CIContext(options: [.cacheIntermediates: false])
  /// Read and written on the main thread.
  private var busy = false
  private var count = 0
  private let startedAt = CACurrentMediaTime()

  static func folder(_ captureId: String) -> URL {
    FileManager.default.temporaryDirectory.appendingPathComponent("sajao-capture/\(captureId)", isDirectory: true)
  }

  init(dir: URL, emit: @escaping ([String: Any]) -> Void) {
    self.dir = dir
    self.emit = emit
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
  }

  /// Offer an AR frame. Saves it as a keyframe candidate when it is clearly
  /// the sharpest yet for its direction. Main thread; encoding runs on a
  /// background queue.
  func offer(_ frame: ARFrame, sharpness: Double, yaw: Double?, pitch: Double?) {
    // Kept whatever tracking says: without a pose, by time; the server
    // solves those poses from the video.
    let tracking: Bool = {
      if case .normal = frame.camera.trackingState { return true }
      return false
    }()
    let place = frame.camera.transform.columns.3
    let cell = KeyframeGate.cellFor(
      yaw: tracking ? yaw : nil, pitch: tracking ? pitch : nil,
      elapsedMs: (CACurrentMediaTime() - startedAt) * 1000,
      x: tracking ? place.x : nil, z: tracking ? place.z : nil)
    guard !busy, gate.shouldSave(cell: cell, sharpness: sharpness) else { return }
    busy = true
    count += 1
    let name = String(format: "kf-%04d", count)
    let camera = frame.camera
    let transform = camera.transform
    let intrinsics = camera.intrinsics
    let resolution = camera.imageResolution
    let depth = Self.depthCopy(frame.sceneDepth)
    let image = CIImage(cvPixelBuffer: frame.capturedImage)
    let dir = self.dir
    writer.async { [weak self] in
      guard let self else { return }
      let jpeg = dir.appendingPathComponent("\(name).jpg")
      var ok = false
      if let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
        let data = self.context.jpegRepresentation(
          of: image, colorSpace: colorSpace,
          options: [CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String): Self.jpegQuality])
      {
        ok = (try? data.write(to: jpeg, options: .atomic)) != nil
      }
      if ok, let depth {
        try? Self.rawDepthData(depth).write(to: dir.appendingPathComponent("\(name).depth"), options: .atomic)
      }
      DispatchQueue.main.async {
        self.busy = false
        guard ok else { return }
        self.gate.saved(cell: cell, sharpness: sharpness)
        let q = simd_quatf(transform)
        let t = transform.columns.3
        var payload: [String: Any] = [
          "uri": jpeg.absoluteString,
          "sharpness": sharpness,
          "depth": depth != nil,
          "tracking": tracking,
          "intrinsics": [
            "fx": Double(intrinsics.columns.0.x),
            "fy": Double(intrinsics.columns.1.y),
            "cx": Double(intrinsics.columns.2.x),
            "cy": Double(intrinsics.columns.2.y),
            "width_px": Int(resolution.width),
            "height_px": Int(resolution.height),
          ]
        ]
        if tracking, let yaw, let pitch {
          payload["yaw"] = yaw
          payload["pitch"] = pitch
          payload["pose"] = [
            "position": ["x_m": Double(t.x), "y_m": Double(t.y), "z_m": Double(t.z)],
            "rotation": [Double(q.imag.x), Double(q.imag.y), Double(q.imag.z), Double(q.real)],
          ]
        }
        self.emit(payload)
      }
    }
  }

  /// Delete candidates the app's recorder dropped.
  func discard(_ uris: [String]) {
    let dir = self.dir
    writer.async {
      for uri in uris {
        guard let url = URL(string: uri), url.deletingLastPathComponent().standardizedFileURL == dir.standardizedFileURL else {
          continue
        }
        try? FileManager.default.removeItem(at: url)
        try? FileManager.default.removeItem(at: url.deletingPathExtension().appendingPathExtension("depth"))
      }
    }
  }

  /// End of the scan: write the planes, the LiDAR scene mesh and the depth
  /// file for the chosen keyframes (ids k1, k2, ... in the given order),
  /// delete every other candidate, and return the files' uris. Runs after
  /// any keyframe still being written.
  func finish(
    planes: [ARPlaneAnchor], meshes: [ARMeshAnchor], chosen: [String],
    completion: @escaping ([String: Any?]) -> Void
  ) {
    let dir = self.dir
    writer.async {
      var result: [String: Any?] = ["planes": nil, "sceneMesh": nil, "depth": nil]
      let planesURL = dir.appendingPathComponent("planes.json")
      if let data = try? JSONSerialization.data(withJSONObject: ["format": "sajao-planes-1", "planes": planes.map(Self.planeJSON)]),
        (try? data.write(to: planesURL, options: .atomic)) != nil
      {
        result["planes"] = planesURL.absoluteString
      }
      if !meshes.isEmpty {
        let meshURL = dir.appendingPathComponent("scene-mesh.ply")
        if (try? Self.ply(meshes).write(to: meshURL, options: .atomic)) != nil {
          result["sceneMesh"] = meshURL.absoluteString
        }
      }
      let chosenURLs = chosen.compactMap { URL(string: $0) }
      var entries: [DepthEntry] = []
      for (index, url) in chosenURLs.enumerated() {
        let raw = url.deletingPathExtension().appendingPathExtension("depth")
        if let data = try? Data(contentsOf: raw), let entry = Self.readRawDepth(data, id: "k\(index + 1)") {
          entries.append(entry)
        }
      }
      if !entries.isEmpty {
        let depthURL = dir.appendingPathComponent("depth.sjdepth")
        if (try? DepthContainer.data(entries).write(to: depthURL, options: .atomic)) != nil {
          result["depth"] = depthURL.absoluteString
        }
      }
      let keep = Set(chosenURLs.map(\.lastPathComponent))
      let files = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? []
      for file in files where file.lastPathComponent.hasPrefix("kf-") {
        let isKeptImage = keep.contains(file.lastPathComponent)
        if !isKeptImage { try? FileManager.default.removeItem(at: file) }
      }
      DispatchQueue.main.async { completion(result) }
    }
  }

  // MARK: - Formats

  private struct RawDepth {
    let width: Int
    let height: Int
    let millimetres: [UInt16]
    let confidence: [UInt8]
  }

  /// LiDAR scene depth in metres to millimetres, confidence 0, 1, 2 to 0, 127, 255.
  private static func depthCopy(_ depth: ARDepthData?) -> RawDepth? {
    guard let depth else { return nil }
    let map = depth.depthMap
    CVPixelBufferLockBaseAddress(map, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(map, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddress(map) else { return nil }
    let width = CVPixelBufferGetWidth(map)
    let height = CVPixelBufferGetHeight(map)
    let rowBytes = CVPixelBufferGetBytesPerRow(map)
    var millimetres = [UInt16](repeating: 0, count: width * height)
    for y in 0..<height {
      let row = base.advanced(by: y * rowBytes).assumingMemoryBound(to: Float32.self)
      for x in 0..<width {
        let metres = row[x]
        millimetres[y * width + x] = metres.isFinite && metres > 0 ? UInt16(min(65535, metres * 1000)) : 0
      }
    }
    var confidence = [UInt8](repeating: 255, count: width * height)
    if let map = depth.confidenceMap {
      CVPixelBufferLockBaseAddress(map, .readOnly)
      defer { CVPixelBufferUnlockBaseAddress(map, .readOnly) }
      if let base = CVPixelBufferGetBaseAddress(map), CVPixelBufferGetWidth(map) == width,
        CVPixelBufferGetHeight(map) == height
      {
        let rowBytes = CVPixelBufferGetBytesPerRow(map)
        // ARKit confidence is 0 (low), 1 (medium), 2 (high).
        let levels: [UInt8] = [0, 127, 255]
        for y in 0..<height {
          let row = base.advanced(by: y * rowBytes).assumingMemoryBound(to: UInt8.self)
          for x in 0..<width { confidence[y * width + x] = levels[min(2, Int(row[x]))] }
        }
      }
    }
    return RawDepth(width: width, height: height, millimetres: millimetres, confidence: confidence)
  }

  private static func rawDepthData(_ depth: RawDepth) -> Data {
    DepthContainer.data([
      DepthEntry(id: "", width: depth.width, height: depth.height, millimetres: depth.millimetres, confidence: depth.confidence)
    ])
  }

  private static func readRawDepth(_ data: Data, id: String) -> DepthEntry? {
    // A one-entry SJDEPTH1 file with an empty id: magic 8, count 4, id length 2, size 8.
    let header = 8 + 4 + 2 + 8
    guard data.count >= header else { return nil }
    func u32(_ offset: Int) -> Int {
      Int(data.subdata(in: offset..<offset + 4).withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) }.littleEndian)
    }
    let width = u32(14)
    let height = u32(18)
    let pixels = width * height
    guard data.count == header + pixels * 3 else { return nil }
    let millimetres: [UInt16] = data.subdata(in: header..<header + pixels * 2).withUnsafeBytes { raw in
      (0..<pixels).map { raw.loadUnaligned(fromByteOffset: $0 * 2, as: UInt16.self).littleEndian }
    }
    let confidence = [UInt8](data.subdata(in: header + pixels * 2..<data.count))
    return DepthEntry(id: id, width: width, height: height, millimetres: millimetres, confidence: confidence)
  }

  private static func planeJSON(_ plane: ARPlaneAnchor) -> [String: Any] {
    let m = plane.transform
    let columns = [m.columns.0, m.columns.1, m.columns.2, m.columns.3]
    let classification: String
    switch plane.classification {
    case .wall: classification = "wall"
    case .floor: classification = "floor"
    case .ceiling: classification = "ceiling"
    case .table: classification = "table"
    case .seat: classification = "seat"
    case .door: classification = "door"
    case .window: classification = "window"
    default: classification = "none"
    }
    return [
      "id": plane.identifier.uuidString,
      "type": plane.alignment == .vertical ? "vertical" : "horizontal_up",
      "classification": classification,
      // Column-major, as ARCore's toMatrix.
      "transform": columns.flatMap { [Double($0.x), Double($0.y), Double($0.z), Double($0.w)] },
      "extent": [Double(plane.planeExtent.width), Double(plane.planeExtent.height)],
      "polygon_xz": plane.geometry.boundaryVertices.flatMap { [Double($0.x), Double($0.z)] },
    ]
  }

  /// The LiDAR scene mesh as binary PLY in the AR world frame, metres, with
  /// ARKit's surface class per face (0 none, 1 wall, 2 floor, 3 ceiling,
  /// 4 table, 5 seat, 6 window, 7 door).
  private static func ply(_ meshes: [ARMeshAnchor]) -> Data {
    var vertices: [SIMD3<Float>] = []
    var faces: [(UInt32, UInt32, UInt32, UInt8)] = []
    for anchor in meshes {
      let geometry = anchor.geometry
      let base = UInt32(vertices.count)
      let source = geometry.vertices
      let pointer = source.buffer.contents().advanced(by: source.offset)
      for i in 0..<source.count {
        let p = pointer.advanced(by: i * source.stride).assumingMemoryBound(to: Float.self)
        let world = anchor.transform * SIMD4<Float>(p[0], p[1], p[2], 1)
        vertices.append(SIMD3(world.x, world.y, world.z))
      }
      let faceBuffer = geometry.faces
      let facePointer = faceBuffer.buffer.contents()
      func index(_ face: Int, _ corner: Int) -> UInt32 {
        let offset = (face * faceBuffer.indexCountPerPrimitive + corner) * faceBuffer.bytesPerIndex
        if faceBuffer.bytesPerIndex == 2 {
          return UInt32(facePointer.advanced(by: offset).assumingMemoryBound(to: UInt16.self).pointee)
        }
        return facePointer.advanced(by: offset).assumingMemoryBound(to: UInt32.self).pointee
      }
      let classes = geometry.classification
      for face in 0..<faceBuffer.count {
        var surface: UInt8 = 0
        if let classes {
          surface = classes.buffer.contents().advanced(by: classes.offset + face * classes.stride)
            .assumingMemoryBound(to: UInt8.self).pointee
        }
        faces.append((base + index(face, 0), base + index(face, 1), base + index(face, 2), surface))
      }
    }
    var out = Data(
      """
      ply
      format binary_little_endian 1.0
      comment sajao-scene-mesh-1: AR world frame, metres, y up
      element vertex \(vertices.count)
      property float x
      property float y
      property float z
      element face \(faces.count)
      property list uchar uint vertex_indices
      property uchar classification
      end_header

      """.utf8)
    func le<T: FixedWidthInteger>(_ value: T) {
      withUnsafeBytes(of: value.littleEndian) { out.append(contentsOf: $0) }
    }
    for v in vertices {
      le(v.x.bitPattern)
      le(v.y.bitPattern)
      le(v.z.bitPattern)
    }
    for (a, b, c, surface) in faces {
      out.append(3)
      le(a)
      le(b)
      le(c)
      out.append(surface)
    }
    return out
  }
}
