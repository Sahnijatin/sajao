import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { roomContent } from "@/rooms/room-content";
import { RevealScreen } from "@/screens/reveal";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function RevealRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  if (!room) return <Redirect href="/" />;
  // The room screen arrives with its own task; until then this returns to My home.
  return <RevealScreen content={roomContent(room)} onOpenRoom={() => router.dismissTo("/")} />;
}
