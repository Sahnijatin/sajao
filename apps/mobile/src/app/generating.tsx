import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useMemo } from "react";
import { afterMeasured } from "@/rooms/flow";
import { designsOffered, roomContent, sampleContent } from "@/rooms/room-content";
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
  const content = sampleContent();
  // No server and no stand-in allowed in this build: the room screen says
  // the room is being prepared.
  if (!content) return <Redirect href={toRoom} />;
  const designs = designsOffered(content.spaceType);
  return (
    <GeneratingScreen
      roomId={room}
      designs={designs}
      onLeave={() => router.dismissTo("/")}
      onDone={() => {
        // The room's card on My home now shows its designs.
        if (designs) {
          const still = content.looks[1]?.still ?? content.looks[0]?.still;
          if (still) useRooms.getState().setRoomDesigns(room, content.looks.length, still);
        }
        router.replace(
          askArea()
            ? { pathname: "/areas", params: { room, next: "reveal" } }
            : { pathname: "/reveal", params: { room } },
        );
      }}
    />
  );
}
