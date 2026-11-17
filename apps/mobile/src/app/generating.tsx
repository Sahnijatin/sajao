import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { designsOffered, roomContent } from "@/rooms/room-content";
import { GeneratingScreen } from "@/screens/generating";
import { useRooms } from "@/state/rooms";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function GeneratingRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  if (!room) return <Redirect href="/" />;
  const content = roomContent(room);
  // No real progress to show yet, and no stand-in allowed in this build: the
  // room screen says the room is being prepared.
  if (!content) return <Redirect href={{ pathname: "/room/[id]", params: { id: room } }} />;
  const designs = designsOffered(content.spaceType);
  return (
    <GeneratingScreen
      roomId={room}
      designs={designs}
      onDone={() => {
        // The room's card on My home now shows its designs.
        if (designs) {
          const still = content.looks[1]?.still ?? content.looks[0]?.still;
          if (still) useRooms.getState().setRoomDesigns(room, content.looks.length, still);
        }
        router.replace({ pathname: "/reveal", params: { room } });
      }}
    />
  );
}
