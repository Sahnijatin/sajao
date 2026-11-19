// The budget for one room, asked each time a room goes on to its designs
// (after the first, whose budget is part of taste). Prefilled from the last
// room, so the usual answer is one tap.
import { Button, Chip, motion, Text, useTheme } from "@sajao/ui";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ScrollView, View } from "react-native";
import Animated, { Easing, FadeIn } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { BUDGETS_INR, type TasteAnswers } from "@/taste/taste-session";
import { formatInr } from "@/utils/format-inr";

export type RoomBudget = TasteAnswers["budget"];

export function BudgetScreen({
  initial,
  onDone,
}: {
  /** The budget to start from: the last room's. */
  initial: RoomBudget;
  onDone: (budget: RoomBudget) => void;
}) {
  const { t } = useTranslation();
  const { tokens, duration } = useTheme();
  const { spacing } = tokens;
  const insets = useSafeAreaInsets();
  const [rupees, setRupees] = useState(Math.round(initial.limit.amount_minor / 100));
  const [flexibility, setFlexibility] = useState(initial.flexibility);
  const fade = duration(motion.ease.durationMs);
  const entering =
    fade > 0 ? FadeIn.duration(fade).easing(Easing.bezier(...motion.ease.bezier)) : undefined;
  // A budget from Profile that is not one of the steps still shows, selected.
  const steps = BUDGETS_INR.includes(rupees)
    ? BUDGETS_INR
    : [...BUDGETS_INR, rupees].sort((a, b) => a - b);
  return (
    <ScrollView
      style={{ backgroundColor: tokens.colors.canvas }}
      contentContainerStyle={{
        paddingTop: insets.top + spacing.gutter,
        paddingBottom: insets.bottom + spacing.sheetBottom,
        paddingHorizontal: spacing.gutter,
        gap: spacing.gutter,
      }}
    >
      <Animated.View entering={entering} style={{ gap: spacing.gutter }}>
        <Text variant="title" accessibilityRole="header">
          {t("budget.title")}
        </Text>
        <Text tone="secondary">{t("budget.body")}</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {steps.map((step) => (
            <Chip
              key={step}
              label={formatInr(step * 100)}
              selected={rupees === step}
              onPress={() => setRupees(step)}
            />
          ))}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
          {(["strict", "stretch_10"] as const).map((each) => (
            <Chip
              key={each}
              label={t(`taste.flexibility.${each}`)}
              selected={flexibility === each}
              onPress={() => setFlexibility(each)}
            />
          ))}
        </View>
        <Button
          label={t("budget.continue")}
          onPress={() =>
            onDone({ limit: { currency: "INR", amount_minor: rupees * 100 }, flexibility })
          }
        />
      </Animated.View>
    </ScrollView>
  );
}
