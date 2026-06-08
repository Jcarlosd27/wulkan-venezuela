import type { ReactNode } from "react";

interface ErrorStateProps {
  title?: string;
  message: string;
  action?: ReactNode;
}

export function ErrorState({ title = "Error", message, action }: ErrorStateProps) {
  return (
    <div className="errorState">
      <div className="errorIcon">⚠️</div>
      <h3>{title}</h3>
      <p>{message}</p>
      {action && <div className="errorAction">{action}</div>}
    </div>
  );
}
