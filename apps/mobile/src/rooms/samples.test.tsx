import { ThemeProvider } from "@sajao/ui";
import { render, screen } from "@testing-library/react-native";
import { Text } from "react-native";
import "@/i18n";
import { useRoomData } from "@/state/room-data";
import { designsOffered, roomContent, sampleContent, useRoomContent } from "./room-content";
import { roomSpaceProfile } from "./room-space";
import { RoomStillView } from "./room-still";

let mockPreview = true;
jest.mock("@/preview-screens", () => ({ previewScreensEnabled: () => mockPreview }));

describe("stand-in content by build", () => {
  it("development and preview builds have a sample for the preview screens", () => {
    mockPreview = true;
    expect(sampleContent()?.sample).toBe(true);
  });

  it("a store or closed-test build has none", () => {
    mockPreview = false;
    expect(sampleContent()).toBeNull();
  });

  it.each([true, false])(
    "a person's room is never a sample, in any build (preview %s)",
    (preview) => {
      mockPreview = preview;
      expect(roomContent("r")).toBeNull();
      expect(roomSpaceProfile("r")).toBeNull();
    },
  );

  it("a room shows what the server sent for it", async () => {
    mockPreview = true;
    const real = {
      ...(sampleContent() as NonNullable<ReturnType<typeof sampleContent>>),
      sample: false,
    };
    useRoomData.getState().setContent("r", real);
    expect(roomContent("r")).toBe(real);
    expect(roomContent("other")).toBeNull();
    function Probe() {
      return <Text>{String(useRoomContent("r")?.sample)}</Text>;
    }
    await render(<Probe />);
    expect(screen.getByText("false")).toBeTruthy();
  });

  it("a store build never draws a stand-in room; a real photo still shows", async () => {
    mockPreview = false;
    const view = await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomStillView testID="still" still={{ kind: "placeholder", look: "after" }} />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("still").children).toHaveLength(0);
    await view.rerender(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomStillView testID="still" still={{ kind: "image", uri: "file:///hero.jpg" }} />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("still").children).toHaveLength(1);
  });

  it("a person's room card never draws a stand-in, even where samples are allowed", async () => {
    mockPreview = true;
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomStillView
          testID="still"
          drawn={false}
          still={{ kind: "placeholder", look: "before" }}
        />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("still").children).toHaveLength(0);
  });
});

describe("which spaces get designs", () => {
  it("living rooms and bedrooms at launch; any other known kind does not, yet", () => {
    expect(designsOffered("living_room")).toBe(true);
    expect(designsOffered("bedroom")).toBe(true);
    expect(designsOffered("balcony")).toBe(false);
    expect(designsOffered("other")).toBe(false);
    expect(designsOffered(null)).toBe(true);
  });
});
