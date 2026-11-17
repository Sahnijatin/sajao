import { ThemeProvider } from "@sajao/ui";
import { render, screen } from "@testing-library/react-native";
import { BeforeAfter } from "./before-after";
import "@/i18n";

const show = (reducedMotion: boolean) =>
  render(
    <ThemeProvider tier="standard" reducedMotion={reducedMotion}>
      <BeforeAfter
        before={{ kind: "placeholder", look: "before" }}
        after={{ kind: "image", uri: "file:///after.jpg" }}
      />
    </ThemeProvider>,
  );

describe("before and after", () => {
  it("is one picture to a screen reader, with both stills labelled", async () => {
    await show(false);
    expect(screen.getByLabelText("A room before and after a redesign")).toBeTruthy();
    expect(screen.getByText("Before")).toBeTruthy();
    expect(screen.getByText("After")).toBeTruthy();
  });

  it("shows both stills side by side, unmoving, with reduced motion", async () => {
    await show(true);
    const picture = screen.getByTestId("before-after");
    expect(picture.props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({ flexDirection: "row" })]),
    );
  });
});
