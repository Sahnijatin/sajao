import type { SpaceProfile } from "@sajao/schemas";
import { validate } from "@sajao/schemas/validate";
import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import i18n from "@/i18n";
import { SpaceProfileScreen } from "@/screens/space-profile";
import { useSettings } from "@/state/settings";
import fixture from "../../../../packages/schemas/fixtures/v1/valid/space-profile.json";

jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);
// The plan is drawn with Skia, which needs a device.
jest.mock("@/space/plan-view", () => ({ PlanView: () => null }));

const profile = fixture as unknown as SpaceProfile;

async function show(current: SpaceProfile = profile) {
  const onChange = jest.fn();
  const onShowIdeas = jest.fn();
  const onChoosePart = jest.fn();
  const view = await render(
    <ThemeProvider tier="standard" reducedMotion>
      <SpaceProfileScreen
        profile={current}
        onChange={onChange}
        onShowIdeas={onShowIdeas}
        onChoosePart={onChoosePart}
      />
    </ThemeProvider>,
  );
  return { view, onChange, onShowIdeas, onChoosePart };
}

beforeEach(async () => {
  await act(async () => {
    useSettings.setState({ language: null, units: "cm" });
    await i18n.changeLanguage("en");
  });
});

describe("Space Profile card", () => {
  it("says what was found, with an honest estimated badge", async () => {
    await show();
    expect(screen.getByText("A living room")).toBeTruthy();
    expect(screen.getByText("About 14 m² · 1 window · 1 door · morning light")).toBeTruthy();
    expect(screen.getByText("Estimated ±15 cm")).toBeTruthy();
    expect(screen.queryByText("Verified")).toBeNull();
  });

  it("shows sizes in feet when the user chose feet and inches", async () => {
    await act(async () => useSettings.setState({ units: "ft_in" }));
    await show();
    expect(screen.getByText("About 154 sq ft · 1 window · 1 door · morning light")).toBeTruthy();
    expect(screen.getByText("Estimated ±0 ft 6 in")).toBeTruthy();
  });

  it("names a partial scan as part of the space", async () => {
    await show({ ...profile, extent: "part" });
    expect(screen.getByText("Part of A living room")).toBeTruthy();
  });

  it("shows Verified only for a verified profile", async () => {
    await show({ ...profile, verification: "verified" });
    expect(screen.getByText("Verified")).toBeTruthy();
    expect(screen.queryByText(/Estimated/)).toBeNull();
  });

  it("offers all of it or just a part, with all of it selected first", async () => {
    const { onChoosePart, onChange } = await show();
    const [all, part] = screen.getAllByRole("radio");
    expect(all!.props.accessibilityState).toEqual({ checked: true });
    expect(part!.props.accessibilityState).toEqual({ checked: false });
    await fireEvent.press(part!);
    expect(onChoosePart).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("cycles an existing item through keep, replace and remove with a valid profile", async () => {
    const { onChange } = await show();
    await fireEvent.press(screen.getByRole("button", { name: "Three seater sofa: Replace" }));
    const changed = onChange.mock.calls[0]![0] as SpaceProfile;
    expect(changed.existing_items[0]!.action).toBe("remove");
    expect(validate("SpaceProfile", JSON.parse(JSON.stringify(changed))).ok).toBe(true);
  });

  it("moves on to ideas", async () => {
    const { onShowIdeas } = await show();
    await fireEvent.press(screen.getByRole("button", { name: "Show me ideas" }));
    expect(onShowIdeas).toHaveBeenCalledTimes(1);
  });

  it("renders in Hindi", async () => {
    await act(async () => {
      await i18n.changeLanguage("hi");
    });
    await show();
    expect(screen.getByText("एक लिविंग रूम")).toBeTruthy();
    expect(screen.getByText("हम क्या नया करें?")).toBeTruthy();
  });

  it("does not offer Just a part while there is no screen to draw it on", async () => {
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <SpaceProfileScreen profile={profile} onChange={jest.fn()} onShowIdeas={jest.fn()} />
      </ThemeProvider>,
    );
    expect(screen.getByText("All of it")).toBeTruthy();
    expect(screen.queryByText("Just a part")).toBeNull();
  });
});
