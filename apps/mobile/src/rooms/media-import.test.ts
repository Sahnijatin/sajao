import type { PickResult } from "@/import/pick";
import { useCaptureStore } from "@/state/capture";
import { useRooms } from "@/state/rooms";
import { importFromGallery } from "./media-import";

const mockUpload = jest.fn();
jest.mock("@/capture/package/start-upload", () => ({
  startCaptureUpload: (...args: unknown[]) => mockUpload(...args),
}));

const capture = { captureId: "cap-1" } as unknown as Extract<
  PickResult,
  { state: "picked" }
>["capture"];

beforeEach(() => {
  mockUpload.mockClear();
  useRooms.setState({ rooms: [] });
});

describe("making a room from photos or a video", () => {
  it("does nothing when the picker is closed", async () => {
    expect(await importFromGallery(async () => ({ state: "cancelled" }))).toEqual({
      status: "cancelled",
    });
    expect(useRooms.getState().rooms).toHaveLength(0);
    expect(mockUpload).not.toHaveBeenCalled();
  });

  it("passes on why the pictures cannot be used", async () => {
    const result = await importFromGallery(async () => ({
      state: "problem",
      problem: "photosAndVideo",
    }));
    expect(result).toEqual({ status: "problem", problem: "photosAndVideo" });
    expect(mockUpload).not.toHaveBeenCalled();
  });

  it("makes a room on My home and starts the upload with no AR data", async () => {
    const result = await importFromGallery(async () => ({ state: "picked", capture }));
    expect(result).toEqual({ status: "imported", roomId: "cap-1" });
    expect(useRooms.getState().rooms.map((room) => room.captureId)).toEqual(["cap-1"]);
    expect(useCaptureStore.getState().last).toBe(capture);
    expect(mockUpload).toHaveBeenCalledWith(capture, expect.objectContaining({ has_ar: false }));
  });

  it("says it failed when the picker throws", async () => {
    const result = await importFromGallery(async () => {
      throw new Error("no picker in this build");
    });
    expect(result).toEqual({ status: "problem", problem: "failed" });
  });
});
