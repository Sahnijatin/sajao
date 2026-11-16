import { uploadMessage } from "./upload-status";

jest.mock("@/capture/package/start-upload", () => ({ startCaptureUpload: jest.fn() }));

describe("upload status", () => {
  it("shows nothing before the first scan", () => {
    expect(uploadMessage({ state: "idle", finished: 0, total: 0 })).toBeNull();
  });

  it("counts files while uploading and says when the scan is up", () => {
    expect(uploadMessage({ state: "uploading", finished: 0, total: 0 })).toEqual({
      key: "home.upload.starting",
    });
    expect(uploadMessage({ state: "uploading", finished: 3, total: 12 })).toEqual({
      key: "home.upload.uploading",
      values: { finished: 3, total: 12 },
    });
    expect(uploadMessage({ state: "done", finished: 1, total: 1 })?.key).toBe("home.upload.done");
    expect(uploadMessage({ state: "done", finished: 1, total: 1, videoSkipped: true })?.key).toBe(
      "home.upload.doneNoVideo",
    );
  });

  it("says the scan is safe when the upload paused or there is no server", () => {
    expect(uploadMessage({ state: "failed", finished: 0, total: 0 })?.key).toBe(
      "home.upload.failed",
    );
    expect(uploadMessage({ state: "waiting", finished: 0, total: 0 })?.key).toBe(
      "home.upload.waiting",
    );
  });
});
