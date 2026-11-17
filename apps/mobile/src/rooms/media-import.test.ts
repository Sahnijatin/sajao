import { MAX_MEDIA, type Picker, pickMedia } from "./media-import";

const picker = (over: Partial<Picker> = {}): Picker => ({
  requestMediaLibraryPermissionsAsync: async () => ({ granted: true }),
  launchImageLibraryAsync: async () => ({ canceled: true }),
  ...over,
});

describe("choosing photos or a video", () => {
  it("says so when this build has no picker", async () => {
    expect(await pickMedia(async () => null)).toEqual({ status: "unavailable" });
  });

  it("says so when the phone refuses the photo library", async () => {
    const load = async () =>
      picker({ requestMediaLibraryPermissionsAsync: async () => ({ granted: false }) });
    expect(await pickMedia(load)).toEqual({ status: "denied" });
  });

  it("is nothing when the picker is closed", async () => {
    expect(await pickMedia(async () => picker())).toEqual({ status: "cancelled" });
  });

  it("returns photos and videos as they are, a video with its length", async () => {
    const launch = jest.fn(async () => ({
      canceled: false,
      assets: [
        { uri: "file://a.jpg", type: "image" },
        { uri: "file://b.mov", type: "video", duration: 42000 },
      ],
    }));
    const result = await pickMedia(async () => picker({ launchImageLibraryAsync: launch }));
    expect(result).toEqual({
      status: "picked",
      media: [
        { uri: "file://a.jpg", kind: "photo", durationS: null },
        { uri: "file://b.mov", kind: "video", durationS: 42 },
      ],
    });
    expect(launch).toHaveBeenCalledWith(
      expect.objectContaining({
        allowsMultipleSelection: true,
        selectionLimit: MAX_MEDIA,
        allowsEditing: false,
      }),
    );
  });
});
