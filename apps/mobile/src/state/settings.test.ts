import { DEFAULT_UNITS, migrateSettings, useSettings } from "./settings";

describe("units", () => {
  it("default to feet and inches", () => {
    expect(DEFAULT_UNITS).toBe("ft_in");
    expect(useSettings.getInitialState().units).toBe("ft_in");
  });
});

describe("settings saved by an earlier version", () => {
  it("centimetres saved under the old default move to feet and inches", () => {
    expect(migrateSettings({ language: null, units: "cm" }, 1)).toEqual({
      language: null,
      units: "ft_in",
    });
  });

  it("a saved language and a saved choice of feet and inches are kept", () => {
    expect(migrateSettings({ language: "hi", units: "ft_in" }, 1)).toEqual({
      language: "hi",
      units: "ft_in",
    });
  });

  it("centimetres chosen before version 3 move to feet and inches, which every length shows in", () => {
    expect(migrateSettings({ language: "en", units: "cm" }, 2)).toEqual({
      language: "en",
      units: "ft_in",
    });
  });

  it("copes with nothing saved, or something unreadable", () => {
    expect(migrateSettings(undefined, 0)).toEqual({ language: null, units: "ft_in" });
    expect(migrateSettings({ units: "metres" }, 1)).toEqual({ language: null, units: "ft_in" });
  });
});
