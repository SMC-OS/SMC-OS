import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

export function ComingSoon({
  title,
  description,
  sprint,
}: {
  title: string;
  description: string;
  sprint: string;
}) {
  return (
    <Card className="flex flex-col items-start gap-3 p-8">
      <Badge tone="info">Coming in {sprint}</Badge>
      <h2 className="text-xl font-semibold text-foreground">{title}</h2>
      <p className="max-w-prose text-sm text-muted">{description}</p>
    </Card>
  );
}
