import { ThemeProvider } from "@sajao/ui";
import { fireEvent, render, screen } from "@testing-library/react-native";
import "@/i18n";
import { BudgetScreen, type RoomBudget } from "@/screens/budget";

jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);

const last: RoomBudget = {
  limit: { currency: "INR", amount_minor: 15_000_000 },
  flexibility: "stretch_10",
};

const show = async (initial: RoomBudget = last) => {
  const onDone = jest.fn<void, [RoomBudget]>();
  await render(
    <ThemeProvider tier="standard" reducedMotion>
      <BudgetScreen initial={initial} onDone={onDone} />
    </ThemeProvider>,
  );
  return onDone;
};

describe("a room's budget", () => {
  it("starts from the last room's, so keeping it is one tap", async () => {
    const onDone = await show();
    expect(screen.getByRole("header", { name: "Budget for this room" })).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Show me designs" }));
    expect(onDone).toHaveBeenCalledWith(last);
  });

  it("can be changed for this room", async () => {
    const onDone = await show();
    await fireEvent.press(screen.getByText("₹2,50,000"));
    await fireEvent.press(screen.getByText("Keep to it"));
    await fireEvent.press(screen.getByRole("button", { name: "Show me designs" }));
    expect(onDone).toHaveBeenCalledWith({
      limit: { currency: "INR", amount_minor: 25_000_000 },
      flexibility: "strict",
    });
  });

  it("keeps a budget that is not one of the steps", async () => {
    const onDone = await show({ ...last, limit: { currency: "INR", amount_minor: 7_500_000 } });
    expect(screen.getByText("₹75,000")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Show me designs" }));
    expect(onDone.mock.calls[0]?.[0].limit.amount_minor).toBe(7_500_000);
  });
});
