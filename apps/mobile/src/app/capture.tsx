import { useRouter } from "expo-router";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Platform } from "react-native";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { afterReview } from "@/rooms/flow";
import { roomSpaceProfile } from "@/rooms/room-space";
import { CaptureScreen } from "@/screens/capture";
import { useCaptureStore } from "@/state/capture";
import { useRooms } from "@/state/rooms";
import { useTaste } from "@/state/taste";

const ROUTES = { space: "/space", taste: "/taste", generating: "/generating" } as const;

export default function CaptureRoute() {
  const router = useRouter();
  // The room made from this scan, once it is confirmed on the review.
  const roomId = useRef<string | null>(null);
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
      // Imported photos or a video become a room on My home, like a scan.
      useRooms.getState().addRoomForCapture(picked.capture.captureId);
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
      onDone={() => {
        // A confirmed scan goes on: what we found, then taste the first time,
        // then its designs. Anything else returns to My home.
        if (roomId.current) {
          const step = afterReview({
            hasSpaceProfile: roomSpaceProfile(roomId.current) !== null,
            hasTaste: useTaste.getState().answers !== null,
          });
          router.replace({ pathname: ROUTES[step], params: { room: roomId.current } });
        } else {
          router.back();
        }
      }}
      // The upload runs in the background and resumes after an interruption.
      onCaptured={(capture, device) => {
        // The scan becomes a room on My home at once; its designs arrive later.
        roomId.current = useRooms.getState().addRoomForCapture(capture.captureId).id;
        void startCaptureUpload(capture, device);
      }}
      onUsePhotos={() => void usePhotos()}
    />
  );
}
