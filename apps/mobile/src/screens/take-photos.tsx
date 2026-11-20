// Take photos: how a room starts. A short note, the camera held sideways,
// then each photo looked at once ("Happy with the view and lighting?") with
// Retake or Continue. One to three photos make the room.
import { Button, GlassSurface, motion, playHaptic, Text, useTheme } from "@sajao/ui";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { BackHandler, Image, Pressable, ScrollView, StyleSheet, View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useCameraPermission } from "react-native-vision-camera";
import { PhotoCamera, type PhotoCameraHandle } from "@/photos/photo-camera";
import {
  canAddAnother,
  heldSideways,
  MAX_PHOTOS,
  photoSession,
  sessionWith,
  type TakenPhoto,
} from "@/photos/photo-session";
import { preparePhoto, type SavedPhoto } from "@/photos/take-photo";

export interface TakePhotosProps {
  /** The kept photos, one to three, in the order they were taken. */
  onDone: (photos: TakenPhoto[]) => void;
  onClose: () => void;
  /** "Use photos or a video": pictures already on the phone. */
  onUsePhotos: () => void;
  prepare?: (fileUri: string) => Promise<SavedPhoto>;
  /** Photos the room already has, when adding to it; empty for a new room. */
  initialPhotos?: readonly TakenPhoto[];
}

const SHUTTER = 76;

export function TakePhotosScreen({
  onDone,
  onClose,
  onUsePhotos,
  prepare = preparePhoto,
  initialPhotos = [],
}: TakePhotosProps) {
  const [session, dispatch] = useReducer(photoSession, initialPhotos, sessionWith);
  const { current, kept } = session;

  useEffect(() => {
    if (current.step === "done") onDone(session.kept);
  }, [current.step, onDone, session.kept]);

  // Android back steps back through the flow before it leaves.
  useEffect(() => {
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      if (current.step === "review") dispatch({ type: "retake" });
      else onClose();
      return true;
    });
    return () => subscription.remove();
  }, [current.step, onClose]);

  if (current.step === "note") {
    return (
      <PhotoNote
        onStart={() => dispatch({ type: "start" })}
        onUsePhotos={onUsePhotos}
        onClose={onClose}
      />
    );
  }
  if (current.step === "review") {
    return (
      <PhotoReview
        photo={current.photo}
        number={(current.replacing ?? kept.length) + 1}
        onRetake={() => dispatch({ type: "retake" })}
        onContinue={() => dispatch({ type: "continue" })}
      />
    );
  }
  if (current.step === "photos") {
    return (
      <AllPhotos
        photos={kept}
        canAddAnother={canAddAnother(session)}
        onRetakeAt={(index) => dispatch({ type: "retakeAt", index })}
        onAddAnother={() => dispatch({ type: "addAnother" })}
        onUse={() => dispatch({ type: "finish" })}
      />
    );
  }
  if (current.step === "camera") {
    return (
      <PhotoTaking
        number={(current.replacing ?? kept.length) + 1}
        prepare={prepare}
        onTaken={(photo) => dispatch({ type: "taken", photo })}
        onClose={onClose}
        onUsePhotos={onUsePhotos}
      />
    );
  }
  return null;
}

function PhotoNote({
  onStart,
  onUsePhotos,
  onClose,
}: {
  onStart: () => void;
  onUsePhotos: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const { colors, spacing } = tokens;
  const insets = useSafeAreaInsets();
  const fade = duration(motion.ease.durationMs);
  const entering =
    fade > 0 ? FadeIn.duration(fade).easing(Easing.bezier(...motion.ease.bezier)) : undefined;
  const tips = [t("photos.note.floor"), t("photos.note.private"), t("photos.note.people")];

  return (
    <ScrollView
      testID="photos-note"
      style={{ flex: 1, backgroundColor: colors.canvas }}
      contentContainerStyle={{
        flexGrow: 1,
        justifyContent: "center",
        padding: spacing.gutter,
        paddingTop: insets.top + spacing.gutter,
        paddingBottom: insets.bottom + spacing.sheetBottom,
        gap: spacing.sheetBottom,
      }}
    >
      <Animated.View entering={entering} style={{ gap: spacing.sheetBottom }}>
        <View style={{ gap: spacing.md }}>
          <Text variant="title" accessibilityRole="header">
            {t("photos.note.title")}
          </Text>
          <Text tone="secondary">{t("photos.note.body")}</Text>
        </View>
        <View style={{ gap: spacing.lg }}>
          {tips.map((tip, index) => (
            <View key={tip} style={{ flexDirection: "row", gap: spacing.lg }}>
              <Text variant="label" tone="accent">
                {index + 1}
              </Text>
              <Text style={{ flex: 1 }}>{tip}</Text>
            </View>
          ))}
        </View>
        <View style={{ gap: spacing.lg }}>
          <Button label={t("photos.note.start")} onPress={onStart} />
          <Button label={t("home.usePhotos")} variant="outline" onPress={onUsePhotos} />
          <Button label={t("capture.close")} variant="ghost" size="small" onPress={onClose} />
        </View>
      </Animated.View>
    </ScrollView>
  );
}

function PhotoTaking({
  number,
  prepare,
  onTaken,
  onClose,
  onUsePhotos,
}: {
  number: number;
  prepare: (fileUri: string) => Promise<SavedPhoto>;
  onTaken: (photo: TakenPhoto) => void;
  onClose: () => void;
  onUsePhotos: () => void;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const insets = useSafeAreaInsets();
  const permission = useCameraPermission();
  const camera = useRef<PhotoCameraHandle>(null);
  const [rotation, setRotation] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<"notLandscape" | "failed" | null>(null);
  const sideways = heldSideways(rotation);

  // A selection tick as the phone turns sideways: ready to take.
  const wasSideways = useRef(false);
  useEffect(() => {
    if (sideways && !wasSideways.current) void playHaptic("levelReached");
    wasSideways.current = sideways;
    if (sideways) setProblem(null);
  }, [sideways]);

  const shoot = useCallback(async () => {
    if (!sideways || busy || !camera.current) return;
    setBusy(true);
    setProblem(null);
    try {
      void playHaptic("cornerCaptured");
      const file = await camera.current.takePhoto();
      const saved = await prepare(file);
      if (saved.ok) onTaken(saved.photo);
      else setProblem(saved.problem);
    } catch {
      setProblem("failed");
    } finally {
      setBusy(false);
    }
  }, [busy, onTaken, prepare, sideways]);

  if (!permission.hasPermission) {
    return (
      <View
        testID="photos-permission"
        style={{
          flex: 1,
          justifyContent: "center",
          gap: spacing.gutter,
          padding: spacing.gutter,
          backgroundColor: colors.canvas,
        }}
      >
        <Text variant="title">{t("photos.permissionTitle")}</Text>
        <Text tone="secondary">{t("photos.permissionBody")}</Text>
        {permission.canRequestPermission ? (
          <Button
            label={t("capture.permissionAllow")}
            onPress={() => void permission.requestPermission()}
          />
        ) : null}
        <Button label={t("home.usePhotos")} variant="outline" onPress={onUsePhotos} />
        <Button label={t("capture.close")} variant="ghost" size="small" onPress={onClose} />
      </View>
    );
  }

  // The hint turns with the phone, so it reads upright when held sideways.
  const turn = sideways && rotation !== null ? [{ rotate: `${rotation}deg` }] : [];
  const hint = problem
    ? t(`photos.camera.problems.${problem}`)
    : sideways
      ? t("photos.camera.ready")
      : t("photos.camera.turn");

  return (
    <View testID="photos-camera" style={{ flex: 1, backgroundColor: colors.ink }}>
      <PhotoCamera ref={camera} active onRotation={setRotation} style={StyleSheet.absoluteFill} />
      <View
        style={[StyleSheet.absoluteFill, { justifyContent: "center", alignItems: "center" }]}
        pointerEvents="none"
      >
        <View style={{ transform: turn, maxWidth: 320 }}>
          <GlassSurface
            tone="dark"
            style={{
              paddingHorizontal: spacing.gutter,
              paddingVertical: spacing.lg,
              gap: spacing.xs,
            }}
          >
            <Text
              testID="photos-hint"
              tone="onDark"
              variant="bodyStrong"
              accessibilityLiveRegion="polite"
            >
              {hint}
            </Text>
            <Text tone="onDark" variant="caption">
              {t("photos.camera.count", { number, most: MAX_PHOTOS })}
            </Text>
          </GlassSurface>
        </View>
      </View>
      <View
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: insets.bottom + spacing.sheetBottom,
          alignItems: "center",
        }}
      >
        <Pressable
          testID="photos-shutter"
          accessibilityRole="button"
          accessibilityLabel={t("photos.camera.shutter")}
          accessibilityState={{ disabled: !sideways || busy }}
          disabled={!sideways || busy}
          onPress={() => void shoot()}
          style={{
            width: SHUTTER,
            height: SHUTTER,
            borderRadius: SHUTTER / 2,
            borderWidth: 4,
            borderColor: colors.onAccent,
            alignItems: "center",
            justifyContent: "center",
            opacity: sideways && !busy ? 1 : 0.4,
          }}
        >
          <View
            style={{
              width: SHUTTER - 16,
              height: SHUTTER - 16,
              borderRadius: (SHUTTER - 16) / 2,
              backgroundColor: colors.onAccent,
            }}
          />
        </Pressable>
      </View>
      <View style={{ position: "absolute", top: insets.top + spacing.lg, left: spacing.gutter }}>
        <Pressable accessibilityRole="button" onPress={onClose} hitSlop={spacing.lg}>
          <GlassSurface
            tone="dark"
            style={{
              borderRadius: 999,
              paddingHorizontal: spacing.gutter,
              paddingVertical: spacing.md,
            }}
          >
            <Text tone="onDark" variant="label">
              {t("capture.close")}
            </Text>
          </GlassSurface>
        </Pressable>
      </View>
    </View>
  );
}

function PhotoReview({
  photo,
  number,
  onRetake,
  onContinue,
}: {
  photo: TakenPhoto;
  number: number;
  onRetake: () => void;
  onContinue: () => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const { colors, spacing, radius } = tokens;
  const insets = useSafeAreaInsets();
  const fade = duration(motion.ease.durationMs);
  const entering =
    fade > 0 ? FadeIn.duration(fade).easing(Easing.bezier(...motion.ease.bezier)) : undefined;

  return (
    <ScrollView
      testID="photos-review"
      style={{ flex: 1, backgroundColor: colors.canvas }}
      contentContainerStyle={{
        flexGrow: 1,
        justifyContent: "center",
        padding: spacing.gutter,
        paddingTop: insets.top + spacing.gutter,
        paddingBottom: insets.bottom + spacing.sheetBottom,
        gap: spacing.sheetBottom,
      }}
    >
      <Animated.View entering={entering}>
        <Image
          testID="photos-review-image"
          source={{ uri: photo.uri }}
          accessibilityLabel={t("photos.review.picture", { number })}
          style={{
            width: "100%",
            aspectRatio: photo.widthPx / photo.heightPx,
            borderRadius: radius.card,
            backgroundColor: colors.sand,
          }}
        />
      </Animated.View>
      <Text variant="heading" accessibilityRole="header">
        {t("photos.review.question")}
      </Text>
      <View style={{ gap: spacing.lg }}>
        <View style={{ flexDirection: "row", gap: spacing.lg }}>
          <View style={{ flex: 1 }}>
            <Button label={t("photos.review.retake")} variant="outline" onPress={onRetake} />
          </View>
          <View style={{ flex: 1 }}>
            <Button label={t("photos.review.continue")} onPress={onContinue} />
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

/** Every photo taken, each with its own Retake, before they make the room. */
function AllPhotos({
  photos,
  canAddAnother: offerAnother,
  onRetakeAt,
  onAddAnother,
  onUse,
}: {
  photos: readonly TakenPhoto[];
  canAddAnother: boolean;
  onRetakeAt: (index: number) => void;
  onAddAnother: () => void;
  onUse: () => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const { colors, spacing, radius } = tokens;
  const insets = useSafeAreaInsets();
  const fade = duration(motion.ease.durationMs);
  const entering =
    fade > 0 ? FadeIn.duration(fade).easing(Easing.bezier(...motion.ease.bezier)) : undefined;
  return (
    <ScrollView
      testID="photos-all"
      style={{ flex: 1, backgroundColor: colors.canvas }}
      contentContainerStyle={{
        padding: spacing.gutter,
        paddingTop: insets.top + spacing.gutter,
        paddingBottom: insets.bottom + spacing.sheetBottom,
        gap: spacing.sheetBottom,
      }}
    >
      <Text variant="title" accessibilityRole="header">
        {t("photos.all.title", { count: photos.length })}
      </Text>
      {photos.map((photo, index) => (
        <Animated.View key={photo.uri} entering={entering} style={{ gap: spacing.md }}>
          <Image
            testID={`photos-all-${index + 1}`}
            source={{ uri: photo.uri }}
            accessibilityLabel={t("photos.review.picture", { number: index + 1 })}
            style={{
              width: "100%",
              aspectRatio: photo.widthPx / photo.heightPx,
              borderRadius: radius.card,
              backgroundColor: colors.sand,
            }}
          />
          <Button
            label={t("photos.all.retake", { number: index + 1 })}
            variant="outline"
            size="small"
            onPress={() => onRetakeAt(index)}
          />
        </Animated.View>
      ))}
      <View style={{ gap: spacing.lg }}>
        <Button
          label={t("photos.all.use", { count: photos.length })}
          onPress={() => {
            void playHaptic("roomAdded");
            onUse();
          }}
        />
        {offerAnother ? (
          <Button
            label={t("photos.review.another", { number: photos.length + 1, most: MAX_PHOTOS })}
            variant="ghost"
            size="small"
            onPress={onAddAnother}
          />
        ) : null}
      </View>
    </ScrollView>
  );
}
