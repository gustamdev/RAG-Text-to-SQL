import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="border-b border-border">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-6 px-4 py-10 md:flex-row md:items-end md:justify-between md:px-8 md:py-16">
        <div>
          {eyebrow && <p className="eyebrow text-muted-foreground">{eyebrow}</p>}
          <h1 className="display mt-3 text-4xl md:text-6xl">{title}</h1>
          {description && (
            <p className="mt-4 max-w-2xl text-sm text-muted-foreground md:text-base">{description}</p>
          )}
        </div>
        {action}
      </div>
    </div>
  );
}
