import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { roomContent } from "@/rooms/room-content";
import { GeneratingScreen } from "@/screens/generating";
import { useRooms } from "@/state/rooms";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function GeneratingRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  if (!room) return <Redirect href="/" />;
  return (
    <GeneratingScreen
      roomId={room}
      onDone={() => {
        // The room's card on My home now shows its designs.
        const content = roomContent(room);
        const still = content.looks[1]?.still ?? content.looks[0]?.still;
        if (still) useRooms.getState().setRoomDesigns(room, content.looks.length, still);
        router.replace({ pathname: "/reveal", params: { room } });
      }}
    />
  );
}
