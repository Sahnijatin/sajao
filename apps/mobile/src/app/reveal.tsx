import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { roomContent } from "@/rooms/room-content";
import { RevealScreen } from "@/screens/reveal";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function RevealRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  if (!room) return <Redirect href="/" />;
  return (
    <RevealScreen
      content={roomContent(room)}
      // The reveal gives way to the room: back from there is My home.
      onOpenRoom={() => router.replace({ pathname: "/room/[id]", params: { id: room } })}
    />
  );
}
