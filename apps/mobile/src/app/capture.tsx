import { useRouter } from "expo-router";
import { startCaptureUpload } from "@/capture/package/start-upload";
import { CaptureScreen } from "@/screens/capture";

export default function CaptureRoute() {
  const router = useRouter();
  // Choosing gallery photos arrives with its own task.
  return (
    <CaptureScreen
      onClose={() => router.back()}
      onDone={() => router.back()}
      // The upload runs in the background and resumes after an interruption.
      onCaptured={(capture, device) => void startCaptureUpload(capture, device)}
      onUsePhotos={() => router.back()}
    />
  );
}
