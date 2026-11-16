import { useTheme } from "@sajao/ui";
import { DeviceMotion } from "expo-sensors";
import { useCallback, useEffect, useMemo, useReducer } from "react";
import type { AnalysedFrame } from "./scan-camera";
import { INITIAL_SCAN, rollFromGravity, rotationRateDegrees, scanReducer } from "./scan-session";

const MOTION_INTERVAL_MS = 100;

/** Scan state driven by analysed camera frames and the phone's motion sensors. */
export function useScanSession(active: boolean) {
  const { tier } = useTheme();
  const reducer = useMemo(() => scanReducer(tier), [tier]);
  const [state, dispatch] = useReducer(reducer, INITIAL_SCAN);

  useEffect(() => {
    if (!active) return;
    DeviceMotion.setUpdateInterval(MOTION_INTERVAL_MS);
    const subscription = DeviceMotion.addListener((reading) => {
      const gravity = reading.accelerationIncludingGravity;
      const rate = reading.rotationRate;
      dispatch({
        type: "motion",
        // expo-sensors reports rotation rate in degrees per second already.
        rotationRate: rate ? Math.hypot(rate.alpha, rate.beta, rate.gamma) : 0,
        rollDegrees: gravity ? rollFromGravity(gravity) : 0,
      });
    });
    return () => subscription.remove();
  }, [active]);

  const onFrame = useCallback((frame: AnalysedFrame) => dispatch({ type: "frame", ...frame }), []);
  const scanAnyway = useCallback(() => dispatch({ type: "scanAnyway" }), []);

  return { state, onFrame, scanAnyway };
}

// Kept for sensors that report radians per second.
export { rotationRateDegrees };
