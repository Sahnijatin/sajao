import { Button, Card, Chip, Text, useTheme } from "@sajao/ui";
import { type ReactNode, useReducer } from "react";
import { useTranslation } from "react-i18next";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { tasteSoFar } from "@/taste/adaptive-swipes";
import { DECK } from "@/taste/deck";
import {
  AGE_BANDS,
  BUDGETS_INR,
  canContinue,
  HOUSEHOLDS,
  MUST_HAVES,
  progress,
  startTaste,
  type TasteAnswers,
  tasteAnswers,
  tasteReducer,
  TENURES,
} from "@/taste/taste-session";
import { vastuEnabled } from "@/features";
import { formatInr } from "@/utils/format-inr";

const reducer = tasteReducer(DECK);

function Group({ title, children }: { title?: string; children: ReactNode }) {
  const { spacing } = useTheme().tokens;
  return (
    <View style={{ gap: spacing.md }}>
      {title ? <Text variant="label">{title}</Text> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>{children}</View>
    </View>
  );
}

/**
 * Taste onboarding: a little context, 8 to 12 adaptive swipes, then budget
 * and must-haves. The age band is asked once and never shown back.
 */
export function TasteScreen({
  onDone,
  showVastu = vastuEnabled(),
}: {
  onDone: (answers: TasteAnswers) => void;
  /** The "consider Vastu" choice, behind its build setting (off). */
  showVastu?: boolean;
}) {
  const { t } = useTranslation();
  const { tokens } = useTheme();
  const { spacing } = tokens;
  const insets = useSafeAreaInsets();
  const [state, dispatch] = useReducer(reducer, undefined, startTaste);

  const finish = () => {
    const done = reducer(state, { type: "continue" });
    if (done.step === "done") onDone(tasteAnswers(done, DECK));
  };

  let body: ReactNode = null;
  if (state.step === "context") {
    body = (
      <>
        <Text variant="title" accessibilityRole="header">
          {t("taste.contextTitle")}
        </Text>
        <Group title={t("taste.ageTitle")}>
          {AGE_BANDS.map((band) => (
            <Chip
              key={band}
              label={t(`taste.ageBands.${band}`)}
              selected={state.ageBand === band}
              onPress={() => dispatch({ type: "ageBand", value: band })}
            />
          ))}
        </Group>
        <Group title={t("taste.householdTitle")}>
          {HOUSEHOLDS.map((who) => (
            <Chip
              key={who}
              label={t(`taste.household.${who}`)}
              selected={state.household.includes(who)}
              onPress={() => dispatch({ type: "household", value: who })}
            />
          ))}
        </Group>
        <Group title={t("taste.tenureTitle")}>
          {TENURES.map((tenure) => (
            <Chip
              key={tenure}
              label={t(`taste.tenure.${tenure}`)}
              selected={state.tenure === tenure}
              onPress={() => dispatch({ type: "tenure", value: tenure })}
            />
          ))}
        </Group>
        <Button
          label={t("taste.continue")}
          disabled={!canContinue(state)}
          onPress={() => dispatch({ type: "continue" })}
        />
      </>
    );
  } else if (state.step === "swipes" && state.card) {
    const card = state.card;
    const mainStyle = (Object.keys(card.appeal) as (keyof typeof card.appeal)[]).reduce((a, b) =>
      card.appeal[b] > card.appeal[a] ? b : a,
    );
    const traits = tasteSoFar(state.swipes, DECK);
    body = (
      <>
        <View
          style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}
        >
          <Button
            label={t("taste.back")}
            variant="ghost"
            size="small"
            onPress={() => dispatch({ type: "back" })}
          />
          <Text variant="meta" tone="secondary">
            {t("taste.progress", progress(state))}
          </Text>
        </View>
        <Text variant="title" accessibilityRole="header">
          {t("taste.question")}
        </Text>
        <Card style={{ gap: spacing.md, minHeight: 240, justifyContent: "flex-end" }}>
          <Text variant="heading">{t(`taste.styles.${mainStyle}`)}</Text>
          <Text variant="bodySmall" tone="secondary">
            {card.traits.map((trait) => t(`taste.traits.${trait}`)).join(", ")}
          </Text>
        </Card>
        <View style={{ flexDirection: "row", gap: spacing.lg }}>
          <Button
            label={t("taste.no")}
            variant="outline"
            style={{ flex: 1 }}
            onPress={() => dispatch({ type: "answer", value: "no" })}
          />
          <Button
            label={t("taste.love")}
            style={{ flex: 1 }}
            onPress={() => dispatch({ type: "answer", value: "love" })}
          />
        </View>
        <Button
          label={t("taste.unsure")}
          variant="ghost"
          size="small"
          onPress={() => dispatch({ type: "answer", value: "unsure" })}
        />
        {traits.length > 0 ? (
          <View style={{ gap: spacing.md }}>
            <Text variant="captionStrong" tone="secondary">
              {t("taste.soFar").toUpperCase()}
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
              {traits.map((trait) => (
                <Chip key={trait} label={t(`taste.traits.${trait}`)} selected disabled />
              ))}
            </View>
          </View>
        ) : null}
      </>
    );
  } else if (state.step === "budget") {
    body = (
      <>
        <Button
          label={t("taste.back")}
          variant="ghost"
          size="small"
          style={{ alignSelf: "flex-start" }}
          onPress={() => dispatch({ type: "back" })}
        />
        <Text variant="title" accessibilityRole="header">
          {t("taste.budgetTitle")}
        </Text>
        <Group>
          {BUDGETS_INR.map((rupees) => (
            <Chip
              key={rupees}
              label={formatInr(rupees * 100)}
              selected={state.budgetInr === rupees}
              onPress={() => dispatch({ type: "budget", value: rupees })}
            />
          ))}
        </Group>
        <Group>
          {(["strict", "stretch_10"] as const).map((flexibility) => (
            <Chip
              key={flexibility}
              label={t(`taste.flexibility.${flexibility}`)}
              selected={state.flexibility === flexibility}
              onPress={() => dispatch({ type: "flexibility", value: flexibility })}
            />
          ))}
        </Group>
        <Group title={t("taste.mustHavesTitle")}>
          {MUST_HAVES.map((item) => (
            <Chip
              key={item}
              label={t(`taste.mustHaves.${item}`)}
              selected={state.mustHaves.includes(item)}
              onPress={() => dispatch({ type: "mustHave", value: item })}
            />
          ))}
        </Group>
        {showVastu ? (
          <Chip
            label={t("taste.vastu")}
            selected={state.considerVastu}
            onPress={() => dispatch({ type: "considerVastu", value: !state.considerVastu })}
          />
        ) : null}
        <Button label={t("taste.finish")} disabled={!canContinue(state)} onPress={finish} />
      </>
    );
  }

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
      {body}
    </ScrollView>
  );
}
