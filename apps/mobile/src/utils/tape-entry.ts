// A value read off a tape, as the person types it: feet and inches, or
// centimetres. Turned into metres for the space profile. Pure.

export type TapeMode = "ft_in" | "cm";

export interface TapeEntry {
  mode: TapeMode;
  feet: string;
  inches: string;
  centimetres: string;
}

const METRES_PER_FOOT = 0.3048;
const METRES_PER_INCH = 0.0254;

/** A typed number, with a comma taken as a decimal point; null when it is not one. */
function number(text: string): number | null {
  const trimmed = text.trim().replace(",", ".");
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/** The entry in metres, or null when it is not a length greater than zero. */
export function tapeMetres(entry: TapeEntry): number | null {
  if (entry.mode === "cm") {
    const cm = number(entry.centimetres);
    return cm !== null && cm > 0 ? cm / 100 : null;
  }
  const feet = entry.feet.trim() === "" ? 0 : number(entry.feet);
  const inches = entry.inches.trim() === "" ? 0 : number(entry.inches);
  if (feet === null || inches === null || inches >= 12) return null;
  const metres = feet * METRES_PER_FOOT + inches * METRES_PER_INCH;
  return metres > 0 ? metres : null;
}
