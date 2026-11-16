import { render, screen, fireEvent } from "@testing-library/react-native";
import { dependencies } from "../../package.json";
import { ErrorScreen } from "@/components/error-screen";
import { loadConfig } from "@/config";
import {
  clearFatalError,
  describeError,
  getFatalError,
  installGlobalErrorHandler,
  reportError,
  setErrorReporter,
  subscribeToFatalError,
} from "./crash-guard";

function fakeErrorUtils() {
  const previous = jest.fn();
  let handler: (error: unknown, isFatal?: boolean) => void = previous;
  return {
    previous,
    throwError: (error: unknown, isFatal?: boolean) => handler(error, isFatal),
    getGlobalHandler: () => handler,
    setGlobalHandler: (next: typeof handler) => {
      handler = next;
    },
  };
}

afterEach(() => {
  clearFatalError();
  setErrorReporter(() => {});
});

describe("startup fails safe", () => {
  it("has the package that draws the Android tab icons", () => {
    // Without expo-symbols the tab layout throws on Android at launch.
    expect(dependencies).toHaveProperty("expo-symbols");
  });

  it("a bad config value is a result, never an exception", () => {
    const result = loadConfig({ EXPO_PUBLIC_SUPABASE_URL: "https://example.supabase.co" });
    expect(result.ok).toBe(false);
    expect(loadConfig({}).ok).toBe(true);
  });

  it("in a release build a fatal error is kept, reported and not passed to the handler that closes the app", () => {
    const utils = fakeErrorUtils();
    const reporter = jest.fn();
    const listener = jest.fn();
    setErrorReporter(reporter);
    subscribeToFatalError(listener);
    installGlobalErrorHandler(utils, false);

    utils.throwError(new Error("native module missing"), true);

    expect(utils.previous).not.toHaveBeenCalled();
    expect(getFatalError()).toMatchObject({ message: "native module missing", source: "global" });
    expect(reporter).toHaveBeenCalledWith(expect.any(Error), { source: "global", fatal: true });
    expect(listener).toHaveBeenCalled();
  });

  it("a non-fatal error is reported without replacing the screen", () => {
    const utils = fakeErrorUtils();
    installGlobalErrorHandler(utils, false);
    utils.throwError(new Error("minor"), false);
    expect(getFatalError()).toBeNull();
  });

  it("in development the usual error screen still gets the error", () => {
    const utils = fakeErrorUtils();
    installGlobalErrorHandler(utils, true);
    utils.throwError(new Error("dev"), true);
    expect(utils.previous).toHaveBeenCalled();
    expect(getFatalError()).toBeNull();
  });

  it("a reporter that throws does not turn a handled error into a crash", () => {
    setErrorReporter(() => {
      throw new Error("reporter down");
    });
    expect(reportError("plain text", "render").message).toBe("plain text");
  });

  it("the error screen shows a plain message and a way to retry", async () => {
    const retry = jest.fn();
    await render(
      <ErrorScreen error={describeError(new Error("boom"), "render")} onRetry={retry} />,
    );
    expect(screen.getByText("Something went wrong")).toBeTruthy();
    await fireEvent.press(screen.getByText("Try again"));
    expect(retry).toHaveBeenCalled();
  });
});
