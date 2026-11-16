import { useRouter } from "expo-router";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { CaptureScreen } from "@/screens/capture";
import { useRooms } from "@/state/rooms";

export default function CaptureRoute() {
  const router = useRouter();
  // Choosing gallery photos arrives with its own task.
  return (
    <CaptureScreen
      onClose={() => router.back()}
      onDone={() => router.back()}
      // The upload runs in the background and resumes after an interruption.
      onCaptured={(capture, device) => {
        // The scan becomes a room on My home at once; its designs arrive later.
        useRooms.getState().addRoomForCapture(capture.captureId);
        void startCaptureUpload(capture, device);
      }}
      onUsePhotos={() => router.back()}
    />
  );
}
