import { useState } from "react";
import { TextInput, type TextInputProps, View } from "react-native";
import { useTheme } from "../theme";
import { fontFor, touchTarget } from "../tokens";
import { Text } from "./Text";

export interface TextFieldProps extends TextInputProps {
  label: string;
}

/** Uncontrolled by default: pass defaultValue and read onChangeText. */
export function TextField({ label, style, onFocus, onBlur, ...rest }: TextFieldProps) {
  const { tokens } = useTheme();
  const { colors, radius, spacing, typography } = tokens;
  const [focused, setFocused] = useState(false);

  return (
    <View style={{ gap: spacing.xs }}>
      <Text variant="label" tone="secondary">
        {label}
      </Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.inkTertiary}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        style={[
          {
            minHeight: touchTarget,
            paddingHorizontal: spacing.lg,
            borderRadius: radius.card,
            borderWidth: 1,
            borderColor: focused ? colors.accent : colors.hairline,
            backgroundColor: colors.surface,
            color: colors.ink,
            fontSize: typography.body.fontSize,
          },
          fontFor(typography.body.weight),
          style,
        ]}
        {...rest}
      />
    </View>
  );
}
