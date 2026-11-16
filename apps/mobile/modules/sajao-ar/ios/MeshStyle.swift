import ARKit
import SceneKit
import UIKit

/// The look of the live scan, from the "Scan, mapping live" mockup: glowing
/// cyan edges, faces filled at 5 to 12 percent, bright vertex dots, a brief
/// brighten where the mesh just grew. Faces are tinted subtly by surface class.
enum MeshStyle {
  static let cyan = UIColor(red: 0.30, green: 0.90, blue: 1.0, alpha: 1)

  /// Fill tint per ARKit mesh class. Kept close to cyan so the room stays the hero.
  static func classTint(_ raw: UInt8) -> (UIColor, CGFloat) {
    let surface = ARMeshClassification(rawValue: Int(raw)) ?? ARMeshClassification.none
    switch surface {
    case .wall: return (UIColor(red: 0.35, green: 0.85, blue: 1.0, alpha: 1), 0.08)
    case .floor: return (UIColor(red: 0.30, green: 0.70, blue: 1.0, alpha: 1), 0.07)
    case .ceiling: return (UIColor(red: 0.55, green: 0.65, blue: 1.0, alpha: 1), 0.05)
    case .table: return (UIColor(red: 1.0, green: 0.78, blue: 0.40, alpha: 1), 0.12)
    case .seat: return (UIColor(red: 1.0, green: 0.55, blue: 0.75, alpha: 1), 0.12)
    case .window: return (UIColor(red: 0.65, green: 0.95, blue: 1.0, alpha: 1), 0.10)
    case .door: return (UIColor(red: 0.45, green: 1.0, blue: 0.70, alpha: 1), 0.10)
    default: return (cyan, 0.06)
    }
  }

  static func fillMaterial(_ color: UIColor, alpha: CGFloat) -> SCNMaterial {
    let material = SCNMaterial()
    material.lightingModel = .constant
    material.diffuse.contents = color.withAlphaComponent(alpha)
    material.isDoubleSided = true
    material.writesToDepthBuffer = false
    material.blendMode = .alpha
    return material
  }

  static func edgeMaterial() -> SCNMaterial {
    let material = SCNMaterial()
    material.lightingModel = .constant
    material.diffuse.contents = cyan.withAlphaComponent(0.85)
    material.emission.contents = cyan
    material.emission.intensity = 1
    material.isDoubleSided = true
    material.blendMode = .add
    material.writesToDepthBuffer = false
    return material
  }

  /// Grid lines on planes and links between tracked points: fainter than plane edges.
  static func linkMaterial() -> SCNMaterial {
    let material = edgeMaterial()
    material.diffuse.contents = cyan.withAlphaComponent(0.4)
    material.emission.intensity = 0.55
    return material
  }

  /// Line geometry joining `points` by index pairs.
  static func lineGeometry(_ points: [SCNVector3], indices: [UInt32]) -> SCNGeometry? {
    guard !points.isEmpty, !indices.isEmpty else { return nil }
    let geometry = SCNGeometry(
      sources: [SCNGeometrySource(vertices: points)],
      elements: [SCNGeometryElement(indices: indices, primitiveType: .line)])
    geometry.materials = [linkMaterial()]
    return geometry
  }

  /// A plane's interior grid, in the plane anchor's local space, so it reads as a mesh.
  static func planeGrid(_ plane: ARPlaneAnchor) -> SCNGeometry? {
    let outline = plane.geometry.boundaryVertices.map { SIMD2<Float>($0.x, $0.z) }
    let ends = SurfaceMesh.gridLines(outline)
    let points = ends.map { SCNVector3($0.x, 0, $0.y) }
    return lineGeometry(points, indices: Array(0..<UInt32(points.count)))
  }

  static func dotMaterial() -> SCNMaterial {
    let material = SCNMaterial()
    material.lightingModel = .constant
    material.diffuse.contents = UIColor.white
    material.emission.contents = cyan
    material.blendMode = .add
    material.writesToDepthBuffer = false
    return material
  }

  /// One node for a LiDAR mesh anchor: class-tinted faces, edges and dots,
  /// all sharing one copy of the vertices.
  static func meshNode(_ geometry: ARMeshGeometry, lite: Bool) -> SCNNode {
    let vertices = geometry.vertices
    var points: [SCNVector3] = []
    points.reserveCapacity(vertices.count)
    let vertexBase = vertices.buffer.contents().advanced(by: vertices.offset)
    for index in 0..<vertices.count {
      let p = vertexBase.advanced(by: index * vertices.stride).assumingMemoryBound(to: Float.self)
      points.append(SCNVector3(p[0], p[1], p[2]))
    }

    let faces = geometry.faces
    let faceBase = faces.buffer.contents()
    func index(_ face: Int, _ corner: Int) -> UInt32 {
      let offset = (face * faces.indexCountPerPrimitive + corner) * faces.bytesPerIndex
      if faces.bytesPerIndex == 2 {
        return UInt32(faceBase.advanced(by: offset).assumingMemoryBound(to: UInt16.self).pointee)
      }
      return faceBase.advanced(by: offset).assumingMemoryBound(to: UInt32.self).pointee
    }

    let classes = geometry.classification
    func classOf(_ face: Int) -> UInt8 {
      guard let classes else { return 0 }
      let base = classes.buffer.contents().advanced(by: classes.offset + face * classes.stride)
      return base.assumingMemoryBound(to: UInt8.self).pointee
    }

    var fillByClass: [UInt8: [UInt32]] = [:]
    var edges: [UInt32] = []
    edges.reserveCapacity(faces.count * 6)
    for face in 0..<faces.count {
      let a = index(face, 0)
      let b = index(face, 1)
      let c = index(face, 2)
      if !lite { fillByClass[classOf(face), default: []].append(contentsOf: [a, b, c]) }
      edges.append(contentsOf: [a, b, b, c, c, a])
    }

    var elements: [SCNGeometryElement] = []
    var materials: [SCNMaterial] = []
    for (rawClass, indices) in fillByClass {
      elements.append(SCNGeometryElement(indices: indices, primitiveType: .triangles))
      let (color, alpha) = classTint(rawClass)
      materials.append(fillMaterial(color, alpha: alpha))
    }
    elements.append(SCNGeometryElement(indices: edges, primitiveType: .line))
    materials.append(edgeMaterial())
    // Every third vertex as a bright dot: enough to read as mapped points.
    let dots = stride(from: 0, to: UInt32(points.count), by: lite ? 6 : 3).map { $0 }
    let dotElement = SCNGeometryElement(indices: dots, primitiveType: .point)
    dotElement.pointSize = 3
    dotElement.minimumPointScreenSpaceRadius = 1
    dotElement.maximumPointScreenSpaceRadius = 2.5
    elements.append(dotElement)
    materials.append(dotMaterial())

    let scnGeometry = SCNGeometry(sources: [SCNGeometrySource(vertices: points)], elements: elements)
    scnGeometry.materials = materials
    let node = SCNNode(geometry: scnGeometry)
    node.name = "sajao-surface"
    return node
  }

  /// Just-mapped areas glow brighter for a moment, then settle.
  static func brighten(_ node: SCNNode) {
    guard let edge = node.geometry?.materials.first(where: { $0.blendMode == .add && $0.emission.contents != nil }) else { return }
    edge.emission.intensity = 2.2
    let duration: TimeInterval = 0.8
    node.runAction(
      SCNAction.customAction(duration: duration) { _, elapsed in
        edge.emission.intensity = 2.2 - 1.2 * (elapsed / CGFloat(duration))
      })
  }

  // MARK: - Planes (phones without LiDAR)

  static func addPlaneNodes(to node: SCNNode, plane: ARPlaneAnchor, device: MTLDevice, lite: Bool) {
    guard let fill = ARSCNPlaneGeometry(device: device), let lines = ARSCNPlaneGeometry(device: device) else { return }
    fill.update(from: plane.geometry)
    lines.update(from: plane.geometry)
    let tint: UIColor = plane.alignment == .vertical ? cyan : UIColor(red: 0.30, green: 0.70, blue: 1.0, alpha: 1)
    fill.materials = [fillMaterial(tint, alpha: lite ? 0.05 : 0.09)]
    let edge = edgeMaterial()
    edge.fillMode = .lines
    lines.materials = [edge]
    let fillNode = SCNNode(geometry: fill)
    fillNode.name = "sajao-surface"
    let lineNode = SCNNode(geometry: lines)
    lineNode.name = "sajao-plane-lines"
    let gridNode = SCNNode(geometry: planeGrid(plane))
    gridNode.name = "sajao-plane-grid"
    node.addChildNode(fillNode)
    node.addChildNode(lineNode)
    node.addChildNode(gridNode)
  }

  static func updatePlaneNodes(_ node: SCNNode, plane: ARPlaneAnchor) {
    for child in node.childNodes {
      if child.name == "sajao-plane-grid" {
        child.geometry = planeGrid(plane)
      } else {
        (child.geometry as? ARSCNPlaneGeometry)?.update(from: plane.geometry)
      }
    }
  }
}
