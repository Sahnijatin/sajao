import Foundation
import simd

/// The live surface effect on phones without LiDAR, built from what ARKit
/// tracks: planes drawn as a grid mesh, and tracked feature points joined to
/// their nearest neighbours so non-flat things (a sofa, a table edge) read as
/// a wire mesh. Same as `SurfaceMesh.kt` on Android, which is unit tested.
/// Drawing only: nothing here sets a dimension.
enum SurfaceMesh {
  /// Grid spacing on planes, in metres.
  static let gridMetres: Float = 0.3
  /// Points closer than this are joined, in metres.
  static let linkMetres: Float = 0.22
  /// Each point joins at most this many nearest neighbours.
  static let linksPerPoint = 3

  /// Grid lines inside a convex plane polygon in the plane's local x and z:
  /// lines of constant x and of constant z every `spacing`, clipped to the
  /// polygon. Returns segment end points, two per line.
  static func gridLines(_ polygon: [SIMD2<Float>], spacing: Float = gridMetres) -> [SIMD2<Float>] {
    guard polygon.count >= 3 else { return [] }
    let xs = polygon.map(\.x)
    let zs = polygon.map(\.y)
    guard let minX = xs.min(), let maxX = xs.max(), let minZ = zs.min(), let maxZ = zs.max() else { return [] }
    var out: [SIMD2<Float>] = []
    for axis in 0...1 {
      let lo = axis == 0 ? minX : minZ
      let hi = axis == 0 ? maxX : maxZ
      var step = Int(floor(lo / spacing)) + 1
      while Float(step) * spacing < hi {
        let value = Float(step) * spacing
        if let (from, to) = clip(polygon, axis: axis, value: value) {
          if axis == 0 {
            out.append(SIMD2(value, from))
            out.append(SIMD2(value, to))
          } else {
            out.append(SIMD2(from, value))
            out.append(SIMD2(to, value))
          }
        }
        step += 1
      }
    }
    return out
  }

  /// Where the line with coordinate `axis` fixed at `value` crosses a convex
  /// polygon: the range of the other coordinate.
  private static func clip(_ polygon: [SIMD2<Float>], axis: Int, value: Float) -> (Float, Float)? {
    var lo = Float.greatestFiniteMagnitude
    var hi = -Float.greatestFiniteMagnitude
    for i in 0..<polygon.count {
      let p = polygon[i]
      let q = polygon[(i + 1) % polygon.count]
      let a = p[axis]
      let b = q[axis]
      if a == b || value < min(a, b) || value > max(a, b) { continue }
      let t = (value - a) / (b - a)
      let other = p[1 - axis] + t * (q[1 - axis] - p[1 - axis])
      lo = min(lo, other)
      hi = max(hi, other)
    }
    return hi > lo ? (lo, hi) : nil
  }

  /// Joins each point to its nearest neighbours within `link` metres, at most
  /// `perPoint` each, using cells `link` wide so thousands of points stay
  /// fast. Returns index pairs, each edge once.
  static func links(_ points: [SIMD3<Float>], link: Float = linkMetres, perPoint: Int = linksPerPoint) -> [UInt32] {
    func cell(_ p: SIMD3<Float>) -> SIMD3<Int32> {
      SIMD3(Int32(floor(p.x / link)), Int32(floor(p.y / link)), Int32(floor(p.z / link)))
    }
    var cells: [SIMD3<Int32>: [Int]] = [:]
    for (i, p) in points.enumerated() { cells[cell(p), default: []].append(i) }
    var seen = Set<UInt64>()
    var out: [UInt32] = []
    let limit = link * link
    var near: [(Float, Int)] = []
    for (i, p) in points.enumerated() {
      near.removeAll(keepingCapacity: true)
      let c = cell(p)
      for dx in -1...1 {
        for dy in -1...1 {
          for dz in -1...1 {
            guard let bucket = cells[c &+ SIMD3(Int32(dx), Int32(dy), Int32(dz))] else { continue }
            for j in bucket where j != i {
              let d = simd_distance_squared(p, points[j])
              if d <= limit { near.append((d, j)) }
            }
          }
        }
      }
      near.sort { $0.0 < $1.0 }
      for (_, j) in near.prefix(perPoint) {
        let a = min(i, j)
        let b = max(i, j)
        if seen.insert(UInt64(a) << 32 | UInt64(b)).inserted {
          out.append(UInt32(a))
          out.append(UInt32(b))
        }
      }
    }
    return out
  }
}
