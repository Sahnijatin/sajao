// One motion sensor reading as a sensor log line: turn rates, acceleration
// with and without gravity, as the phone reports them. The server uses them
// with the video and AR poses; nothing here is interpreted on the phone.
import type { RawMotion } from "../pose";

const round = (value: number, digits: number) => {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
};

/** The log line for a reading, or null when the phone reported nothing usable. */
export function imuReading(reading: RawMotion): Record<string, number | string> | null {
  const line: Record<string, number | string> = { source: "imu" };
  const put = (
    prefix: string,
    digits: number,
    values: Record<string, number> | null | undefined,
  ) => {
    if (!values) return;
    for (const [axis, value] of Object.entries(values)) {
      if (typeof value === "number" && Number.isFinite(value)) {
        line[`${prefix}_${axis}`] = round(value, digits);
      }
    }
  };
  // Degrees per second about the phone's axes, labelled as the platform reports them.
  put("gyro", 2, reading.rotationRate);
  // Metres per second squared, without and with gravity.
  put("accel", 3, reading.acceleration);
  put("gravity_accel", 3, reading.accelerationIncludingGravity);
  return Object.keys(line).length > 1 ? line : null;
}
