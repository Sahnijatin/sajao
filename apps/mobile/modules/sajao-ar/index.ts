// JavaScript side of the AR scan module. Safe to import anywhere: when the
// native module is missing (an older build, tests, the web) capabilities say
// AR is unavailable and the capture screen keeps the 2D scan.
import { requireNativeView, requireOptionalNativeModule } from "expo";
import type { ComponentType } from "react";
import type { NativeSyntheticEvent, StyleProp, ViewStyle } from "react-native";

export interface ArCapabilities {
  platform: "ios" | "android" | "none";
  arSupported: boolean;
  lidar: boolean;
  depth: boolean;
}

export type ArTrackingName = "initializing" | "normal" | "limited" | "notAvailable";

export interface ArStatusEvent {
  tracking: ArTrackingName;
  lidar: boolean;
  planes: number;
  meshTriangles: number;
  featurePoints: number;
  mappedPoints: number;
  /** Mean camera image brightness, 0 to 255. */
  brightness: number;
  /** iOS: lumens, about 1000 in a well-lit room. Android: average pixel intensity times 1000. */
  ambientIntensity: number;
  detector: boolean;
  labels: number;
  /** Running totals for the debug overlay: AR camera frames seen since the view started. */
  frames?: number;
  /** Detector runs finished. */
  detectorRuns?: number;
  /** Frames due for the detector while it was still busy. */
  detectorSkipped?: number;
  /** How long the latest detector run took, in milliseconds. */
  detectorMs?: number;
  /** Detections returned so far, and how many were placed in the room. */
  detectionsFound?: number;
  detectionsPlaced?: number;
  /** Placed detections by how they were placed, for example "floor 12 plane 3 points 0 size 40". */
  placedBy?: string;
  /** Why the detector failed to load; empty when it loaded. */
  detectorError?: string;
}

export interface ArPoseEvent {
  yaw: number;
  pitch: number;
  x: number;
  y: number;
  z: number;
  tracking: ArTrackingName;
}

export interface ArDetectionEvent {
  detections: {
    detectorClass: string;
    score: number;
    world?: { x: number; y: number; z: number };
    /** The plane the ray through the box centre meets. */
    surface?: "wall" | "floor" | "ceiling" | "raised" | "none";
    /** Metres from the object point to that plane along the ray. */
    gap?: number;
    /** Metres from the camera to the object point. */
    range?: number;
    /** How the point was found: floor, plane, points or size. */
    placedBy?: "floor" | "plane" | "points" | "size" | "";
    /** The detection's box in the upright camera image, 0 to 1. */
    box?: { x: number; y: number; width: number; height: number };
  }[];
}

export interface ArSurfacesEvent {
  /** Sharpness of the camera frame; any scale, compared within a session. */
  sharpness: number;
  /** Where a 4 by 3 grid of rays from the camera met walls and floor. */
  hits: {
    kind: "wall" | "floor";
    normalYaw: number;
    offset: number;
    x: number;
    y: number;
    z: number;
  }[];
  /** World height of the floor plane, once found. */
  floorY?: number;
}

export interface ArLabelProp {
  id: string;
  text: string;
  x: number;
  y: number;
  z: number;
}

export interface SajaoArViewProps {
  active: boolean;
  torch: boolean;
  lite: boolean;
  reducedMotion: boolean;
  labels: ArLabelProp[];
  onArStatus?: (event: NativeSyntheticEvent<ArStatusEvent>) => void;
  onArPose?: (event: NativeSyntheticEvent<ArPoseEvent>) => void;
  onArDetections?: (event: NativeSyntheticEvent<ArDetectionEvent>) => void;
  onArSurfaces?: (event: NativeSyntheticEvent<ArSurfacesEvent>) => void;
  style?: StyleProp<ViewStyle>;
}

interface NativeArModule {
  getCapabilities(): ArCapabilities;
}

const NativeModule = requireOptionalNativeModule<NativeArModule>("SajaoAr");

const NONE: ArCapabilities = { platform: "none", arSupported: false, lidar: false, depth: false };

export function getArCapabilities(): ArCapabilities {
  try {
    return NativeModule ? { ...NONE, ...NativeModule.getCapabilities() } : NONE;
  } catch {
    return NONE;
  }
}

let cachedView: ComponentType<SajaoArViewProps> | null = null;

/** The native AR view, or null when this build has none. */
export function getArView(): ComponentType<SajaoArViewProps> | null {
  if (!NativeModule) return null;
  if (!cachedView) {
    try {
      cachedView = requireNativeView<SajaoArViewProps>("SajaoAr", "SajaoArView");
    } catch {
      return null;
    }
  }
  return cachedView;
}
