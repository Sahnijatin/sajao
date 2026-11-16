import { useRouter } from "expo-router";
import { CaptureScreen } from "@/screens/capture";

export default function CaptureRoute() {
  const router = useRouter();
  // Saving the scan and choosing gallery photos arrive with the upload wiring.
  return (
    <CaptureScreen
      onClose={() => router.back()}
      onDone={() => router.back()}
      onUsePhotos={() => router.back()}
    />
  );
}
