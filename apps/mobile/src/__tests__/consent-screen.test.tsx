import { ThemeProvider } from "@sajao/ui";
import { fireEvent, render, screen } from "@testing-library/react-native";
import { Linking } from "react-native";
import "@/i18n";
import { ConsentScreen } from "@/screens/consent";
import { CONSENT_VERSION, hasConsent, useConsent } from "@/state/consent";

jest.mock(
  "react-native-safe-area-context",
  () => jest.requireActual("react-native-safe-area-context/jest/mock").default,
);

const legal = { privacyUrl: "https://sajao.app/privacy", termsUrl: "https://sajao.app/terms" };

const show = (props: Partial<React.ComponentProps<typeof ConsentScreen>> = {}) =>
  render(
    <ThemeProvider tier="standard" reducedMotion>
      <ConsentScreen legal={legal} onAccept={jest.fn()} {...props} />
    </ThemeProvider>,
  );

describe("consent at first use", () => {
  it("says plainly what happens to your photos, and that you can delete everything", async () => {
    await show();
    expect(screen.getByRole("header", { name: "Before you start" })).toBeTruthy();
    expect(screen.getByText(/^Your photos and scans go to Sajao/)).toBeTruthy();
    expect(screen.getByText(/delete your account and everything kept for it/)).toBeTruthy();
  });

  it("opens the privacy policy and terms", async () => {
    const open = jest.spyOn(Linking, "openURL").mockResolvedValue(undefined);
    await show();
    await fireEvent.press(screen.getByRole("button", { name: "Privacy policy" }));
    await fireEvent.press(screen.getByRole("button", { name: "Terms" }));
    expect(open.mock.calls).toEqual([[legal.privacyUrl], [legal.termsUrl]]);
    open.mockRestore();
  });

  it("links nothing while the policy is not hosted", async () => {
    await show({ legal: null });
    expect(screen.queryByRole("button", { name: "Privacy policy" })).toBeNull();
    expect(screen.queryByText(/you agree to/)).toBeNull();
  });

  it("agrees once, for the current wording", async () => {
    const onAccept = jest.fn();
    await show({ onAccept });
    await fireEvent.press(screen.getByRole("button", { name: "Agree and continue" }));
    expect(onAccept).toHaveBeenCalledTimes(1);
  });
});

describe("the consent kept on the phone", () => {
  it("counts only for the current wording", () => {
    useConsent.setState({ acceptedVersion: null, acceptedAtMs: null });
    expect(hasConsent(useConsent.getState())).toBe(false);
    useConsent.getState().accept(5);
    expect(useConsent.getState()).toMatchObject({
      acceptedVersion: CONSENT_VERSION,
      acceptedAtMs: 5,
    });
    expect(hasConsent(useConsent.getState())).toBe(true);
    expect(hasConsent({ acceptedVersion: "0" })).toBe(false);
  });
});
