// My home: the rooms you have added, newest first, and one way in to a new
// one. Before the first room it shows what the app does in one picture, one
// line and one button. Scanning is only ever reached from "Add a room".
import { Button, motion, playHaptic, Text, useTheme } from "@sajao/ui";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ScrollView, View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";
import { SafeAreaView } from "react-native-safe-area-context";
import { BeforeAfter } from "@/components/before-after";
import { UploadStatus } from "@/components/upload-status";
import { importOffered } from "@/rooms/media-import";
import { RoomCard } from "@/rooms/room-card";
import { sortRooms } from "@/rooms/rooms";
import { samplesAllowed } from "@/rooms/samples";
import { useRooms, useRoomsLoaded } from "@/state/rooms";

/** Each card follows the one above by this much as the list appears. */
const STAGGER_MS = 60;

export function HomeScreen() {
  const { t } = useTranslation();
  const router = useRouter();
  const { tokens, duration } = useTheme();
  const { colors, spacing } = tokens;
  const loaded = useRoomsLoaded();
  const saved = useRooms((state) => state.rooms);
  const rooms = useMemo(() => sortRooms(saved), [saved]);
  const addRoom = () => router.push("/capture");
  // The second way in: photos or a video already on the phone.
  const usePhotos = importOffered() ? (
    <Button
      label={t("home.usePhotos")}
      variant="ghost"
      size="small"
      onPress={() => router.push("/import")}
    />
  ) : null;

  // A soft tick as a new room's card lands, when you come back from adding it.
  const seen = useRef<number | null>(null);
  useFocusEffect(
    useCallback(() => {
      if (!loaded) return;
      if (seen.current !== null && rooms.length > seen.current) void playHaptic("roomAdded");
      seen.current = rooms.length;
    }, [loaded, rooms.length]),
  );

  const fade = duration(motion.ease.durationMs);
  const entering = (index: number) =>
    fade > 0
      ? FadeIn.duration(fade)
          .delay(index * STAGGER_MS)
          .easing(Easing.bezier(...motion.ease.bezier))
      : undefined;
  const nowMs = Date.now();

  // Nothing but the canvas until the saved rooms are read: the empty state
  // must not flash in front of someone who has rooms.
  if (!loaded) {
    return <View testID="home-loading" style={{ flex: 1, backgroundColor: colors.canvas }} />;
  }

  if (rooms.length === 0) {
    return (
      <SafeAreaView edges={["top"]} style={{ flex: 1, backgroundColor: colors.canvas }}>
        <ScrollView
          // The tab bar sits over the page on iOS: the list ends above it.
          contentInsetAdjustmentBehavior="automatic"
          contentContainerStyle={{
            flexGrow: 1,
            padding: spacing.gutter,
            paddingBottom: spacing.sheetBottom,
            gap: spacing.sheetBottom,
          }}
        >
          {/* The drawn before and after is a stand-in. A store build waits for the real pair. */}
          {samplesAllowed() ? (
            <Animated.View entering={entering(0)} style={{ flex: 1, minHeight: 320 }}>
              <BeforeAfter
                before={{ kind: "placeholder", look: "before" }}
                after={{ kind: "placeholder", look: "after" }}
                style={{ flex: 1 }}
              />
            </Animated.View>
          ) : (
            <View style={{ flex: 1 }} />
          )}
          <Animated.View entering={entering(1)} style={{ gap: spacing.sheetBottom }}>
            <Text variant="title" accessibilityRole="header">
              {t("home.empty.line")}
            </Text>
            <View style={{ gap: spacing.lg }}>
              <Button label={t("home.addRoom")} onPress={addRoom} />
              {usePhotos}
            </View>
          </Animated.View>
          <UploadStatus />
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView edges={["top"]} style={{ flex: 1, backgroundColor: colors.canvas }}>
      <ScrollView
        // The tab bar sits over the page on iOS: the last card ends above it.
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={{
          padding: spacing.gutter,
          paddingBottom: spacing.sheetBottom,
          gap: spacing.sheetBottom,
        }}
      >
        <Text variant="title" accessibilityRole="header">
          {t("home.title")}
        </Text>
        <UploadStatus />
        {rooms.map((room, index) => (
          <Animated.View key={room.id} entering={entering(index)}>
            <RoomCard
              room={room}
              nowMs={nowMs}
              onPress={() => router.push({ pathname: "/room/[id]", params: { id: room.id } })}
            />
          </Animated.View>
        ))}
        <View style={{ gap: spacing.lg }}>
          <Button label={t("home.addRoom")} variant="outline" onPress={addRoom} />
          {usePhotos}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
