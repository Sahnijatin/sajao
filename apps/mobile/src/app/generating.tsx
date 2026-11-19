import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useMemo } from "react";
import { afterMeasured } from "@/rooms/flow";
import { roomContent } from "@/rooms/room-content";
import { roomGeneration } from "@/rooms/room-source";
import { GeneratingScreen } from "@/screens/generating";
import { useRooms } from "@/state/rooms";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function GeneratingRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  // With a server, the stages are the room's real job. Designs are asked for
  // separately, so the real stages stop once the room is measured.
  const real = useMemo(() => roomGeneration(), []);
  if (!room) return <Redirect href="/" />;
  const toRoom = { pathname: "/room/[id]", params: { id: room } } as const;
  // A scan of several areas stops once to ask which one to redesign.
  const askArea = () => {
    const areas = roomContent(room)?.areas.length ?? 0;
    const chosen = Boolean(
      useRooms.getState().rooms.find((each) => each.id === room)?.redesignAreaId,
    );
    return afterMeasured({ areas, chosen }) === "areas";
  };
  if (real) {
    return (
      <GeneratingScreen
        roomId={room}
        source={real}
        designs={false}
        onDone={() =>
          router.replace(
            askArea() ? { pathname: "/areas", params: { room, next: "room" } } : toRoom,
          )
        }
        onLeave={() => router.dismissTo("/")}
      />
    );
  }
  // No server in this build: nothing is being worked on, so the room screen
  // says plainly that the room is not ready yet. A sample is never shown as
  // someone's room.
  return <Redirect href={toRoom} />;
}
