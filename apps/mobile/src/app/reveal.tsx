import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { roomContent } from "@/rooms/room-content";
import { RevealScreen } from "@/screens/reveal";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function RevealRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  if (!room) return <Redirect href="/" />;
  const content = roomContent(room);
  // Nothing to reveal yet: the room screen says it is being prepared.
  if (!content) return <Redirect href={{ pathname: "/room/[id]", params: { id: room } }} />;
  return (
    <RevealScreen
      content={content}
      // The reveal gives way to the room: back from there is My home.
      onOpenRoom={() => router.replace({ pathname: "/room/[id]", params: { id: room } })}
    />
  );
}
