import type { ReactNode } from "react";

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon = "📭", title, description, action }: EmptyStateProps) {
  return (
    <div className="emptyState">
      <div className="emptyIcon">{icon}</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div className="emptyAction">{action}</div>}
    </div>
  );
}
