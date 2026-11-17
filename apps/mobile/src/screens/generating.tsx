// While a room is being worked on: three stages in plain words, one after
// the other, each ticking off as it finishes. There is no bar to watch run
// out; when the last stage is done the screen hands straight on to the reveal.
import { motion, playHaptic, Text, useTheme } from "@sajao/ui";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import Animated, { cubicBezier } from "react-native-reanimated";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  type GenerationSource,
  type GenerationStage,
  stagesFor,
  useGeneration,
} from "@/rooms/generation";

/** The last tick stays in view for this long before the reveal. */
export const HANDOVER_MS = 700;

const breathe = { from: { opacity: 0.35 }, to: { opacity: 1 } };
const easing = cubicBezier(...motion.ease.bezier);

type StageState = "done" | "current" | "next";

function StageRow({ stage, state }: { stage: GenerationStage; state: StageState }) {
  const { t } = useTranslation();
  const { tokens, reducedMotion, duration } = useTheme();
  const { colors, spacing, radius } = tokens;
  const dot = spacing.xl;
  return (
    <View
      testID={`stage-${stage}`}
      accessible
      accessibilityLabel={t(`generating.stages.${stage}`)}
      accessibilityState={{ busy: state === "current", checked: state === "done" }}
      style={{ flexDirection: "row", alignItems: "center", gap: spacing.gutter }}
    >
      <Animated.View
        style={[
          {
            width: dot,
            height: dot,
            borderRadius: radius.pill,
            backgroundColor:
              state === "done" ? colors.success : state === "current" ? colors.accent : colors.sand,
            transitionProperty: "backgroundColor",
            transitionDuration: duration(motion.ease.durationMs),
            transitionTimingFunction: easing,
          },
          // The stage in hand breathes slowly; with reduced motion it stands still.
          state === "current" && !reducedMotion
            ? {
                animationName: breathe,
                animationDuration: 1100,
                animationIterationCount: "infinite",
                animationDirection: "alternate",
                animationTimingFunction: "ease-in-out",
              }
            : null,
        ]}
      />
      <Text
        variant={state === "current" ? "heading" : "body"}
        tone={state === "current" ? "primary" : "tertiary"}
      >
        {t(`generating.stages.${stage}`)}
      </Text>
    </View>
  );
}

export function GeneratingScreen({
  roomId,
  onDone,
  source,
  designs = true,
}: {
  roomId: string;
  /** False for a kind of space that gets no designs yet: the designing stage is left out. */
  designs?: boolean;
  /** Every stage is finished: go to the reveal. */
  onDone: () => void;
  source?: GenerationSource;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { colors, spacing } = tokens;
  const stages = stagesFor(designs);
  const progress = useGeneration(roomId, source, stages);

  // A light tick as each stage finishes.
  const ticked = useRef(0);
  useEffect(() => {
    if (progress.finished > ticked.current) void playHaptic("cornerCaptured");
    ticked.current = progress.finished;
  }, [progress.finished]);

  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    if (!progress.done) return;
    const timer = setTimeout(() => done.current(), HANDOVER_MS);
    return () => clearTimeout(timer);
  }, [progress.done]);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.canvas }}>
      <View
        style={{
          flex: 1,
          padding: spacing.gutter,
          paddingTop: spacing.sheetBottom * 2,
          gap: spacing.sheetBottom * 2,
        }}
      >
        <Text variant="title" accessibilityRole="header">
          {t(designs ? "generating.title" : "generating.titleRoomOnly")}
        </Text>
        <View accessibilityLiveRegion="polite" style={{ gap: spacing.sheetBottom }}>
          {stages.map((stage, index) => (
            <StageRow
              key={stage}
              stage={stage}
              state={
                index < progress.finished ? "done" : stage === progress.current ? "current" : "next"
              }
            />
          ))}
        </View>
      </View>
    </SafeAreaView>
  );
}
