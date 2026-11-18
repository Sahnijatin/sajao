import { ThemeProvider } from "@sajao/ui";
import { render, screen } from "@testing-library/react-native";
import "@/i18n";
import { designsOffered, roomContent } from "./room-content";
import { roomSpaceProfile } from "./room-space";
import { RoomStillView } from "./room-still";

let mockPreview = true;
jest.mock("@/preview-screens", () => ({ previewScreensEnabled: () => mockPreview }));

describe("stand-in content by build", () => {
  it("development and preview builds get the sample room and space profile", () => {
    mockPreview = true;
    expect(roomContent("r")?.sample).toBe(true);
    expect(roomSpaceProfile("r")).not.toBeNull();
  });

  it("a store or closed-test build gets none of it", () => {
    mockPreview = false;
    expect(roomContent("r")).toBeNull();
    expect(roomSpaceProfile("r")).toBeNull();
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
