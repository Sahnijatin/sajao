import { Redirect, Stack, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { roomName } from "@/rooms/room-card";
import { roomContent } from "@/rooms/room-content";
import { RoomScreen } from "@/screens/room";
import { useRooms, useRoomsLoaded } from "@/state/rooms";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

export default function RoomRoute() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const loaded = useRoomsLoaded();
  const room = useRooms((state) => state.rooms.find((each) => each.id === id));
  if (!loaded) return null;
  // A link to a room that is not on this phone goes to My home.
  if (!room) return <Redirect href="/" />;
  return (
    <>
      <Stack.Screen options={{ title: roomName(room, t) }} />
      <RoomScreen content={roomContent(room.id)} />
    </>
  );
}
