import { useLocalSearchParams, useRouter } from "expo-router";
import { TasteScreen } from "@/screens/taste";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/**
 * Taste and budget. With a room: the first-time step before that room's
 * designs. Without one: opened from Profile to change the answers.
 */
export default function TasteRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  return (
    <TasteScreen
      onDone={(answers) => {
        useTaste.getState().setAnswers(answers);
        if (room) router.replace({ pathname: "/generating", params: { room } });
        else router.back();
      }}
    />
  );
}
