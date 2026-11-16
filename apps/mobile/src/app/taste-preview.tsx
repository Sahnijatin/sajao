// Dev-only preview of taste onboarding. The root layout guards this route.
import { useRouter } from "expo-router";
import { TasteScreen } from "@/screens/taste";

export default function TastePreviewRoute() {
  const router = useRouter();
  return <TasteScreen onDone={() => router.back()} />;
}
