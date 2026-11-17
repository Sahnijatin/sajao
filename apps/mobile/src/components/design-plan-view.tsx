// The room plan with one design's furniture in place, top down: the drawing,
// with each wall's length and the tightest clearances written over it in the
// chosen units. The plan and its numbers are a view of the `Design` and the
// room's measured shell.
import { Text, useTheme } from "@sajao/ui";
import type { Design } from "@sajao/schemas";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";
import { designPlan, type PlanShell, type Px } from "@/rooms/design-plan";
import { formatLength, type LengthUnits } from "@/utils/format-length";
import { PlanCanvas } from "./plan-canvas";

/** Room for the wall lengths written outside the outline. */
const PADDING = 44;
/** Labels are centred on their point: this is half their box. */
const LABEL = { width: 84, height: 20 };

function Label({ at, text, tone }: { at: Px; text: string; tone: "wall" | "gap" }) {
  const { tokens } = useTheme();
  return (
    <View
      pointerEvents="none"
      style={{
        position: "absolute",
        left: at.x - LABEL.width / 2,
        top: at.y - LABEL.height / 2,
        width: LABEL.width,
        height: LABEL.height,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <View
        style={{
          paddingHorizontal: tokens.spacing.sm,
          borderRadius: tokens.radius.pill,
          backgroundColor: tone === "gap" ? tokens.colors.surface : "transparent",
        }}
      >
        <Text
          variant="micro"
          tone={tone === "gap" ? "primary" : "secondary"}
          style={{ fontVariant: ["tabular-nums"] }}
        >
          {text}
        </Text>
      </View>
    </View>
  );
}

export function DesignPlanView({
  design,
  shell,
  units,
  width,
  height,
}: {
  /** The design whose furniture is drawn; null draws the room alone. */
  design: Design | null;
  shell: PlanShell;
  units: LengthUnits;
  width: number;
  height: number;
}) {
  const { t } = useTranslation();
  const plan = useMemo(
    () => designPlan(design, shell, { width, height, padding: PADDING }),
    [design, shell, width, height],
  );
  return (
    <View
      testID="room-plan"
      accessible
      accessibilityRole="image"
      accessibilityLabel={t("room.plan.picture", { count: plan.items.length })}
      style={{ width, height }}
    >
      <PlanCanvas plan={plan} width={width} height={height} />
      {plan.walls.map((wall) => (
        <Label key={wall.id} at={wall.at} tone="wall" text={formatLength(wall.metres, units, t)} />
      ))}
      {plan.clearances.map((gap) => (
        <Label
          key={gap.itemId}
          at={{ x: (gap.from.x + gap.to.x) / 2, y: (gap.from.y + gap.to.y) / 2 }}
          tone="gap"
          text={formatLength(gap.metres, units, t)}
        />
      ))}
    </View>
  );
}
