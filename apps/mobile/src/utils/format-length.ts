// Lengths are stored in metres everywhere. They are shown in centimetres or
// feet and inches, by the user's choice.
export type LengthUnits = "cm" | "ft_in";

const METRES_PER_INCH = 0.0254;

export function toCentimetres(metres: number): number {
  return Math.round(metres * 100);
}

/** Rounded to the nearest inch, so 0.3 m is 1 ft 0 in, never 0 ft 12 in. */
export function toFeetAndInches(metres: number): { feet: number; inches: number } {
  const totalInches = Math.round(metres / METRES_PER_INCH);
  return { feet: Math.floor(totalInches / 12), inches: totalInches % 12 };
}

type Translate = (key: string, values: Record<string, number>) => string;

export function formatLength(metres: number, units: LengthUnits, t: Translate): string {
  if (units === "cm") return t("length.cm", { value: toCentimetres(metres) });
  return t("length.ftIn", toFeetAndInches(metres));
}
