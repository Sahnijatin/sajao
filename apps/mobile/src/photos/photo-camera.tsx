// The camera for Take photos: preview plus a still-photo output. This file is
// the only place Take photos touches the camera library. Orientation comes
// from the phone itself, so a photo taken sideways is stored sideways even
// though the app's screens stay upright.
import { forwardRef, useImperativeHandle } from "react";
import type { StyleProp, ViewStyle } from "react-native";
import { Camera, useCameraDevice, usePhotoOutput } from "react-native-vision-camera";
import { fileUri } from "./take-photo";

export interface PhotoCameraHandle {
  /** Take a photo; resolves with its file. */
  takePhoto(): Promise<string>;
}

export interface PhotoCameraProps {
  active: boolean;
  /** Degrees the controls must turn by to read upright. */
  onRotation: (degrees: number) => void;
  style?: StyleProp<ViewStyle>;
}

export const PhotoCamera = forwardRef<PhotoCameraHandle, PhotoCameraProps>(function PhotoCamera(
  { active, onRotation, style },
  ref,
) {
  const device = useCameraDevice("back");
  const photoOutput = usePhotoOutput({ qualityPrioritization: "quality" });

  useImperativeHandle(
    ref,
    () => ({
      async takePhoto() {
        const file = await photoOutput.capturePhotoToFile({ flashMode: "off" }, {});
        return fileUri(file.filePath);
      },
    }),
    [photoOutput],
  );

  if (!device) return null;
  return (
    <Camera
      style={style}
      device={device}
      isActive={active}
      outputs={[photoOutput]}
      orientationSource="device"
      onUIRotationChanged={onRotation}
      resizeMode="cover"
    />
  );
});
