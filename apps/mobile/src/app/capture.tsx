import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";
import { Alert, Platform } from "react-native";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { CaptureScreen } from "@/screens/capture";
import { useCaptureStore } from "@/state/capture";

export default function CaptureRoute() {
  const router = useRouter();
  const { t } = useTranslation();

  // Photos or a video the person already has: picked, then uploaded like a scan.
  const usePhotos = async () => {
    try {
      const { pickFromGallery } = await import("@/import/pick");
      const picked = await pickFromGallery();
      if (picked.state === "cancelled") return;
      if (picked.state === "problem") {
        Alert.alert(t("import.problemTitle"), t(`import.problems.${picked.problem}`));
        return;
      }
      useCaptureStore.getState().setLast(picked.capture);
      void startCaptureUpload(picked.capture, {
        platform: Platform.OS === "ios" ? "ios" : "android",
        tier: "standard",
        has_ar: false,
      });
      router.back();
    } catch {
      Alert.alert(t("import.problemTitle"), t("import.problems.failed"));
    }
  };

  return (
    <CaptureScreen
      onClose={() => router.back()}
      onDone={() => router.back()}
      // The upload runs in the background and resumes after an interruption.
      onCaptured={(capture, device) => void startCaptureUpload(capture, device)}
      onUsePhotos={() => void usePhotos()}
    />
  );
}
