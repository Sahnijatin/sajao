// Sends a finished scan to the server: every file of the capture package
// through the resumable uploader, then one call that registers the capture.
// Both steps are safe to repeat after a lost connection or an app restart:
// finished files are skipped, and the capture id (chosen on the phone when
// the scan started) makes registering twice return the same capture.
//
// Everything that touches the network or the disk is passed in, so this
// logic is tested without a phone.
import type { CapturePackage } from "@sajao/schemas";
import type { MediaKind } from "@/uploads/resumable-upload";
import type { LocalCapture } from "./native-capture";
import {
  type PackageFileKind,
  type PackageUploadDeps,
  uploadCapturePackage,
} from "./upload-package";

/** How each package file is uploaded: the upload kind and its content type. */
export function uploadSpec(kind: PackageFileKind): { kind: MediaKind; contentType: string } {
  switch (kind) {
    case "keyframe":
      return { kind: "photo", contentType: "image/jpeg" };
    case "video":
      return { kind: "video", contentType: "video/mp4" };
    case "sensor_log":
      return { kind: "data", contentType: "application/x-ndjson" };
    case "planes":
      return { kind: "data", contentType: "application/json" };
    case "scene_mesh":
    case "depth":
      return { kind: "data", contentType: "application/octet-stream" };
  }
}

export interface CaptureDeviceInfo {
  platform: "ios" | "android";
  tier: "standard" | "low";
  has_ar: boolean;
}

/** The body of POST /v1/captures. */
export interface RegisterCaptureBody {
  id: string;
  device: CaptureDeviceInfo;
  media: {
    id: string;
    kind: "photo";
    origin: "camera" | "gallery";
    storage_key: string;
    width_px: number;
    height_px: number;
    has_ar_pose: boolean;
  }[];
  package: CapturePackage;
}

/**
 * The register call's body. A Capture needs at least one media item: the
 * first keyframe stands in as a photo, with its real size.
 */
export function registerBody(
  local: LocalCapture,
  uploaded: CapturePackage,
  device: CaptureDeviceInfo,
  mediaId: string,
): RegisterCaptureBody {
  const first = uploaded.keyframes[0];
  // Keyframes are stored in sensor orientation; without intrinsics the size is the camera's usual one.
  const size = first.intrinsics ?? local.firstPictureSize ?? { width_px: 1920, height_px: 1440 };
  return {
    id: local.captureId,
    device,
    media: [
      {
        id: mediaId,
        kind: "photo",
        origin: local.origin ?? "camera",
        storage_key: first.image,
        width_px: size.width_px,
        height_px: size.height_px,
        has_ar_pose: first.pose !== undefined,
      },
    ],
    package: uploaded,
  };
}

export interface CaptureUploadDeps extends PackageUploadDeps {
  /** POST /v1/captures. Resolves once the server has the capture. */
  register(body: RegisterCaptureBody): Promise<void>;
  /** Remembers the media item's id, so a retry registers the same body. */
  mediaId(captureId: string): Promise<string>;
}

/** Upload the package, then register the capture. Safe to call again after any failure. */
export async function uploadAndRegister(
  local: LocalCapture,
  device: CaptureDeviceInfo,
  deps: CaptureUploadDeps,
): Promise<CapturePackage> {
  const uploaded = await uploadCapturePackage(local.captureId, local.state, local.files, deps);
  await deps.register(registerBody(local, uploaded, device, await deps.mediaId(local.captureId)));
  return uploaded;
}

/** A random version 4 UUID. An identifier, not a secret. */
export function uuidV4(random: () => number = Math.random): string {
  const hex = (count: number) =>
    Array.from({ length: count }, () => Math.floor(random() * 16).toString(16)).join("");
  const variant = (8 + Math.floor(random() * 4)).toString(16);
  return `${hex(8)}-${hex(4)}-4${hex(3)}-${variant}${hex(3)}-${hex(12)}`;
}
