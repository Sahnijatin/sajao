import { tapeMetres, type TapeEntry } from "./tape-entry";

const entry = (over: Partial<TapeEntry>): TapeEntry => ({
  mode: "ft_in",
  feet: "",
  inches: "",
  centimetres: "",
  ...over,
});

describe("a value read off a tape", () => {
  it("takes feet and inches", () => {
    expect(tapeMetres(entry({ feet: "11", inches: "2" }))).toBeCloseTo(3.4036, 4);
    expect(tapeMetres(entry({ feet: "9" }))).toBeCloseTo(2.7432, 4);
    expect(tapeMetres(entry({ inches: "6" }))).toBeCloseTo(0.1524, 4);
  });

  it("takes centimetres, with a comma or a point", () => {
    expect(tapeMetres(entry({ mode: "cm", centimetres: "340" }))).toBeCloseTo(3.4, 6);
    expect(tapeMetres(entry({ mode: "cm", centimetres: "340,5" }))).toBeCloseTo(3.405, 6);
  });

  it("refuses what is not a length", () => {
    for (const bad of [
      entry({}),
      entry({ feet: "0", inches: "0" }),
      entry({ feet: "ten" }),
      entry({ feet: "9", inches: "12" }),
      entry({ feet: "-2" }),
      entry({ mode: "cm", centimetres: "" }),
      entry({ mode: "cm", centimetres: "0" }),
    ]) {
      expect(tapeMetres(bad)).toBeNull();
    }
  });
});
