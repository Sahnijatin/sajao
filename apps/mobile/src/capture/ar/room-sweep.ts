// A simulated scan of a rectangular room, for calibrating coverage: the
// phone stands in the room and sweeps, casting the same 4 by 3 grid of rays
// as the native view every 250 ms. Test support only.
import type { SurfaceHit } from "./surface-coverage";

export interface Room {
  /** Half widths: walls at x = +-halfX and z = +-halfZ; floor at y = 0. */
  halfX: number;
  halfZ: number;
}

/** The grid's angles from the view centre, degrees: the sensor's long side is upright on the phone. */
const UP_DOWN = [-19, -6, 6, 19];
const SIDEWAYS = [-12, 0, 12];

/** Where the grid of rays from a camera at (x, height, z) facing yaw and pitch lands. */
export function gridHits(
  room: Room,
  camera: { x: number; z: number; height: number },
  yawDegrees: number,
  pitchDegrees: number,
): SurfaceHit[] {
  const hits: SurfaceHit[] = [];
  for (const up of UP_DOWN) {
    for (const side of SIDEWAYS) {
      // App yaw: 0 looks down -z, positive turns left (towards -x).
      const yaw = ((yawDegrees + side) * Math.PI) / 180;
      const pitch = ((pitchDegrees + up) * Math.PI) / 180;
      const d = {
        x: -Math.sin(yaw) * Math.cos(pitch),
        y: Math.sin(pitch),
        z: -Math.cos(yaw) * Math.cos(pitch),
      };
      const candidates: { t: number; hit: SurfaceHit }[] = [];
      const at = (t: number) => ({
        x: camera.x + d.x * t,
        y: camera.height + d.y * t,
        z: camera.z + d.z * t,
      });
      if (d.y < 0) {
        const t = -camera.height / d.y;
        candidates.push({ t, hit: { kind: "floor", normalYaw: 0, offset: 0, ...at(t) } });
      }
      // Each wall faces into the room; normal yaw is atan2(nx, nz).
      const walls = [
        { axis: "z", value: -room.halfZ, normalYaw: 0, normal: { x: 0, z: 1 } },
        { axis: "z", value: room.halfZ, normalYaw: 180, normal: { x: 0, z: -1 } },
        { axis: "x", value: -room.halfX, normalYaw: 90, normal: { x: 1, z: 0 } },
        { axis: "x", value: room.halfX, normalYaw: -90, normal: { x: -1, z: 0 } },
      ] as const;
      for (const wall of walls) {
        const along = wall.axis === "x" ? d.x : d.z;
        const from = wall.axis === "x" ? camera.x : camera.z;
        if (Math.abs(along) < 1e-6) continue;
        const t = (wall.value - from) / along;
        if (t <= 0) continue;
        const p = at(t);
        const offset = wall.normal.x * p.x + wall.normal.z * p.z;
        candidates.push({
          t,
          hit: { kind: "wall", normalYaw: wall.normalYaw, offset, ...p },
        });
      }
      const nearest = candidates.sort((a, b) => a.t - b.t)[0];
      if (nearest && nearest.hit.y <= 2.8) hits.push(nearest.hit);
    }
  }
  return hits;
}
