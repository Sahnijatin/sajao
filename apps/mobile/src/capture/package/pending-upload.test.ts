import { addNativeKeyframe, localCapture } from "./native-capture";
import { buildPackage } from "./recorder";
import { clearPendingUpload, loadPendingUpload, savePendingUpload } from "./pending-upload";
import { startRecording } from "./recorder";

const saved = new Map<string, string>();
jest.mock("@react-native-async-storage/async-storage", () => ({
  __esModule: true,
  default: {
    getItem: async (key: string) =>
      (globalThis as { __saved?: Map<string, string> }).__saved?.get(key) ?? null,
    setItem: async (key: string, value: string) =>
      void (globalThis as { __saved?: Map<string, string> }).__saved?.set(key, value),
    removeItem: async (key: string) =>
      void (globalThis as { __saved?: Map<string, string> }).__saved?.delete(key),
  },
}));

const DEVICE = { platform: "ios", tier: "standard", has_ar: true } as const;
const POSE = {
  position: { x_m: 0.2, y_m: 1.4, z_m: -0.6 },
  rotation: [0, 0, 0, 1] as [number, number, number, number],
};
const INTRINSICS = { fx: 1400, fy: 1400, cx: 960, cy: 720, width_px: 1920, height_px: 1440 };

function scan(id: string) {
  let state = startRecording(0, { tracking: "arkit", lidar: false, depth: false });
  const frame = (uri: string, yaw: number) => ({
    uri,
    sharpness: 30,
    yaw,
    pitch: 0,
    depth: false,
    tracking: true,
    pose: POSE,
    intrinsics: INTRINSICS,
  });
  state = addNativeKeyframe(state, frame("file:///kf-1.jpg", 0), 100).state;
  state = addNativeKeyframe(state, frame("file:///kf-2.jpg", 90), 2000).state;
  return localCapture(id, state, { planes: "file:///planes.json", sceneMesh: null, depth: null });
}

describe("pending upload", () => {
  beforeEach(() => {
    saved.clear();
    (globalThis as { __saved?: Map<string, string> }).__saved = saved;
  });

  it("remembers the scan across an app restart", async () => {
    expect(await loadPendingUpload()).toBeNull();
    await savePendingUpload({ local: scan("scan-1"), device: DEVICE });
    const pending = await loadPendingUpload();
    expect(pending?.local.captureId).toBe("scan-1");
    expect(pending?.local.files.planes).toBe("file:///planes.json");
    expect(pending?.device).toEqual(DEVICE);
  });

  it("brings the keyframes and their poses back, so the resumed upload builds the same package", async () => {
    const before = scan("scan-1");
    await savePendingUpload({ local: before, device: DEVICE });
    const after = (await loadPendingUpload())?.local;
    if (!after) throw new Error("nothing was remembered");
    expect(after.state.keyframes.size).toBe(2);
    expect(after.files.keyframes.map((frame) => frame.uri)).toEqual([
      "file:///kf-1.jpg",
      "file:///kf-2.jpg",
    ]);
    const keys = { keyframes: { k1: "user/a.jpg", k2: "user/b.jpg" }, sensorLog: "user/s.jsonl" };
    expect(buildPackage(after.state, keys)).toEqual(buildPackage(before.state, keys));
    expect(buildPackage(after.state, keys).keyframes[0]?.pose).toEqual(POSE);
  });

  it("is forgotten once its upload is done, but never a newer scan", async () => {
    await savePendingUpload({ local: scan("scan-2"), device: DEVICE });
    await clearPendingUpload("scan-1");
    expect((await loadPendingUpload())?.local.captureId).toBe("scan-2");
    await clearPendingUpload("scan-2");
    expect(await loadPendingUpload()).toBeNull();
  });

  it("ignores a damaged record", async () => {
    saved.set("sajao.upload.pending", "{not json");
    expect(await loadPendingUpload()).toBeNull();
    saved.set("sajao.upload.pending", JSON.stringify({ local: {} }));
    expect(await loadPendingUpload()).toBeNull();
    // A record written before keyframes were stored as entries.
    const old = { local: { captureId: "x", files: {}, state: { keyframes: {} } }, device: DEVICE };
    saved.set("sajao.upload.pending", JSON.stringify(old));
    expect(await loadPendingUpload()).toBeNull();
  });
});
