// Dev-only component gallery: every token and component on one screen, with
// switches to preview the low-tier and reduced-motion fallbacks. Labels here
// are developer-facing, so they are not in the app's string catalogs.
import { type ReactNode, useState } from "react";
import { ScrollView, View } from "react-native";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Chip } from "../components/Chip";
import { GlassSurface } from "../components/GlassSurface";
import { Sheet } from "../components/Sheet";
import { Text } from "../components/Text";
import { TextField } from "../components/TextField";
import { type HapticMoment, hapticMap, playHaptic } from "../haptics";
import { ThemeProvider, useTheme } from "../theme";
import { colors, type TypographyVariant, typography } from "../tokens";

function Section({ title, children }: { title: string; children: ReactNode }) {
  const { tokens } = useTheme();
  return (
    <View style={{ gap: tokens.spacing.xl }}>
      <Text variant="heading">{title}</Text>
      {children}
    </View>
  );
}

function Row({ children }: { children: ReactNode }) {
  const { tokens } = useTheme();
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: tokens.spacing.md }}>
      {children}
    </View>
  );
}

function Swatch({ name, color }: { name: string; color: string }) {
  const { tokens } = useTheme();
  return (
    <View style={{ alignItems: "center", gap: tokens.spacing.xs, width: 72 }}>
      <View
        style={{
          width: 48,
          height: 48,
          borderRadius: tokens.radius.card,
          backgroundColor: color,
          borderWidth: 1,
          borderColor: tokens.colors.hairline,
        }}
      />
      <Text variant="caption" tone="secondary">
        {name}
      </Text>
    </View>
  );
}

function GalleryContent() {
  const { tokens, tier, reducedMotion } = useTheme();
  const { spacing, radius } = tokens;
  const [chip, setChip] = useState("Japandi");
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <ScrollView
      testID="gallery"
      style={{ backgroundColor: tokens.colors.canvas }}
      contentContainerStyle={{ padding: spacing.gutter, gap: spacing.sheetBottom }}
      contentInsetAdjustmentBehavior="automatic"
    >
      <Text variant="caption" tone="tertiary">
        {`Tier: ${tier} · Reduced motion: ${reducedMotion ? "on" : "off"}`}
      </Text>

      <Section title="Colors">
        <Row>
          {Object.entries(colors).map(([name, color]) => (
            <Swatch key={name} name={name} color={color} />
          ))}
        </Row>
      </Section>

      <Section title="Type">
        {(Object.keys(typography) as TypographyVariant[]).map((variant) => (
          <Text key={variant} variant={variant}>
            {`${variant} · Scan your room`}
          </Text>
        ))}
        <Text variant="title">
          Warm{" "}
          <Text variant="title" italic>
            Japandi
          </Text>
        </Text>
      </Section>

      <Section title="Buttons">
        <Button label="Show me ideas" />
        <Row>
          <Button label="Rent instead" variant="outline" style={{ flex: 1 }} />
          <Button label="Add to list" variant="ink" style={{ flex: 1 }} />
        </Row>
        <Row>
          <Button label="Change" variant="tint" size="small" />
          <Button label="Ghost" variant="ghost" size="small" />
          <Button label="Disabled" disabled size="small" />
        </Row>
      </Section>

      <Section title="Chips">
        <Row>
          {["Japandi", "Warm Luxe", "Modern Indian"].map((label) => (
            <Chip
              key={label}
              label={label}
              selected={chip === label}
              onPress={() => setChip(label)}
            />
          ))}
        </Row>
      </Section>

      <Section title="Card">
        <Card>
          <Text variant="label">Card</Text>
          <Text variant="bodySmall" tone="secondary">
            Soft stacked shadows; one shadow on the low tier.
          </Text>
        </Card>
      </Section>

      <Section title="Glass surface">
        {(["light", "dark"] as const).map((tone) => (
          <View key={tone} style={{ borderRadius: radius.pane, overflow: "hidden" }}>
            <View style={{ flexDirection: "row", height: 120 }}>
              <View style={{ flex: 1, backgroundColor: tokens.colors.accent }} />
              <View style={{ flex: 1, backgroundColor: tokens.colors.warning }} />
              <View style={{ flex: 1, backgroundColor: tokens.colors.success }} />
            </View>
            <GlassSurface
              tone={tone}
              testID={`glass-${tone}`}
              style={{
                position: "absolute",
                left: spacing.gutter,
                right: spacing.gutter,
                top: spacing.gutter,
                padding: spacing.gutter,
              }}
            >
              <Text variant="label" tone={tone === "dark" ? "onDark" : "primary"}>
                {tone === "dark" ? "Dark glass, for camera screens" : "Light glass"}
              </Text>
              <Text variant="bodySmall" tone={tone === "dark" ? "onDark" : "secondary"}>
                Live blur, or a tint on the low tier.
              </Text>
            </GlassSurface>
          </View>
        ))}
      </Section>

      <Section title="Input">
        <TextField label="Room name" placeholder="Living room" />
      </Section>

      <Section title="Sheet">
        <Row>
          <Button label="Open sheet" variant="outline" onPress={() => setSheetOpen(true)} />
        </Row>
        <Sheet isPresented={sheetOpen} onDismiss={() => setSheetOpen(false)} snapPoints={["half"]}>
          <View style={{ gap: spacing.xxl }}>
            <Text variant="heading">Sheet</Text>
            <Button label="Close" onPress={() => setSheetOpen(false)} />
          </View>
        </Sheet>
      </Section>

      <Section title="Haptics">
        <Row>
          {(Object.keys(hapticMap) as HapticMoment[]).map((moment) => (
            <Chip
              key={moment}
              label={moment}
              selected={false}
              onPress={() => void playHaptic(moment)}
            />
          ))}
        </Row>
      </Section>
    </ScrollView>
  );
}

export default function GalleryScreen() {
  const [lowTier, setLowTier] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  return (
    // Unset switches fall back to the device's own tier and system setting.
    <ThemeProvider
      {...(lowTier ? { tier: "low" as const } : {})}
      {...(reducedMotion ? { reducedMotion: true } : {})}
    >
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", gap: 8, padding: 16, backgroundColor: colors.canvas }}>
          <Chip label="Low tier" selected={lowTier} onPress={() => setLowTier((on) => !on)} />
          <Chip
            label="Reduced motion"
            selected={reducedMotion}
            onPress={() => setReducedMotion((on) => !on)}
          />
        </View>
        <GalleryContent />
      </View>
    </ThemeProvider>
  );
}
