// The room plan with one design's furniture in place, top down: the drawing,
// with each wall's length and the tightest clearances written over it in the
// chosen units. The plan and its numbers are a view of the `Design` and the
// room's measured shell.
import { Text, useTheme } from "@sajao/ui";
import type { Design } from "@sajao/schemas";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";
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

/** The smallest target a finger can hit reliably, in points. */
const MIN_TARGET = 44;

export function DesignPlanView({
  design,
  shell,
  units,
  width,
  height,
  selectedId = null,
  onSelect,
  gaps = true,
}: {
  /** The design whose furniture is drawn; null draws the room alone. */
  design: Design | null;
  shell: PlanShell;
  units: LengthUnits;
  width: number;
  height: number;
  /** The piece picked on the plan; its gap to the nearest wall is the one shown. */
  selectedId?: string | null;
  /** Tapping a piece picks it; tapping it again lets it go. Left out, pieces are not tappable. */
  onSelect?: (itemId: string | null) => void;
  /** Gaps to the walls: shown for measured rooms only. */
  gaps?: boolean;
}) {
  const { t } = useTranslation();
  const plan = useMemo(
    () => designPlan(design, shell, { width, height, padding: PADDING }, { selectedId, gaps }),
    [design, shell, width, height, selectedId, gaps],
  );
  return (
    <View
      testID="room-plan"
      // With tappable pieces the plan is a group, so each piece can be reached.
      accessible={!onSelect}
      accessibilityRole={onSelect ? undefined : "image"}
      accessibilityLabel={t("room.plan.picture", { count: plan.items.length })}
      style={{ width, height }}
    >
      <PlanCanvas plan={plan} width={width} height={height} />
      {onSelect
        ? plan.items.map((item) => {
            const xs = item.corners.map((corner) => corner.x);
            const ys = item.corners.map((corner) => corner.y);
            const w = Math.max(Math.max(...xs) - Math.min(...xs), MIN_TARGET);
            const h = Math.max(Math.max(...ys) - Math.min(...ys), MIN_TARGET);
            const chosen = item.id === plan.selected?.id;
            return (
              <Pressable
                key={item.id}
                testID={`plan-item-${item.id}`}
                accessibilityRole="button"
                accessibilityLabel={item.title}
                accessibilityState={{ selected: chosen }}
                onPress={() => onSelect(chosen ? null : item.id)}
                style={{
                  position: "absolute",
                  left: item.centre.x - w / 2,
                  top: item.centre.y - h / 2,
                  width: w,
                  height: h,
                }}
              />
            );
          })
        : null}
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
