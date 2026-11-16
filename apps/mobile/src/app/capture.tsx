import { useRouter } from "expo-router";
import { useRef } from "react";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { CaptureScreen } from "@/screens/capture";
import { useRooms } from "@/state/rooms";

export default function CaptureRoute() {
  const router = useRouter();
  // The room made from this scan, once it is confirmed on the review.
  const roomId = useRef<string | null>(null);
  // Choosing gallery photos arrives with its own task.
  return (
    <CaptureScreen
      onClose={() => router.back()}
      onDone={() => {
        // A confirmed scan goes on to its designs; anything else returns to My home.
        if (roomId.current) {
          router.replace({ pathname: "/generating", params: { room: roomId.current } });
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
      onUsePhotos={() => router.back()}
    />
  );
}
