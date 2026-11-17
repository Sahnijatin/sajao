import { useCaptureStore } from "@/state/capture";
import { localCapture } from "./native-capture";
import { startRecording } from "./recorder";
import { startCaptureUpload } from "./start-upload";

// The preview build today: no API URL is set for it.
jest.mock("@/config", () => ({
  configResult: {
    ok: true,
    config: {
      environment: "preview",
      apiUrl: null,
      supabase: { url: "https://example.supabase.co", publishableKey: "sb_publishable_x" },
    },
  },
}));

describe("starting a capture upload", () => {
  it("keeps the scan on the phone and marks it as waiting when the build has no server", async () => {
    const fetchSpy = jest.spyOn(globalThis, "fetch");
    const local = localCapture(
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      startRecording(0, { tracking: "arcore", lidar: false, depth: false }),
      { planes: null, sceneMesh: null, depth: null },
    );
    await startCaptureUpload(local, { platform: "android", tier: "low", has_ar: true });
    expect(useCaptureStore.getState().upload).toEqual({ state: "waiting", finished: 0, total: 0 });
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
