import { imuReading } from "./imu";
import { IMU_INTERVAL_MS, SENSOR_INTERVAL_MS, sensorDue, sensorInterval } from "./native-capture";

describe("motion sensor log", () => {
  it("writes turn rates and acceleration as the phone reports them", () => {
    expect(
      imuReading({
        rotationRate: { alpha: 1.234, beta: -20.5, gamma: 0 },
        acceleration: { x: 0.01234, y: 0, z: -0.5 },
        accelerationIncludingGravity: { x: 0, y: -9.81, z: 0.2 },
      }),
    ).toEqual({
      source: "imu",
      gyro_alpha: 1.23,
      gyro_beta: -20.5,
      gyro_gamma: 0,
      accel_x: 0.012,
      accel_y: 0,
      accel_z: -0.5,
      gravity_accel_x: 0,
      gravity_accel_y: -9.81,
      gravity_accel_z: 0.2,
    });
  });

  it("writes nothing for an empty reading and skips bad numbers", () => {
    expect(imuReading({})).toBeNull();
    expect(imuReading({ rotationRate: { alpha: Number.NaN, beta: 1, gamma: 2 } })).toEqual({
      source: "imu",
      gyro_beta: 1,
      gyro_gamma: 2,
    });
  });

  it("paces each source on its own: motion readings ten a second, AR poses five", () => {
    expect(sensorInterval("imu")).toBe(IMU_INTERVAL_MS);
    expect(sensorInterval("ar_pose")).toBe(SENSOR_INTERVAL_MS);
    expect(sensorDue(1000, 1100, sensorInterval("imu"))).toBe(true);
    expect(sensorDue(1000, 1100, sensorInterval("ar_pose"))).toBe(false);
    expect(sensorDue(null, 0)).toBe(true);
  });
});
