// JavaScript side of the AR scan module. Safe to import anywhere: when the
// native module is missing (an older build, tests, the web) capabilities say
// AR is unavailable and the capture screen keeps the 2D scan.
import { requireNativeView, requireOptionalNativeModule } from "expo";
import type { ComponentType, RefAttributes } from "react";
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
  /** "loading", "loaded (N ms, ...)" after a self-test, or "error: ...". */
  detectorStatus?: string;
  /** Camera image size the detector and keyframes see, for example "640x480". */
  cameraImage?: string;
  /** Planes by state, for example "tracking 4 paused 1". */
  planeStates?: string;
  /** Coverage hits by source, for example "planes 120 points 40". */
  surfaceHits?: string;
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

/** A keyframe candidate the native view saved: full resolution, sensor orientation. */
export interface ArKeyframeEvent {
  /** Local file of the JPEG. */
  uri: string;
  sharpness: number;
  yaw: number;
  pitch: number;
  /** A depth image was saved with it. */
  depth: boolean;
  /** AR camera pose: +X right, +Y up, -Z forward relative to the stored image. */
  pose: {
    position: { x_m: number; y_m: number; z_m: number };
    rotation: [number, number, number, number];
  };
  /** Of the stored image, in its pixels. */
  intrinsics: {
    fx: number;
    fy: number;
    cx: number;
    cy: number;
    width_px: number;
    height_px: number;
  };
}

/** Files the native view wrote at the end of a capture; null where the phone had none. */
export interface ArCaptureFiles {
  planes: string | null;
  sceneMesh: string | null;
  depth: string | null;
  error?: string;
}

/** Methods on the AR view's ref. */
export interface SajaoArViewRef {
  /** Delete keyframe candidates the app's recorder dropped. */
  discardKeyframes(uris: string[]): Promise<void>;
  /** End the capture: write planes, the LiDAR mesh and depth for these keyframes, in this order (k1, k2, ...). */
  finishCapture(chosen: string[]): Promise<ArCaptureFiles>;
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
  /** Records a capture package while set; empty records nothing. */
  captureId?: string;
  onArKeyframe?: (event: NativeSyntheticEvent<ArKeyframeEvent>) => void;
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

type ArViewComponent = ComponentType<SajaoArViewProps & RefAttributes<SajaoArViewRef>>;

let cachedView: ArViewComponent | null = null;

/** The native AR view, or null when this build has none. */
export function getArView(): ArViewComponent | null {
  if (!NativeModule) return null;
  if (!cachedView) {
    try {
      cachedView = requireNativeView<SajaoArViewProps>("SajaoAr", "SajaoArView") as ArViewComponent;
    } catch {
      return null;
    }
  }
  return cachedView;
}
