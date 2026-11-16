import { screen } from "@testing-library/react-native";
import { renderRouter } from "expo-router/testing-library";
import { Text } from "react-native";
import { RouteErrorBoundary } from "@/components/route-error-boundary";

// What happened on Android: a layout needed a native module that was not in
// the build and threw while rendering. The app must show the error screen.
function BrokenLayout(): never {
  throw new Error("Cannot find native module 'ExpoSymbols'");
}

describe("a missing native module", () => {
  it("shows the error screen instead of closing the app", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    await renderRouter({
      _layout: { default: BrokenLayout, ErrorBoundary: RouteErrorBoundary },
      index: () => <Text>Home</Text>,
    });
    expect(await screen.findByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText(/Cannot find native module 'ExpoSymbols'/)).toBeTruthy();
    expect(screen.queryByText("Home")).toBeNull();
  });
});
