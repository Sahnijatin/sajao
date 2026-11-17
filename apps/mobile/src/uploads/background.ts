// Asks the phone to keep an upload going after the person leaves the app.
// Android: a foreground service with a quiet notification holds the app's
// process, so the upload code keeps running. iOS needs nothing here: each
// file is handed to the system's background transfer service as it is sent.
import { requireOptionalNativeModule } from "expo-modules-core";
import { Platform } from "react-native";
import i18n from "@/i18n";

interface UploadServiceModule {
  startUploadService?(title: string, text: string): void;
  stopUploadService?(): void;
}

/** Turn background uploading on or off. Never throws: without it the upload still runs in the app. */
export function keepUploading(on: boolean): void {
  if (Platform.OS !== "android") return;
  try {
    const native = requireOptionalNativeModule<UploadServiceModule>("SajaoAr");
    if (on) {
      native?.startUploadService?.(
        i18n.t("home.upload.notificationTitle"),
        i18n.t("home.upload.notificationText"),
      );
    } else {
      native?.stopUploadService?.();
    }
  } catch {
    // An older build without the service: the upload runs while the app is open.
  }
}
