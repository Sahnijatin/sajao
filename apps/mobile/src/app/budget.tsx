import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { BudgetScreen } from "@/screens/budget";
import { useRooms } from "@/state/rooms";
import { useTaste } from "@/state/taste";

export { RouteErrorBoundary as ErrorBoundary } from "@/components/route-error-boundary";

/** A later room's budget, before its designs: prefilled from the last room. */
export default function BudgetRoute() {
  const router = useRouter();
  const { room } = useLocalSearchParams<{ room?: string }>();
  const { answers, lastBudget } = useTaste.getState();
  const initial = lastBudget ?? answers?.budget;
  if (!room) return <Redirect href="/" />;
  // No taste yet: that is where the budget is asked.
  if (!initial) return <Redirect href={{ pathname: "/taste", params: { room } }} />;
  return (
    <BudgetScreen
      initial={initial}
      onDone={(budget) => {
        useRooms.getState().setRoomBudget(room, budget);
        useTaste.getState().setLastBudget(budget);
        router.replace({ pathname: "/generating", params: { room } });
      }}
    />
  );
}
