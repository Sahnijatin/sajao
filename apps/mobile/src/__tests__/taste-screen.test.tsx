import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import i18n from "@/i18n";
import { TasteScreen } from "@/screens/taste";
import type { TasteAnswers } from "@/taste/taste-session";

jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);

const press = (name: string) => fireEvent.press(screen.getByRole("button", { name }));

async function show() {
  const onDone = jest.fn<void, [TasteAnswers]>();
  await render(
    <ThemeProvider tier="standard" reducedMotion>
      <TasteScreen onDone={onDone} />
    </ThemeProvider>,
  );
  return onDone;
}

beforeEach(async () => {
  await act(async () => {
    await i18n.changeLanguage("en");
  });
});

describe("taste onboarding screen", () => {
  it("asks for a little context before the swipes", async () => {
    await show();
    expect(screen.getByText("A little about you")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue" }).props.accessibilityState.disabled).toBe(
      true,
    );
    await press("25 to 34");
    await press("A couple");
    await press("Rented");
    await press("Continue");
    expect(screen.getByText("Would you live here?")).toBeTruthy();
    expect(screen.getByText("1 of 10")).toBeTruthy();
  });

  it("runs the whole flow and hands back the answers", async () => {
    const onDone = await show();
    await press("25 to 34");
    await press("A couple");
    await press("Rented");
    await press("Continue");

    let swipes = 0;
    while (screen.queryByText("Would you live here?")) {
      await press(swipes % 3 === 0 ? "Not for me" : "Love it");
      swipes += 1;
    }
    expect(swipes).toBeGreaterThanOrEqual(8);
    expect(swipes).toBeLessThanOrEqual(12);

    expect(screen.getAllByText("What is your budget?").length).toBeGreaterThan(0);
    // Vastu is behind its build setting, off.
    expect(screen.queryByText(/Vastu/)).toBeNull();
    await press("₹1,50,000");
    await press("Can stretch 10%");
    await press("Sofa");
    await press("Done");

    const answers = onDone.mock.calls[0]![0];
    expect(answers.context).toEqual({ age_band: "25_34", household: ["couple"], tenure: "rented" });
    expect(answers.budget).toEqual({
      limit: { currency: "INR", amount_minor: 15_000_000 },
      flexibility: "stretch_10",
    });
    expect(answers.must_haves).toEqual(["sofa"]);
    expect(answers.consider_vastu).toBe(false);
    expect(answers.swipes).toHaveLength(swipes);
  });

  it("never shows the age band back after it is asked", async () => {
    await show();
    await press("55 or more");
    await press("Just me");
    await press("Owned");
    await press("Continue");
    expect(screen.queryByText(/55/)).toBeNull();
    expect(screen.queryByText(/age/i)).toBeNull();
  });

  it("shows your taste so far once there is something to say", async () => {
    await show();
    await press("25 to 34");
    await press("Pets");
    await press("Owned");
    await press("Continue");
    expect(screen.queryByText("YOUR TASTE SO FAR")).toBeNull();
    await press("Love it");
    expect(screen.getByText("YOUR TASTE SO FAR")).toBeTruthy();
  });

  it("renders in Hindi", async () => {
    await act(async () => {
      await i18n.changeLanguage("hi");
    });
    await show();
    expect(screen.getByText("थोड़ा आपके बारे में")).toBeTruthy();
  });
});
