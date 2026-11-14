import { View, type ViewProps } from "react-native";
import { useTheme } from "../theme";

export function Card({ style, ...rest }: ViewProps) {
  const { tokens, tier } = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: tokens.colors.surface,
          borderRadius: tokens.radius.card,
          padding: tokens.spacing.lg,
          boxShadow: tokens.shadows[tier],
        },
        style,
      ]}
      {...rest}
    />
  );
}
