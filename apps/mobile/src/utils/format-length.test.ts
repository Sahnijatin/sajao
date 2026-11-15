import { formatLength, toCentimetres, toFeetAndInches } from "./format-length";

const t = (key: string, values: Record<string, number>) => `${key} ${JSON.stringify(values)}`;

describe("length formatting", () => {
  it("shows centimetres as whole numbers", () => {
    expect(toCentimetres(3.4)).toBe(340);
    expect(toCentimetres(0.826)).toBe(83);
  });

  it("shows feet and inches rounded to the nearest inch", () => {
    expect(toFeetAndInches(3.4)).toEqual({ feet: 11, inches: 2 });
    expect(toFeetAndInches(0.3048)).toEqual({ feet: 1, inches: 0 });
    expect(toFeetAndInches(0)).toEqual({ feet: 0, inches: 0 });
  });

  it("never shows 12 inches: it carries into the next foot", () => {
    // 0.3 m is 11.81 in, which rounds to 12 in, shown as 1 ft 0 in.
    expect(toFeetAndInches(0.3)).toEqual({ feet: 1, inches: 0 });
    for (let cm = 0; cm <= 1000; cm += 1) {
      expect(toFeetAndInches(cm / 100).inches).toBeLessThan(12);
    }
  });

  it("uses the string for the chosen units", () => {
    expect(formatLength(3.4, "cm", t)).toBe('length.cm {"value":340}');
    expect(formatLength(3.4, "ft_in", t)).toBe('length.ftIn {"feet":11,"inches":2}');
  });
});
