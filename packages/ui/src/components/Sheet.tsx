import { BottomSheet, type BottomSheetProps, Host } from "@expo/ui";
import { useTheme } from "../theme";

export type SheetProps = Pick<
  BottomSheetProps,
  "children" | "isPresented" | "onDismiss" | "snapPoints" | "testID"
>;

/**
 * A native bottom sheet (SwiftUI on iOS, Compose on Android), so detents,
 * drag, back gesture and reduced motion follow each platform's manners.
 */
export function Sheet({ children, ...rest }: SheetProps) {
  const { tokens } = useTheme();
  return (
    <Host>
      <BottomSheet
        showDragIndicator
        containerColor={tokens.colors.canvas}
        contentPadding={tokens.spacing.lg}
        {...rest}
      >
        {children}
      </BottomSheet>
    </Host>
  );
}
