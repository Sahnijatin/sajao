import { validate } from "@sajao/schemas/validate";
import {
  cellOf,
  chosenKeyframes,
  type KeyframeCandidate,
  MAX_KEYFRAMES,
  NO_KEYFRAMES,
  offerKeyframe,
  replacedBy,
} from "./keyframes";
import {
  buildPackage,
  filesToUpload,
  record,
  type RecordedKeyframe,
  startRecording,
} from "./recorder";
import { uploadCapturePackage, type PackageUploadDeps } from "./upload-package";

const frame = (
  uri: string,
  atMs: number,
  sharpness: number,
  yaw: number | null,
  pitch: number | null = 0,
): KeyframeCandidate => ({
  uri,
  atMs,
  sharpness,
  yaw,
  pitch,
});

describe("keyframe selection", () => {
  it("keeps the sharpest frame per direction and skips blur", () => {
    let set = offerKeyframe(NO_KEYFRAMES, frame("a", 0, 200, 10));
    set = offerKeyframe(set, frame("b", 100, 205, 12)); // not clearly sharper
    set = offerKeyframe(set, frame("c", 200, 300, 14)); // clearly sharper: replaces a
    set = offerKeyframe(set, frame("d", 300, 20, 100)); // blurred
    set = offerKeyframe(set, frame("e", 400, 150, 100)); // new direction
    expect(chosenKeyframes(set).map((k) => k.uri)).toEqual(["c", "e"]);
  });

  it("groups by direction with a pose and by time without one", () => {
    expect(cellOf(frame("a", 0, 100, 359))).toBe(cellOf(frame("b", 0, 100, -1)));
    expect(cellOf(frame("a", 0, 100, 0, -40))).not.toBe(cellOf(frame("a", 0, 100, 0, 40)));
    expect(cellOf(frame("a", 100, 100, null, null))).toBe("t0");
    expect(cellOf(frame("a", 1600, 100, null, null))).toBe("t1");
  });

  it("caps the set and reports frames whose files can be deleted", () => {
    let set = NO_KEYFRAMES;
    for (let i = 0; i < MAX_KEYFRAMES + 30; i += 1)
      set = offerKeyframe(set, frame(`f${i}`, i * 2000, 100, null, null));
    expect(set.size).toBe(MAX_KEYFRAMES);
    const before = offerKeyframe(NO_KEYFRAMES, frame("old", 0, 100, 0));
    const after = offerKeyframe(before, frame("new", 10, 500, 0));
    expect(replacedBy(before, after)).toEqual(["old"]);
  });
});

const pose = {
  position: { x_m: 0, y_m: 1.4, z_m: 0 },
  rotation: [0, 0, 0, 1] as [number, number, number, number],
};
const intrinsics = { fx: 1450, fy: 1450, cx: 960, cy: 720, width_px: 1920, height_px: 1440 };
const keyframe = (uri: string, atMs: number, yaw: number, withPose = true): RecordedKeyframe => ({
  ...frame(uri, atMs, 300, yaw),
  pose: withPose ? pose : null,
  intrinsics: withPose ? intrinsics : null,
});

function recorded(withAr = true) {
  let state = startRecording(1000, {
    tracking: withAr ? "arkit" : "none",
    lidar: false,
    depth: false,
  });
  state = record(state, { type: "keyframe", frame: keyframe("file://k-a.jpg", 1500, 0, withAr) });
  state = record(state, { type: "keyframe", frame: keyframe("file://k-b.jpg", 3000, 90, withAr) });
  state = record(state, {
    type: "detections",
    atMs: 2000,
    detections: [
      { detectorClass: "refrigerator", score: 0.8, world: { x: 1, y: 0.9, z: -2 } },
      { detectorClass: "chair", score: 0.6, world: null },
    ],
  });
  state = record(state, { type: "sensor", atMs: 1100, reading: { yaw: 3, brightness: 120 } });
  return state;
}

function fakeDeps(fail: Set<string> = new Set()) {
  const done = new Map<string, string>();
  const uploads: string[] = [];
  const deps: PackageUploadDeps = {
    uploadFile: async ({ localId }) => {
      if (fail.has(localId)) throw new Error("connection lost");
      uploads.push(localId);
      return { key: `captures/${localId}` };
    },
    writeText: async (name) => `file://${name}`,
    done: {
      get: async (id) => done.get(id) ?? null,
      set: async (id, key) => {
        done.set(id, key);
      },
    },
  };
  return { deps, uploads, done };
}

describe("capture package", () => {
  it("records keyframes with poses, detections and a sensor log, timed from the start", () => {
    const state = recorded();
    expect(state.detections).toEqual([
      {
        detector_class: "refrigerator",
        score: 0.8,
        at_ms: 1000,
        world: { x_m: 1, y_m: 0.9, z_m: -2 },
      },
      { detector_class: "chair", score: 0.6, at_ms: 1000 },
    ]);
    expect(JSON.parse(state.sensorLog[0] ?? "{}")).toEqual({ t: 100, yaw: 3, brightness: 120 });
  });

  it("uploads every file, builds a package that validates, and sends the video last", async () => {
    const state = recorded();
    const files = filesToUpload(state, {
      video: "file://scan.mp4",
      planes: "file://planes.json",
      sceneMesh: null,
      depth: null,
    });
    const { deps, uploads } = fakeDeps();
    const pkg = await uploadCapturePackage("cap-1", state, files, deps);
    expect(uploads[0]).toBe("cap-1/sensor_log");
    expect(uploads.at(-1)).toBe("cap-1/video");
    expect(pkg.keyframes.map((k) => [k.id, k.captured_at_ms, Boolean(k.pose)])).toEqual([
      ["k1", 500, true],
      ["k2", 2000, true],
    ]);
    const capture = JSON.parse(
      JSON.stringify({
        schema_version: "1.0",
        id: "00000000-0000-4000-8000-000000000001",
        user_id: "00000000-0000-4000-8000-000000000009",
        created_at: "2026-01-05T10:00:00Z",
        media: [
          {
            id: "00000000-0000-4000-8000-000000000003",
            kind: "video",
            origin: "camera",
            storage_key: pkg.video,
            width_px: 1920,
            height_px: 1440,
            duration_s: 40,
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

  it("works without AR: keyframes and video, no poses", async () => {
    const state = recorded(false);
    const { deps } = fakeDeps();
    const pkg = await uploadCapturePackage(
      "cap-2",
      state,
      filesToUpload(state, { video: "file://v.mp4", planes: null, sceneMesh: null, depth: null }),
      deps,
    );
    expect(pkg.ar.tracking).toBe("none");
    expect(pkg.keyframes.every((k) => k.pose === undefined)).toBe(true);
  });

  it("resumes after a failure without uploading anything twice", async () => {
    const state = recorded();
    const files = filesToUpload(state, {
      video: "file://scan.mp4",
      planes: null,
      sceneMesh: null,
      depth: null,
    });
    const first = fakeDeps(new Set(["cap-3/video"]));
    await expect(uploadCapturePackage("cap-3", state, files, first.deps)).rejects.toThrow(
      "connection lost",
    );
    expect(first.uploads).toEqual(["cap-3/sensor_log", "cap-3/keyframe-k1", "cap-3/keyframe-k2"]);

    // Same store, connection back: only the video goes up, and the package is the same as a clean run.
    const retry = {
      ...first.deps,
      uploadFile: async (file: { localId: string }) => {
        first.uploads.push(file.localId);
        return { key: `captures/${file.localId}` };
      },
    };
    const pkg = await uploadCapturePackage("cap-3", state, files, retry);
    expect(first.uploads.slice(3)).toEqual(["cap-3/video"]);
    const clean = await uploadCapturePackage("cap-3", state, files, fakeDeps().deps);
    expect(pkg).toEqual(clean);
  });

  it("refuses to build a package with a keyframe that was not uploaded", () => {
    expect(() => buildPackage(recorded(), { keyframes: { k1: "a" }, sensorLog: "s" })).toThrow(
      "k2",
    );
  });
});
