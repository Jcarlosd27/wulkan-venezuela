"use client";

import { useCallback, useState } from "react";

export interface ConfirmDialogRef {
  open: (
    title: string,
    message: string,
    options?: { confirmLabel?: string; cancelLabel?: string }
  ) => Promise<boolean>;
}

export function ConfirmationDialog() {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [confirmLabel, setConfirmLabel] = useState("Confirmar");
  const [cancelLabel, setCancelLabel] = useState("Cancelar");
  const [resolve, setResolve] = useState<((value: boolean) => void) | null>(null);

  const handleConfirm = useCallback(() => {
    resolve?.(true);
    setOpen(false);
    setResolve(null);
  }, [resolve]);

  const handleCancel = useCallback(() => {
    resolve?.(false);
    setOpen(false);
    setResolve(null);
  }, [resolve]);

  return (
    <>
      {open && (
        <div className="dialogOverlay" onClick={handleCancel}>
          <div className="dialogContent" onClick={(e) => e.stopPropagation()}>
            <h2>{title}</h2>
            <p>{message}</p>
            <div className="dialogActions">
              <button className="btnSecondary" onClick={handleCancel}>
                {cancelLabel}
              </button>
              <button className="btnPrimary" onClick={handleConfirm}>
                {confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
