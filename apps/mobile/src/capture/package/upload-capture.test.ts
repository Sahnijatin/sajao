import { addNativeKeyframe, localCapture } from "./native-capture";
import { startRecording } from "./recorder";
import {
  type CaptureUploadDeps,
  registerBody,
  uploadAndRegister,
  uploadSpec,
  uuidV4,
} from "./upload-capture";

const CAPTURE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const DEVICE = { platform: "android", tier: "low", has_ar: true } as const;

function scan() {
  let state = startRecording(0, { tracking: "arcore", lidar: false, depth: false });
  const frame = (uri: string, yaw: number, posed: boolean) => ({
    uri,
    sharpness: 30,
    yaw,
    pitch: 0,
    depth: false,
    tracking: posed,
    ...(posed
      ? {
          pose: {
            position: { x_m: 0, y_m: 1.4, z_m: 0 },
            rotation: [0, 0, 0, 1] as [number, number, number, number],
          },
        }
      : {}),
    intrinsics: { fx: 1400, fy: 1400, cx: 960, cy: 540, width_px: 1920, height_px: 1080 },
  });
  state = addNativeKeyframe(state, frame("file:///kf-0001.jpg", 0, true), 100).state;
  state = addNativeKeyframe(state, frame("file:///kf-0002.jpg", 90, true), 2000).state;
  return localCapture(
    CAPTURE_ID,
    state,
    { planes: "file:///planes.json", sceneMesh: null, depth: "file:///depth.sjdepth" },
    "file:///scan.mp4",
  );
}

function deps(failOn: string | null = null) {
  const uploaded: { localId: string; kind: string }[] = [];
  const registered: unknown[] = [];
  const done = new Map<string, string>();
  const ids = new Map<string, string>();
  const value: CaptureUploadDeps = {
    async uploadFile(file) {
      if (file.localId.endsWith(failOn ?? "\u0000")) throw new Error("connection lost");
      uploaded.push({ localId: file.localId, kind: file.kind });
      return { key: `user/${file.localId.split("/")[1]}` };
    },
    writeText: async (name) => `file:///${name}`,
    done: {
      get: async (localId) => done.get(localId) ?? null,
      set: async (localId, key) => void done.set(localId, key),
    },
    register: async (body) => void registered.push(body),
    mediaId: async (captureId) => {
      if (!ids.has(captureId)) ids.set(captureId, uuidV4());
      return ids.get(captureId) as string;
    },
  };
  return { value, uploaded, registered };
}

describe("capture upload", () => {
  it("uploads every file with the right kind, then registers the capture once", async () => {
    const { value, uploaded, registered } = deps();
    const local = scan();
    const result = await uploadAndRegister(local, DEVICE, value);
    expect(uploaded.map((file) => file.kind)).toEqual([
      "sensor_log",
      "keyframe",
      "keyframe",
      "planes",
      "depth",
      "video",
    ]);
    expect(registered).toHaveLength(1);
    expect(registered[0]).toMatchObject({
      id: CAPTURE_ID,
      device: DEVICE,
      media: [
        {
          kind: "photo",
          origin: "camera",
          storage_key: "user/keyframe-k1",
          width_px: 1920,
          height_px: 1080,
          has_ar_pose: true,
        },
      ],
      package: { video: "user/video", planes: "user/planes", depth: "user/depth" },
    });
    expect(result.keyframes).toHaveLength(2);
  });

  it("after a lost connection, a second run sends only what is missing and registers the same body", async () => {
    const { value, uploaded, registered } = deps("video");
    const local = scan();
    await expect(uploadAndRegister(local, DEVICE, value)).rejects.toThrow("connection lost");
    expect(registered).toHaveLength(0);
    const sentFirst = uploaded.length;
    const retry = { ...value, uploadFile: deps().value.uploadFile };
    const sentOnRetry: string[] = [];
    retry.uploadFile = async (file) => {
      sentOnRetry.push(file.kind);
      return { key: `user/${file.localId.split("/")[1]}` };
    };
    await uploadAndRegister(local, DEVICE, retry);
    await uploadAndRegister(local, DEVICE, retry);
    expect(sentFirst).toBe(5);
    expect(sentOnRetry).toEqual(["video"]);
    expect(registered).toHaveLength(2);
    expect(registered[1]).toEqual(registered[0]);
  });

  it("maps package files to upload kinds and content types", () => {
    expect(uploadSpec("keyframe")).toEqual({ kind: "photo", contentType: "image/jpeg" });
    expect(uploadSpec("video")).toEqual({ kind: "video", contentType: "video/mp4" });
    expect(uploadSpec("sensor_log")).toEqual({ kind: "data", contentType: "application/x-ndjson" });
    expect(uploadSpec("planes")).toEqual({ kind: "data", contentType: "application/json" });
    expect(uploadSpec("depth").contentType).toBe("application/octet-stream");
    expect(uploadSpec("scene_mesh").kind).toBe("data");
  });

  it("marks a first keyframe without a pose as such", () => {
    const local = scan();
    const body = registerBody(
      local,
      {
        ar: local.state.ar,
        keyframes: [{ id: "k1", image: "user/k1", captured_at_ms: 0, sharpness: 1 }],
        detections: [],
        sensor_log: "user/log",
      },
      DEVICE,
      uuidV4(),
    );
    expect(body.media[0]).toMatchObject({ has_ar_pose: false, width_px: 1920, height_px: 1440 });
  });

  it("makes version 4 UUIDs", () => {
    const pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    for (let i = 0; i < 50; i += 1) expect(uuidV4()).toMatch(pattern);
    expect(uuidV4()).not.toBe(uuidV4());
  });
});

describe("a video over the server's limit", () => {
  it("is left out and the rest of the scan still registers", async () => {
    const { FileTooLargeError } = jest.requireActual("@/uploads/resumable-upload");
    const { value, registered } = deps();
    let skipped = 0;
    const tooLarge: CaptureUploadDeps = {
      ...value,
      async uploadFile(file) {
        if (file.kind === "video") throw new FileTooLargeError();
        return value.uploadFile(file);
      },
      onVideoSkipped: () => {
        skipped += 1;
      },
    };
    const result = await uploadAndRegister(scan(), DEVICE, tooLarge);
    expect(skipped).toBe(1);
    expect(result.video).toBeUndefined();
    expect(result.keyframes).toHaveLength(2);
    expect(registered).toHaveLength(1);
  });

  it("any other failure of the video still stops the upload so it can resume", async () => {
    const { value, registered } = deps("video");
    await expect(uploadAndRegister(scan(), DEVICE, value)).rejects.toThrow("connection lost");
    expect(registered).toHaveLength(0);
  });
});
