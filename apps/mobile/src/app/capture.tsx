import { useRouter } from "expo-router";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "react-native";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { afterReview } from "@/rooms/flow";
import { importFromGallery } from "@/rooms/media-import";
import { roomSpaceProfile } from "@/rooms/room-space";
import { CaptureScreen } from "@/screens/capture";
import { useRooms } from "@/state/rooms";
import { useTaste } from "@/state/taste";

const ROUTES = {
  space: "/space",
  taste: "/taste",
  budget: "/budget",
  generating: "/generating",
} as const;

export default function CaptureRoute() {
  const router = useRouter();
  // The room made from this scan, once it is confirmed on the review.
  const roomId = useRef<string | null>(null);
  const { t } = useTranslation();

  // Photos or a video the person already has: picked, then uploaded like a scan.
  const usePhotos = async () => {
    const result = await importFromGallery();
    if (result.status === "problem") {
      Alert.alert(t("import.problemTitle"), t(`import.problems.${result.problem}`));
    } else if (result.status === "imported") {
      router.back();
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
