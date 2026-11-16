import { validate } from "@sajao/schemas/validate";
import {
  addNativeKeyframe,
  chosenKeyframeUris,
  localCapture,
  type NativeKeyframe,
  sensorDue,
} from "./native-capture";
import { buildPackage, startRecording } from "./recorder";

const pose = {
  position: { x_m: 0.1, y_m: 1.4, z_m: -0.2 },
  rotation: [0, 0, 0, 1] as [number, number, number, number],
};
const intrinsics = { fx: 1400, fy: 1400, cx: 960, cy: 720, width_px: 1920, height_px: 1440 };
const keyframe = (uri: string, yaw: number, sharpness: number): NativeKeyframe => ({
  uri,
  sharpness,
  yaw,
  pitch: 0,
  depth: true,
  pose,
  intrinsics,
});
const start = () => startRecording(1000, { tracking: "arkit", lidar: true, depth: false });

describe("native capture glue", () => {
  it("keeps a candidate the recorder wants and deletes the one it replaces", () => {
    let state = start();
    let step = addNativeKeyframe(state, keyframe("file:///a.jpg", 10, 100), 1100);
    expect(step.discard).toEqual([]);
    state = step.state;
    step = addNativeKeyframe(state, keyframe("file:///b.jpg", 12, 200), 1200);
    expect(step.discard).toEqual(["file:///a.jpg"]);
    expect(chosenKeyframeUris(step.state)).toEqual(["file:///b.jpg"]);
  });

  it("deletes a candidate the recorder rejects", () => {
    let state = addNativeKeyframe(start(), keyframe("file:///a.jpg", 10, 200), 1100).state;
    const step = addNativeKeyframe(state, keyframe("file:///b.jpg", 12, 150), 1200);
    expect(step.discard).toEqual(["file:///b.jpg"]);
    state = step.state;
    expect(chosenKeyframeUris(state)).toEqual(["file:///a.jpg"]);
  });

  it("orders keyframes by capture time, which gives the ids k1, k2 the depth file uses", () => {
    let state = start();
    state = addNativeKeyframe(state, keyframe("file:///late.jpg", 100, 120), 3000).state;
    state = addNativeKeyframe(state, keyframe("file:///early.jpg", 10, 120), 2000).state;
    expect(chosenKeyframeUris(state)).toEqual(["file:///early.jpg", "file:///late.jpg"]);
  });

  it("builds a package that validates against the Capture schema, with poses and depth", () => {
    let state = start();
    state = addNativeKeyframe(state, keyframe("file:///a.jpg", 10, 120), 1500).state;
    state = addNativeKeyframe(state, keyframe("file:///b.jpg", 100, 130), 2500).state;
    const local = localCapture("cap-1", state, {
      planes: "file:///planes.json",
      sceneMesh: "file:///mesh.ply",
      depth: "file:///depth.sjdepth",
    });
    expect(local.files.keyframes.map((k) => k.id)).toEqual(["k1", "k2"]);
    const pkg = buildPackage(local.state, {
      keyframes: { k1: "captures/cap-1/k1.jpg", k2: "captures/cap-1/k2.jpg" },
      sensorLog: "captures/cap-1/sensors.jsonl",
      planes: "captures/cap-1/planes.json",
      sceneMesh: "captures/cap-1/mesh.ply",
      depth: "captures/cap-1/depth.sjdepth",
    });
    expect(pkg.ar.depth).toBe(true);
    expect(pkg.keyframes[0]).toMatchObject({ id: "k1", captured_at_ms: 500, pose, intrinsics });
    const capture = JSON.parse(
      JSON.stringify({
        schema_version: "1.0",
        id: "00000000-0000-4000-8000-000000000001",
        user_id: "00000000-0000-4000-8000-000000000009",
        created_at: "2026-01-05T10:00:00Z",
        // Until the scan records video, the keyframes are the capture's photos.
        media: [
          {
            id: "00000000-0000-4000-8000-000000000003",
            kind: "photo",
            origin: "camera",
            storage_key: pkg.keyframes[0].image,
            width_px: 1920,
            height_px: 1440,
            has_ar_pose: true,
          },
        ],
        device: { platform: "ios", tier: "standard", has_ar: true },
        package: pkg,
      }),
    );
    const result = validate("Capture", capture);
    expect(result.ok ? [] : result.errors).toEqual([]);
  });

  it("marks depth absent when the phone wrote none", () => {
    const state = addNativeKeyframe(start(), keyframe("file:///a.jpg", 10, 120), 1500).state;
    const local = localCapture("cap-2", state, { planes: null, sceneMesh: null, depth: null });
    expect(local.state.ar.depth).toBe(false);
    expect(local.files.depth).toBeNull();
  });

  it("logs sensor readings at most five times a second", () => {
    expect(sensorDue(null, 0)).toBe(true);
    expect(sensorDue(0, 150)).toBe(false);
    expect(sensorDue(0, 200)).toBe(true);
  });
});
