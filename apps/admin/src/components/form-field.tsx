import type { ReactNode } from "react";

interface FormFieldProps {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}

export function FormField({ label, hint, error, required, children }: FormFieldProps) {
  return (
    <label className={`formField ${error ? "error" : ""}`}>
      <span>
        {label}
        {required && <span className="required">*</span>}
      </span>
      {children}
      {error ? (
        <small className="errorText">❌ {error}</small>
      ) : hint ? (
        <small className="hintText">ℹ️ {hint}</small>
      ) : null}
    </label>
  );
}

