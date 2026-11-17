import { localCapture } from "./native-capture";
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
const scan = (id: string) =>
  localCapture(id, startRecording(0, { tracking: "arkit", lidar: false, depth: false }), {
    planes: "file:///planes.json",
    sceneMesh: null,
    depth: null,
  });

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
  });
});
