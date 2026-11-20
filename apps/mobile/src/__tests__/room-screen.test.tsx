import AsyncStorage from "@react-native-async-storage/async-storage";
import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen, within } from "@testing-library/react-native";
import { Linking } from "react-native";
import "@/i18n";
import { type RoomContent, sampleContent } from "@/rooms/room-content";
import { RoomScreen, RoomWaiting } from "@/screens/room";
import { useSettings } from "@/state/settings";

// Skia ships ESM that Jest does not load; the plan's numbers are plain text over it.
jest.mock("@/components/plan-canvas", () => ({ PlanCanvas: () => null }));
const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (moment: string) => mockHaptic(moment),
}));

const sample = sampleContent() as RoomContent;
/** The same content as it will arrive from the pipeline: not a sample. */
const real: RoomContent = { ...sample, sample: false };

const show = (
  content: RoomContent = sample,
  props: Partial<React.ComponentProps<typeof RoomScreen>> = {},
) =>
  render(
    <ThemeProvider tier="standard" reducedMotion>
      <RoomScreen content={content} {...props} />
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
  it("is hero photos and measured dimensions, with no 3D view", async () => {
    await show();
    expect(screen.getByLabelText("Your room, view 1 of 3")).toBeTruthy();
    expect(screen.getByLabelText("Your room, view 3 of 3")).toBeTruthy();
    expect(screen.getByText("About 14 m²")).toBeTruthy();
    expect(screen.getByText("290 cm")).toBeTruthy();
    expect(screen.queryByTestId("room-3d-slot")).toBeNull();
    expect(screen.queryByText(/3D/)).toBeNull();
    expect(screen.getByTestId("room-plan-slot")).toBeTruthy();
    expect(screen.getByText(/^These are sample views and measurements\./)).toBeTruthy();
  });

  it("lists every wall by letter with a clean length, and no source until it is tapped", async () => {
    await show();
    const walls = within(screen.getByTestId("room-walls"));
    for (const letter of ["A", "B", "C"]) expect(walls.getByText(`Wall ${letter}`)).toBeTruthy();
    // The fourth side of this room is open: it is not listed as a wall.
    expect(walls.queryByText("Wall D")).toBeNull();
    expect(walls.getAllByText("420 cm")).toHaveLength(2);
    expect(walls.getAllByText("340 cm")).toHaveLength(1);
    expect(screen.queryByTestId("measure-provenance")).toBeNull();
    expect(screen.queryByText(/to within/)).toBeNull();
  });

  it("marks a value approx. only when its band is wider than 5 cm", async () => {
    await show();
    const walls = within(screen.getByTestId("room-walls"));
    // Wall A is measured to 1 cm; walls B and C have bands of 12 and 15 cm.
    expect(walls.getAllByText("approx.")).toHaveLength(2);
    expect(walls.getByRole("button", { name: "Wall A, 420 cm" })).toBeTruthy();
    expect(walls.getByRole("button", { name: "Wall B, approx. 340 cm" })).toBeTruthy();
    // Doors and windows here are within 5 cm, so they carry no label.
    expect(within(screen.getByTestId("room-openings")).queryByText("approx.")).toBeNull();
  });

  it("shows the source and error band on tap, and hides them on a second tap", async () => {
    await show();
    const walls = within(screen.getByTestId("room-walls"));
    const wallA = walls.getByRole("button", { name: "Wall A, 420 cm" });
    expect(wallA.props.accessibilityState).toEqual({ expanded: false });
    await fireEvent.press(wallA);
    expect(walls.getByText("Measured, to within 1 cm")).toBeTruthy();
    expect(screen.getAllByTestId("measure-provenance")).toHaveLength(1);
    await fireEvent.press(walls.getByRole("button", { name: "Wall C, approx. 420 cm" }));
    expect(walls.getByText("Estimated from photos. Measure to confirm fit.")).toBeTruthy();
    await fireEvent.press(wallA);
    expect(walls.queryByText("Measured, to within 1 cm")).toBeNull();
  });

  it("lists doors and windows with their wall and size", async () => {
    await show();
    const openings = within(screen.getByTestId("room-openings"));
    // The door is in the open side, which is not a wall and has no letter.
    expect(openings.getByText("Door")).toBeTruthy();
    expect(openings.getByText("90 cm wide, 205 cm high")).toBeTruthy();
    expect(openings.getByText("Window on wall A")).toBeTruthy();
    expect(openings.getByText("150 cm wide, 120 cm high")).toBeTruthy();
    // A door's width and height share a line: the wider band is the one shown.
    await fireEvent.press(openings.getByText("Door"));
    expect(openings.getByText("Estimated from photos. Measure to confirm fit.")).toBeTruthy();
  });

  it("lists the big items already in the room with their sizes", async () => {
    await show();
    const items = within(screen.getByTestId("room-items"));
    expect(items.getByText("Grey three-seater sofa")).toBeTruthy();
    expect(items.getByText("210 cm by 90 cm, 84 cm high")).toBeTruthy();
    expect(items.getByText("Steel almirah")).toBeTruthy();
    expect(items.getByText("90 cm by 50 cm, 190 cm high")).toBeTruthy();
  });

  it("shows sizes in feet and inches when that is the setting", async () => {
    await act(async () => {
      useSettings.setState({ units: "ft_in" });
    });
    await show();
    expect(screen.getByText("About 154 sq ft")).toBeTruthy();
    expect(within(screen.getByTestId("room-walls")).getAllByText("13 ft 9 in")).toHaveLength(2);
  });

  it("keeps a place for the 3D view only when its flag is on", async () => {
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomScreen content={sample} show3d />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("room-3d-slot")).toBeTruthy();
    // The photos and measurements are still the tab.
    expect(screen.getByTestId("room-walls")).toBeTruthy();
  });

  it("says so when the room has not been measured, and drops the sample note for a real room", async () => {
    await show({ ...real, measures: null });
    expect(
      screen.getByText("Your room's measurements appear here once it is measured."),
    ).toBeTruthy();
    expect(screen.queryByTestId("room-walls")).toBeNull();
    expect(screen.queryByText(/sample/i)).toBeNull();
  });

  it("leaves out the openings and items cards when the twin has none", async () => {
    const measures = { ...sample.measures!, openings: [], bigItems: [] };
    await show({ ...real, measures });
    expect(screen.queryByTestId("room-openings")).toBeNull();
    expect(screen.queryByTestId("room-items")).toBeNull();
    expect(screen.getByTestId("room-walls")).toBeTruthy();
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

  it("says first when a look kept the seating and refreshed around it, and only then", async () => {
    const looks = real.looks.map((look) => ({
      ...look,
      design: { ...look.design, layout_rung: "refresh" as const },
    }));
    const view = await show({ ...real, looks });
    await openTab("Designs");
    expect(screen.getByText("We kept your seating and refreshed around it.")).toBeTruthy();
    await view.rerender(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomScreen content={real} />
      </ThemeProvider>,
    );
    await openTab("Designs");
    expect(screen.queryByTestId("design-refresh")).toBeNull();
  });

  it("shows nothing of Vastu while its build setting is off", async () => {
    await show({
      ...real,
      direction: { north_deg: 40, confidence: "approximate", sources: ["compass"] },
    });
    await openTab("Designs");
    expect(screen.queryByTestId("vastu-toggle")).toBeNull();
    expect(screen.queryByText(/Vastu/)).toBeNull();
  });

  it("keeps the Vastu view off, and says why, until the compass is calibrated", async () => {
    await show(sample, { showVastu: true });
    await openTab("Designs");
    const toggle = screen.getByTestId("vastu-toggle");
    expect(toggle.props.disabled).toBe(true);
    expect(toggle.props.value).toBe(false);
    expect(screen.getByText("Needs a compass reading from your scan")).toBeTruthy();
    expect(screen.queryByText(/^Vastu guidance, as close as possible\./)).toBeNull();
  });

  it("switches the Vastu view on with a compass reading, with the required label", async () => {
    await show(
      {
        ...real,
        direction: { north_deg: 40, confidence: "approximate", sources: ["compass"] },
      },
      { showVastu: true },
    );
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
    await show(
      {
        ...real,
        direction: {
          north_deg: 40,
          confidence: "approximate",
          sources: ["main_door_confirmation"],
        },
      },
      { showVastu: true },
    );
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
    // No item carries its own fit check, so none is said to fit.
    expect(screen.queryByText("Fits your room")).toBeNull();
    expect(screen.getAllByText("Needs a fit check")).toHaveLength(4);
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

  it("carries the same sample label on every tab, above the content", async () => {
    await show();
    for (const [tab, text] of [
      [null, /^These are sample views and measurements\./],
      ["Designs", /^These are sample looks\./],
      ["Shopping list", /^These are sample products\./],
    ] as const) {
      if (tab) await openTab(tab);
      expect(screen.getAllByTestId("sample-note")).toHaveLength(1);
      expect(within(screen.getByTestId("sample-note")).getByText(text)).toBeTruthy();
    }
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

describe("a space that is not a living room or bedroom", () => {
  it.each(["balcony", "other"] as const)("%s: shows the Room tab as usual", async (spaceType) => {
    await show({ ...real, spaceType });
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByTestId("room-walls")).toBeTruthy();
    expect(screen.queryByTestId("designs-coming")).toBeNull();
  });

  it("says plainly on Designs and Shopping list that designs are coming, and shows none", async () => {
    await show({ ...real, spaceType: "balcony" });
    for (const tab of ["Designs", "Shopping list"]) {
      await openTab(tab);
      expect(
        screen.getByText(
          "Designs for this kind of space are coming. Your photos and measurements are on the Room tab.",
        ),
      ).toBeTruthy();
      expect(screen.queryByText("Best match")).toBeNull();
      expect(screen.queryByText(/₹/)).toBeNull();
      expect(screen.queryByTestId("vastu-toggle")).toBeNull();
    }
  });

  it.each(["living_room", "bedroom", null] as const)(
    "%s gets its designs (an unknown kind is not ruled out)",
    async (spaceType) => {
      await show({ ...real, spaceType });
      await openTab("Designs");
      expect(screen.queryByTestId("designs-coming")).toBeNull();
      expect(screen.getByText("₹60,496 for everything")).toBeTruthy();
    },
  );
});

describe("a room with nothing ready yet", () => {
  it("says it is being prepared, with no tabs and no stand-in", async () => {
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomWaiting />
      </ThemeProvider>,
    );
    expect(screen.getByText("This room is not ready yet")).toBeTruthy();
    expect(
      screen.getByText(
        "Your photos are saved. Its measurements and three designs show here once they are ready.",
      ),
    ).toBeTruthy();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.queryByText(/sample|₹/i)).toBeNull();
  });
});

describe("the Room tab's photos", () => {
  it("never shows a blank card: no tile without a picture, and a missing photo drops out", async () => {
    const photo = (id: string) => ({
      id,
      still: { kind: "image", uri: `file:///${id}.jpg` } as const,
    });
    await show({
      ...real,
      heroViews: [
        photo("k1"),
        { id: "plain", still: { kind: "placeholder", look: "before" } },
        photo("k2"),
      ],
    });
    expect(screen.queryByTestId("room-hero-plain")).toBeNull();
    expect(screen.getByTestId("room-hero-k1")).toBeTruthy();
    await act(async () => {
      fireEvent(screen.getByTestId("room-hero-k2").children[0] as never, "error");
    });
    expect(screen.queryByTestId("room-hero-k2")).toBeNull();
  });
});

describe("a room whose job is running or stopped", () => {
  it("shows the stages while there is nothing yet, never a stand-in", async () => {
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomWaiting job={{ stage: "reading", finished: 1 }} />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("job-stage-upload").props.accessibilityState).toEqual({
      busy: false,
      checked: true,
    });
    expect(screen.getByTestId("job-stage-read").props.accessibilityState.busy).toBe(true);
    expect(screen.queryByTestId("sample-note")).toBeNull();
  });

  it("says why it stopped, with a Retry on that room", async () => {
    const onRetry = jest.fn();
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomWaiting job={{ stage: "failed", finished: 1, reason: "upload" }} onRetry={onRetry} />
      </ThemeProvider>,
    );
    expect(screen.getByText(/^The upload didn't finish\./)).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("offers to add a photo to this same room when nothing fits", async () => {
    const onAddPhoto = jest.fn();
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomWaiting
          job={{ stage: "failed", finished: 2, reason: "nothing_fits", retryable: false }}
          onAddPhoto={onAddPhoto}
        />
      </ThemeProvider>,
    );
    await fireEvent.press(screen.getByRole("button", { name: "Add a photo" }));
    expect(onAddPhoto).toHaveBeenCalledTimes(1);
  });

  it("offers to add a photo, and no Retry, when a photo room needs a wider view", async () => {
    const onAddPhoto = jest.fn();
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomWaiting
          job={{ stage: "failed", finished: 2, reason: "needs_wider_view", retryable: false }}
          onRetry={jest.fn()}
          onAddPhoto={onAddPhoto}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText(/Add a photo that shows more of the room/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Add a photo" }));
    expect(onAddPhoto).toHaveBeenCalledTimes(1);
  });

  it("offers no Retry when asking again cannot help, and says what to do instead", async () => {
    await render(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomWaiting
          job={{ stage: "failed", finished: 2, reason: "nothing_fits", retryable: false }}
          onRetry={jest.fn()}
        />
      </ThemeProvider>,
    );
    expect(screen.getByText(/^None of our layouts fit what we could see/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("shows the designing stage on Designs and Shopping list until the designs arrive", async () => {
    await show({ ...real, looks: [] }, { job: { stage: "designing", finished: 2 } });
    await openTab("Designs");
    expect(screen.getByTestId("job-stage-design").props.accessibilityState.busy).toBe(true);
    await openTab("Shopping list");
    expect(screen.getByTestId("job-progress")).toBeTruthy();
  });
});

describe("a room being measured again", () => {
  it("says its designs are based on estimated sizes until the new ones arrive", async () => {
    await show(real, { remeasuring: true });
    expect(
      screen.getByText(
        "Measuring again. These designs are based on estimated sizes until the new ones arrive.",
      ),
    ).toBeTruthy();
    await openTab("Designs");
    expect(screen.getByTestId("remeasuring-note")).toBeTruthy();
  });

  it("says nothing of it otherwise", async () => {
    await show(real);
    expect(screen.queryByTestId("remeasuring-note")).toBeNull();
  });
});

describe("the plan on the Room tab", () => {
  it("draws the room with the chosen look's furniture, with wall lengths and the tightest gaps", async () => {
    await show();
    expect(screen.getByText("Floor plan, Best match")).toBeTruthy();
    const plan = within(screen.getByTestId("room-plan"));
    expect(screen.getByLabelText("Plan of your room with 4 items")).toBeTruthy();
    // Three walls carry a length; the open side is drawn dashed and explained.
    expect(plan.getAllByText("420 cm")).toHaveLength(2);
    expect(plan.getAllByText("340 cm")).toHaveLength(1);
    expect(screen.getByTestId("room-plan-open")).toBeTruthy();
    // The sofa stands 12.5 cm off the far wall.
    expect(plan.getByText("13 cm")).toBeTruthy();
    expect(
      screen.getByText("Walls not yet checked with a tape are drawn with a soft edge."),
    ).toBeTruthy();
  });

  it("shows a tapped piece's size and its own gap to the wall, and lets it go on a second tap", async () => {
    await show();
    expect(screen.getByText("Tap a piece to see its size.")).toBeTruthy();
    await fireEvent.press(screen.getByTestId("plan-item-sofa"));
    const picked = within(screen.getByTestId("room-plan-selected"));
    expect(picked.getByText(/^195 cm wide, 85 cm deep, \d+ cm tall$/)).toBeTruthy();
    expect(screen.getByTestId("plan-item-sofa").props.accessibilityState.selected).toBe(true);
    // Only the sofa's gap is labelled now.
    expect(within(screen.getByTestId("room-plan")).getByText("13 cm")).toBeTruthy();
    await fireEvent.press(screen.getByTestId("plan-item-sofa"));
    expect(screen.queryByTestId("room-plan-selected")).toBeNull();
  });

  it("labels no gaps on a room whose sizes are estimated, and says why", async () => {
    await show({ ...real, confidence: "estimated" });
    expect(within(screen.getByTestId("room-plan")).queryByText("13 cm")).toBeNull();
    await fireEvent.press(screen.getByTestId("plan-item-sofa"));
    expect(screen.getByText(/^195 cm wide/)).toBeTruthy();
    expect(screen.getByText("Gaps to the walls show once the room is measured.")).toBeTruthy();
    // No fit claim on Designs either: one quiet line instead.
    await openTab("Designs");
    expect(screen.queryByText("Everything fits your room")).toBeNull();
    expect(screen.queryByText("Some pieces need a fit check")).toBeNull();
    expect(screen.getByText("Based on your photos. Measure to confirm fit.")).toBeTruthy();
  });

  it("starts with no piece picked when the look changes", async () => {
    await show();
    await fireEvent.press(screen.getByTestId("plan-item-sofa"));
    await openTab("Designs");
    await fireEvent.press(screen.getByText("Bold"));
    await openTab("Room");
    expect(screen.queryByTestId("room-plan-selected")).toBeNull();
  });

  it("follows the look chosen on Designs", async () => {
    await show();
    await openTab("Designs");
    await fireEvent.press(screen.getByText("Bold"));
    await openTab("Room");
    expect(screen.getByText("Floor plan, Bold")).toBeTruthy();
    expect(screen.getByLabelText("Plan of your room with 5 items")).toBeTruthy();
  });

  it("shows lengths in feet and inches when that is the setting", async () => {
    await act(async () => {
      useSettings.setState({ units: "ft_in" });
    });
    await show();
    expect(within(screen.getByTestId("room-plan")).getAllByText("13 ft 9 in")).toHaveLength(2);
  });

  it("draws the room alone for a space with no designs", async () => {
    await show({ ...real, spaceType: "balcony" });
    expect(screen.getByText("Floor plan")).toBeTruthy();
    expect(screen.getByLabelText("Plan of your room with 0 items")).toBeTruthy();
  });

  it("drops the soft-edge note once every wall is tape-measured, and the plan when there is no outline", async () => {
    const shell = sample.shell!;
    const measured = {
      ...shell,
      walls: shell.walls.map((wall) => ({
        ...wall,
        length: { ...wall.length, source: "measured" as const },
      })),
    } as typeof shell;
    const view = await show({ ...real, shell: measured });
    expect(screen.queryByText(/soft edge/)).toBeNull();
    await view.rerender(
      <ThemeProvider tier="standard" reducedMotion>
        <RoomScreen content={{ ...real, shell: null }} />
      </ThemeProvider>,
    );
    expect(screen.queryByTestId("room-plan-slot")).toBeNull();
  });
});

describe("shopping list: photos and per-item fit", () => {
  const [value, match, bold] = real.looks as [
    RoomContent["looks"][number],
    RoomContent["looks"][number],
    RoomContent["looks"][number],
  ];
  const [sofa, lamp, ...rest] = match.design.items;
  const withFits = {
    ...real,
    looks: [
      value,
      {
        ...match,
        design: {
          ...match.design,
          items: [
            { ...sofa, fit: { status: "fits", clearance_m: 0.12 } },
            { ...lamp, fit: { status: "does_not_fit" } },
            ...rest,
          ],
        } as unknown as typeof match.design,
      },
      bold,
    ],
  };

  it("shows each real product's photo, and none for samples", async () => {
    const view = await show(real);
    await openTab("Shopping list");
    expect(screen.getByTestId("shopping-photo-sofa").props.source).toEqual({
      uri: "https://cdn.example.com/products/sofa-oak-3s/front.jpg",
    });
    await view.unmount();
    await show();
    await openTab("Shopping list");
    expect(screen.queryByTestId("shopping-photo-sofa")).toBeNull();
  });

  it("says how each item fits, with the space to spare when the verifier gave it", async () => {
    await show(withFits);
    await openTab("Shopping list");
    expect(screen.getByText("Fits with 12 cm to spare")).toBeTruthy();
    expect(screen.getByText("Does not fit here")).toBeTruthy();
    // Items without their own verdict promise nothing.
    expect(screen.queryByText("Fits your room")).toBeNull();
    expect(screen.getAllByText("Needs a fit check")).toHaveLength(2);
  });

  it("does not offer to buy an item that does not fit", async () => {
    await show(withFits);
    await openTab("Shopping list");
    expect(
      screen.getByRole("button", { name: "Buy Paper shade floor lamp" }).props.accessibilityState
        .disabled,
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: "Buy Oak frame three seater sofa" }).props
        .accessibilityState.disabled,
    ).toBe(false);
  });
});

describe("how far to trust the numbers", () => {
  it("says a scanned room was measured by the scan", async () => {
    await show(real);
    expect(
      within(screen.getByTestId("room-confidence")).getByText("Measured by your scan"),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Measure this room for exact fit" })).toBeNull();
  });

  it("says a taped room was checked with a tape", async () => {
    await show({ ...real, confidence: "taped" });
    expect(screen.getByText("Checked with a tape")).toBeTruthy();
  });

  it("an estimated room says so, offers to measure, and makes no fit claims", async () => {
    const onMeasure = jest.fn();
    await show({ ...real, confidence: "estimated" }, { onMeasure });
    expect(screen.getByText("Estimated from photos")).toBeTruthy();
    expect(screen.getByText("Measure to confirm fit.")).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Measure this room for exact fit" }));
    expect(onMeasure).toHaveBeenCalledTimes(1);
    await openTab("Shopping list");
    expect(screen.getAllByText("Measure your room to confirm the fit").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Fits|A tight fit|Does not fit/)).toBeNull();
  });

  it("says nothing when the level is not known", async () => {
    await show({ ...real, confidence: null });
    expect(screen.queryByTestId("room-confidence")).toBeNull();
  });
});

describe("a scan of several areas", () => {
  const living = {
    id: "a1",
    spaceType: "living_room" as const,
    photo: null,
    heroViews: real.heroViews,
    measures: real.measures,
    shell: real.shell,
    confidence: "measured" as const,
  };
  const dining = {
    ...living,
    id: "a2",
    spaceType: "other" as const,
    heroViews: [],
    measures: { ...real.measures!, areaM2: 9 },
  };
  const several: RoomContent = { ...real, areas: [living, dining] };

  it("asks for a choice before any designs, and keeps every area's Room tab", async () => {
    const onChooseArea = jest.fn();
    await show(several, { onChooseArea });
    expect(within(screen.getByTestId("room-areas")).getByText("Living room")).toBeTruthy();
    expect(screen.getByText("About 14 m²")).toBeTruthy();
    await fireEvent.press(within(screen.getByTestId("room-areas")).getByText("Something else"));
    expect(screen.getByText("About 9 m²")).toBeTruthy();
    await openTab("Designs");
    expect(screen.getByTestId("areas-choose")).toBeTruthy();
    expect(screen.queryByText("Best match")).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Choose an area" }));
    expect(onChooseArea).toHaveBeenCalledTimes(1);
  });

  it("shows designs for the chosen area only, and says which", async () => {
    await show(several, { redesignAreaId: "a1", onChooseArea: jest.fn() });
    await openTab("Designs");
    expect(screen.getByText("Designs for: Living room")).toBeTruthy();
    expect(screen.getAllByText("Best match").length).toBeGreaterThan(0);
    await openTab("Shopping list");
    expect(screen.getByText("Designs for: Living room")).toBeTruthy();
  });

  it("a scan of one area shows no area picker", async () => {
    await show({ ...real, areas: [living] });
    expect(screen.queryByTestId("room-areas")).toBeNull();
    await openTab("Designs");
    expect(screen.queryByTestId("areas-chosen")).toBeNull();
  });
});
