// A room's job where the room itself is shown: the three stages, which one
// is in hand, or why it stopped with a Retry. Never stand-in content.
import { Button, Card, Text, useTheme } from "@sajao/ui";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { GENERATION_STAGES } from "@/rooms/generation";
import type { RoomJobState } from "@/state/room-jobs";

/** Reasons the app has words for; any other gets the general message. */
export const KNOWN_REASONS: readonly string[] = [
  "no_walls",
  "no_ar_data",
  "upload",
  "upload_incomplete",
  "photo_too_small",
  "photo_missing",
  "photo_unreadable",
  "planes_unreadable",
  "floor_not_visible",
  "space_not_supported",
  "invalid_request",
  "no_products",
  "no_layout_for_room",
  "nothing_fits",
  "needs_wider_view",
  "render_failed",
  "timed_out",
  "internal",
];

/** Failures that another photo of the same room can fix. */
export const ADD_PHOTO_REASONS: readonly string[] = ["nothing_fits", "needs_wider_view"];

export function JobProgress({
  job,
  onRetry,
  onAddPhoto,
}: {
  job: RoomJobState;
  onRetry?: () => void;
  /** Opens the camera to add a photo to this same room. */
  onAddPhoto?: () => void;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { spacing, colors } = tokens;
  if (job.stage === "failed") {
    const reason = KNOWN_REASONS.includes(job.reason ?? "") ? job.reason : "unknown";
    return (
      <Card testID="job-failed" style={{ gap: spacing.xl }}>
        <Text variant="bodyStrong">{t("generating.failed.title")}</Text>
        <Text tone="secondary">{t(`generating.failed.${reason}`)}</Text>
        {onAddPhoto && ADD_PHOTO_REASONS.includes(job.reason ?? "") ? (
          <Button label={t("generating.failed.addPhoto")} onPress={onAddPhoto} />
        ) : null}
        {/* Retry only when the server says asking again may help. */}
        {onRetry && job.retryable !== false ? (
          <Button label={t("generating.failed.retry")} onPress={onRetry} />
        ) : null}
      </Card>
    );
  }
  return (
    <Card testID="job-progress" style={{ gap: spacing.lg }}>
      <View accessibilityLiveRegion="polite" style={{ gap: spacing.md }}>
        {GENERATION_STAGES.map((stage, index) => {
          const state = index < job.finished ? "done" : index === job.finished ? "current" : "next";
          return (
            <View
              key={stage}
              testID={`job-stage-${stage}`}
              accessible
              accessibilityLabel={t(`generating.stages.${stage}`)}
              accessibilityState={{ busy: state === "current", checked: state === "done" }}
              style={{ flexDirection: "row", alignItems: "center", gap: spacing.lg }}
            >
              <View
                style={{
                  width: spacing.md,
                  height: spacing.md,
                  borderRadius: tokens.radius.pill,
                  backgroundColor:
                    state === "done"
                      ? colors.success
                      : state === "current"
                        ? colors.accent
                        : colors.sand,
                }}
              />
              <Text
                variant={state === "current" ? "bodyStrong" : "body"}
                tone={state === "next" ? "tertiary" : "primary"}
              >
                {t(`generating.stages.${stage}`)}
              </Text>
            </View>
          );
        })}
      </View>
    </Card>
  );
}
