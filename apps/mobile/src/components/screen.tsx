import { Text, useTheme } from "@sajao/ui";
import type { ReactNode } from "react";
import { ScrollView } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

/** The standard page: canvas background, safe area, a title and stacked content. */
export function Screen({ title, children }: { title: string; children: ReactNode }) {
  const { tokens } = useTheme();
  return (
    <SafeAreaView edges={["top"]} style={{ flex: 1, backgroundColor: tokens.colors.canvas }}>
      <ScrollView
        contentContainerStyle={{ padding: tokens.spacing.gutter, gap: tokens.spacing.gutter }}
        contentInsetAdjustmentBehavior="automatic"
      >
        <Text variant="title" accessibilityRole="header">
          {title}
        </Text>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}
