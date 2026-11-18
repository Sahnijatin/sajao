import { ThemeProvider } from "@sajao/ui";
import { act, fireEvent, render, screen } from "@testing-library/react-native";
import type { ReactElement } from "react";
import "@/i18n";
import type { GenerationSource } from "@/rooms/generation";
import { type RoomContent, roomContent } from "@/rooms/room-content";
import { GeneratingScreen, HANDOVER_MS } from "@/screens/generating";
import { RevealScreen } from "@/screens/reveal";

jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);
const mockHaptic = jest.fn();
jest.mock("@sajao/ui", () => ({
  ...jest.requireActual("@sajao/ui"),
  playHaptic: (moment: string) => mockHaptic(moment),
}));

const show = (ui: ReactElement) =>
  render(
    <ThemeProvider tier="standard" reducedMotion>
      {ui}
    </ThemeProvider>,
  );

beforeEach(() => mockHaptic.mockClear());

describe("generating", () => {
  /** A source the test moves forward by hand. */
  function manualSource() {
    let report: (finished: number) => void = () => {};
    const source: GenerationSource = {
      watch(_roomId, onFinished) {
        report = onFinished;
        return () => {};
      },
    };
    return { source, finish: (count: number) => act(async () => report(count)) };
  }
  const stage = (id: string) => screen.getByTestId(`stage-${id}`).props.accessibilityState;

  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("shows three stages in plain words, the first in hand", async () => {
    const { source } = manualSource();
    await show(<GeneratingScreen roomId="r" onDone={jest.fn()} source={source} />);
    expect(screen.getByRole("header", { name: "Designing your room" })).toBeTruthy();
    expect(screen.getByText("Measuring your walls")).toBeTruthy();
    expect(screen.getByText("Finding your furniture")).toBeTruthy();
    expect(screen.getByText("Designing three looks")).toBeTruthy();
    expect(stage("walls")).toEqual({ busy: true, checked: false });
    expect(stage("furniture")).toEqual({ busy: false, checked: false });
    // No bar, and no percentage to watch.
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it("ticks each stage off with a light tick, then hands on to the reveal", async () => {
    const onDone = jest.fn();
    const { source, finish } = manualSource();
    await show(<GeneratingScreen roomId="r" onDone={onDone} source={source} />);
    await finish(1);
    expect(stage("walls")).toEqual({ busy: false, checked: true });
    expect(stage("furniture")).toEqual({ busy: true, checked: false });
    expect(mockHaptic).toHaveBeenCalledTimes(1);
    await finish(2);
    await finish(3);
    expect(stage("looks")).toEqual({ busy: false, checked: true });
    expect(mockHaptic.mock.calls).toEqual([
      ["cornerCaptured"],
      ["cornerCaptured"],
      ["cornerCaptured"],
    ]);
    // It never just ends: the last tick shows, then the reveal opens.
    expect(onDone).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(HANDOVER_MS);
    });
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("never goes backwards if reports arrive out of order", async () => {
    const { source, finish } = manualSource();
    await show(<GeneratingScreen roomId="r" onDone={jest.fn()} source={source} />);
    await finish(2);
    await finish(1);
    expect(stage("furniture")).toEqual({ busy: false, checked: true });
    expect(mockHaptic).toHaveBeenCalledTimes(1);
  });
});

describe("reveal", () => {
  const content = roomContent("r") as RoomContent;

  it("shows the room's hero views first, and no designs yet", async () => {
    await show(<RevealScreen content={content} onOpenRoom={jest.fn()} />);
    expect(screen.getByRole("header", { name: "Here's your room" })).toBeTruthy();
    expect(screen.getByLabelText("Your room, view 1 of 3")).toBeTruthy();
    expect(screen.getByLabelText("Your room, view 3 of 3")).toBeTruthy();
    expect(screen.queryByText("Best match")).toBeNull();
    expect(screen.queryByText(/₹/)).toBeNull();
    expect(mockHaptic).not.toHaveBeenCalled();
  });

  it("then the three looks, each with the total from its own design", async () => {
    const onOpenRoom = jest.fn();
    await show(<RevealScreen content={content} onOpenRoom={onOpenRoom} />);
    await fireEvent.press(screen.getByRole("button", { name: "See my three looks" }));
    expect(mockHaptic).toHaveBeenCalledWith("designReveal");
    expect(screen.getByRole("header", { name: "Three looks for your room" })).toBeTruthy();
    expect(screen.queryByLabelText("Your room, view 1 of 3")).toBeNull();
    for (const [name, total] of [
      ["Best value", "₹33,497 for everything"],
      ["Best match", "₹60,496 for everything"],
      ["Bold", "₹79,495 for everything"],
    ] as const) {
      expect(screen.getByText(name)).toBeTruthy();
      expect(screen.getByText(total)).toBeTruthy();
    }
    await fireEvent.press(screen.getByRole("button", { name: "Open my room" }));
    expect(onOpenRoom).toHaveBeenCalledTimes(1);
  });

  it("says so when the looks are samples, and not when they are real", async () => {
    const view = await show(<RevealScreen content={content} onOpenRoom={jest.fn()} />);
    await fireEvent.press(screen.getByRole("button", { name: "See my three looks" }));
    expect(screen.getByText(/^These are sample looks\./)).toBeTruthy();
    await view.rerender(
      <ThemeProvider tier="standard" reducedMotion>
        <RevealScreen content={{ ...content, sample: false }} onOpenRoom={jest.fn()} />
      </ThemeProvider>,
    );
    expect(screen.queryByText(/sample/i)).toBeNull();
  });

  it("has no paywall, lock or checkout", async () => {
    await show(<RevealScreen content={content} onOpenRoom={jest.fn()} />);
    await fireEvent.press(screen.getByRole("button", { name: "See my three looks" }));
    expect(screen.queryByText(/unlock|upgrade|premium|checkout|pay/i)).toBeNull();
  });

  it("a space that gets no designs yet reveals the room and goes straight to it", async () => {
    const onOpenRoom = jest.fn();
    await show(
      <RevealScreen content={{ ...content, spaceType: "balcony" }} onOpenRoom={onOpenRoom} />,
    );
    expect(screen.getByLabelText("Your room, view 1 of 3")).toBeTruthy();
    expect(screen.getByText(/^Designs for this kind of space are coming\./)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "See my three looks" })).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Open my room" }));
    expect(onOpenRoom).toHaveBeenCalledTimes(1);
  });
});

describe("generating for a space with no designs", () => {
  it("leaves out the designing stage and still hands on", async () => {
    jest.useFakeTimers();
    try {
      const onDone = jest.fn();
      let report: (finished: number) => void = () => {};
      const source: GenerationSource = {
        watch(_roomId, onFinished) {
          report = onFinished;
          return () => {};
        },
      };
      await show(<GeneratingScreen roomId="r" onDone={onDone} source={source} designs={false} />);
      expect(screen.getByRole("header", { name: "Getting your room ready" })).toBeTruthy();
      expect(screen.getByText("Finding your furniture")).toBeTruthy();
      expect(screen.queryByText("Designing three looks")).toBeNull();
      await act(async () => report(2));
      await act(async () => {
        jest.advanceTimersByTime(HANDOVER_MS);
      });
      expect(onDone).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("generating: a stage that fails", () => {
  const failing = (reason: string): GenerationSource => ({
    watch(_roomId, _onFinished, onFailed) {
      onFailed?.(reason);
      return () => {};
    },
  });

  it("says what happened in plain words and offers the way back", async () => {
    const onLeave = jest.fn();
    const onDone = jest.fn();
    await show(
      <GeneratingScreen
        roomId="r"
        onDone={onDone}
        onLeave={onLeave}
        source={failing("no_walls")}
      />,
    );
    expect(screen.getByRole("header", { name: "We couldn't finish this room" })).toBeTruthy();
    expect(screen.getByText(/^We couldn't find the walls\./)).toBeTruthy();
    expect(screen.queryByText("Measuring your walls")).toBeNull();
    await fireEvent.press(screen.getByRole("button", { name: "Back to My home" }));
    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();
  });

  it("never shows a reason code: an unknown one gets the general message", async () => {
    await show(<GeneratingScreen roomId="r" onDone={jest.fn()} source={failing("gpu_oom_17")} />);
    expect(screen.getByText(/^Something went wrong on our side\./)).toBeTruthy();
    expect(screen.queryByText(/gpu_oom_17/)).toBeNull();
  });

  it("an upload that failed says so", async () => {
    await show(<GeneratingScreen roomId="r" onDone={jest.fn()} source={failing("upload")} />);
    expect(screen.getByText(/^Your scan didn't upload\./)).toBeTruthy();
  });
});
