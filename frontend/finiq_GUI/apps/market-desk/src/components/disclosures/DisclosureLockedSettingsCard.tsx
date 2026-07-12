import { Lock } from "lucide-react";
import { Card, CardContent } from "@finiq/ui";

type DisclosureLockedSettingsCardProps = {
  title: string;
};

export function DisclosureLockedSettingsCard({ title }: DisclosureLockedSettingsCardProps) {
  return (
    <Card aria-label={`${title} 잠김`} className="border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
      <CardContent className="flex min-h-8 items-center justify-between px-6 py-0">
        <h3 className="text-sm font-semibold text-[var(--tv-muted)]">{title}</h3>
        <Lock className="h-4 w-4 text-[var(--tv-muted)]" aria-hidden="true" />
      </CardContent>
    </Card>
  );
}
