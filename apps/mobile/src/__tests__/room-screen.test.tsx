import AsyncStorage from "@react-native-async-storage/async-storage";
import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import { Linking } from "react-native";
import "@/i18n";
import { type RoomContent, roomContent } from "@/rooms/room-content";
import { RoomScreen } from "@/screens/room";
import { useSettings } from "@/state/settings";

const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (moment: string) => mockHaptic(moment),
}));

const sample = roomContent("r");
/** The same content as it will arrive from the pipeline: not a sample. */
const real: RoomContent = { ...sample, sample: false };

const show = (content: RoomContent = sample) =>
  render(
    <ThemeProvider tier="standard" reducedMotion>
      <RoomScreen content={content} />
    </ThemeProvider>,
  );
const openTab = (name: string) => fireEvent.press(screen.getByRole("tab", { name }));

beforeEach(async () => {
  mockHaptic.mockClear();
  await AsyncStorage.clear();
  await act(async () => {
    useSettings.setState({ language: null, units: "cm" });
  });
});

describe("room screen", () => {
  it("has exactly three tabs and opens on Room", async () => {
    await show();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.props.accessibilityLabel)).toEqual([
      "Room",
      "Designs",
      "Shopping list",
    ]);
    expect(tabs.map((tab) => tab.props.accessibilityState.selected)).toEqual([true, false, false]);
  });

  it("ticks once when the tab changes, and not when the same tab is tapped", async () => {
    await show();
    await openTab("Room");
    expect(mockHaptic).not.toHaveBeenCalled();
    await openTab("Designs");
    expect(mockHaptic.mock.calls).toEqual([["levelReached"]]);
  });

  it("has no floor-plan import, checkout, paywall or lock on any tab", async () => {
    await show();
    for (const tab of ["Room", "Designs", "Shopping list"]) {
      await openTab(tab);
      expect(
        screen.queryByText(/import|upload a plan|checkout|cart|unlock|upgrade|premium|subscribe/i),
      ).toBeNull();
    }
  });
});

describe("Room tab", () => {
  it("shows the hero views, the size with its source and error band, and the plan slot", async () => {
    await show();
    expect(screen.getByLabelText("Your room, view 1 of 3")).toBeTruthy();
    expect(screen.getByLabelText("Your room, view 3 of 3")).toBeTruthy();
    expect(screen.getByText("410 cm by 340 cm")).toBeTruthy();
    expect(screen.getByText("Ceiling 270 cm")).toBeTruthy();
    expect(screen.getByText("Estimated from your scan, to within 5 cm")).toBeTruthy();
    expect(screen.getByTestId("room-plan-slot")).toBeTruthy();
    expect(screen.getByText(/^These are sample views and sizes\./)).toBeTruthy();
  });

  it("shows sizes in feet and inches when that is the setting", async () => {
    await act(async () => {
      useSettings.setState({ units: "ft_in" });
    });
    await show();
    expect(screen.getByText("13 ft 5 in by 11 ft 2 in")).toBeTruthy();
  });

  it("says so when the room has not been measured, and drops the sample note for a real room", async () => {
    await show({ ...real, dimensions: null });
    expect(screen.getByText("Your room's size appears here once it is measured.")).toBeTruthy();
    expect(screen.queryByText(/sample/i)).toBeNull();
  });
});

describe("Designs tab", () => {
  it("offers the three looks, best match first, each with its own total", async () => {
    await show();
    await openTab("Designs");
    for (const name of ["Best value", "Best match", "Bold"]) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("₹60,496 for everything")).toBeTruthy();
    expect(
      screen.getByText("The sofa faces the window and keeps 0.82 m clear to the door."),
    ).toBeTruthy();
    expect(screen.getByText("Everything fits your room")).toBeTruthy();
    await fireEvent.press(screen.getByText("Bold"));
    expect(screen.getByText("₹79,495 for everything")).toBeTruthy();
    await fireEvent.press(screen.getByText("Best value"));
    expect(screen.getByText("₹33,497 for everything")).toBeTruthy();
  });

  it("keeps the Vastu view off, and says why, until the compass is calibrated", async () => {
    await show();
    await openTab("Designs");
    const toggle = screen.getByTestId("vastu-toggle");
    expect(toggle.props.disabled).toBe(true);
    expect(toggle.props.value).toBe(false);
    expect(screen.getByText("Needs a compass reading from your scan")).toBeTruthy();
    expect(screen.queryByText(/^Vastu guidance, as close as possible\./)).toBeNull();
  });

  it("switches the Vastu view on with a compass reading, with the required label", async () => {
    await show({
      ...real,
      direction: { north_deg: 40, confidence: "approximate", sources: ["compass"] },
    });
    await openTab("Designs");
    const toggle = screen.getByTestId("vastu-toggle");
    expect(toggle.props.disabled).toBe(false);
    expect(screen.queryByText("Needs a compass reading from your scan")).toBeNull();
    await fireEvent(toggle, "valueChange", true);
    expect(
      screen.getByText(
        "Vastu guidance, as close as possible. For a full consultation, speak to an expert.",
      ),
    ).toBeTruthy();
  });

  it("does not count a direction from the door alone as a calibrated compass", async () => {
    await show({
      ...real,
      direction: { north_deg: 40, confidence: "approximate", sources: ["main_door_confirmation"] },
    });
    await openTab("Designs");
    expect(screen.getByTestId("vastu-toggle").props.disabled).toBe(true);
  });
});

describe("Shopping list tab", () => {
  it("lists the chosen look's products with price and fit, and the design's total", async () => {
    await show();
    await openTab("Shopping list");
    expect(screen.getByText("Oak frame three seater sofa")).toBeTruthy();
    expect(screen.getByText("₹42,999")).toBeTruthy();
    expect(screen.getByText("Cane and teak coffee table")).toBeTruthy();
    expect(screen.getAllByText("Fits your room")).toHaveLength(4);
    expect(screen.getByTestId("shopping-total").props.children).toBe("₹60,496");
  });

  it("follows the look chosen on Designs, so the list and the look never disagree", async () => {
    await show();
    await openTab("Designs");
    await fireEvent.press(screen.getByText("Bold"));
    await openTab("Shopping list");
    expect(screen.getByText("Rust velvet armchair")).toBeTruthy();
    expect(screen.getByTestId("shopping-total").props.children).toBe("₹79,495");
    await fireEvent.press(screen.getByText("Best value"));
    expect(screen.queryByText("Rust velvet armchair")).toBeNull();
    expect(screen.getByTestId("shopping-total").props.children).toBe("₹33,497");
    await openTab("Designs");
    expect(screen.getByText("₹33,497 for everything")).toBeTruthy();
  });

  it("opens the retailer's page for a real product", async () => {
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    await show(real);
    await openTab("Shopping list");
    await fireEvent.press(screen.getByRole("button", { name: "Buy Oak frame three seater sofa" }));
    expect(open).toHaveBeenCalledWith("https://www.example.com/p/sofa-oak-3s");
    open.mockRestore();
  });

  it("does not open example links for sample products, and says they are samples", async () => {
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    await show();
    await openTab("Shopping list");
    const buy = screen.getByRole("button", { name: "Buy Oak frame three seater sofa" });
    expect(buy.props.accessibilityState.disabled).toBe(true);
    await fireEvent.press(buy);
    expect(open).not.toHaveBeenCalled();
    expect(screen.getByText(/^These are sample products\./)).toBeTruthy();
    open.mockRestore();
  });

  it("promises no fit for a design that failed the verifier, and marks what is out of stock", async () => {
    const [value, match, bold] = real.looks as [
      RoomContent["looks"][number],
      RoomContent["looks"][number],
      RoomContent["looks"][number],
    ];
    const [sofa, ...rest] = match.design.items;
    const design = {
      ...match.design,
      check_report: { ...match.design.check_report, passed: false, stock_ok: false },
      items: [{ ...sofa, product: { ...sofa.product, in_stock: false } }, ...rest],
    } as typeof match.design;
    await show({ ...real, looks: [value, { ...match, design }, bold] });
    await openTab("Shopping list");
    expect(screen.getByText("Out of stock")).toBeTruthy();
    expect(screen.getAllByText("Needs a fit check")).toHaveLength(3);
    expect(screen.queryByText("Fits your room")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Buy Oak frame three seater sofa" }).props
        .accessibilityState.disabled,
    ).toBe(true);
  });

  it("shows no total rather than one that disagrees with the items", async () => {
    const [value, match, bold] = real.looks as [
      RoomContent["looks"][number],
      RoomContent["looks"][number],
      RoomContent["looks"][number],
    ];
    const design = {
      ...match.design,
      total_cost: { currency: "INR" as const, amount_minor: 100 },
    };
    await show({ ...real, looks: [value, { ...match, design }, bold] });
    await openTab("Shopping list");
    expect(screen.queryByTestId("shopping-total")).toBeNull();
    expect(screen.getByText("Prices are being checked")).toBeTruthy();
  });
});
