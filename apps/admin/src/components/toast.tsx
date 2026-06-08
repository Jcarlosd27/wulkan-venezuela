"use client";

import { useState, useCallback } from "react";

type ToastType = "success" | "error" | "info" | "warning";

interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
}

let toastCounter = 0;
let toastCallback: ((toast: ToastMessage) => void) | null = null;

export function useToast() {
  return useCallback((message: string, type: ToastType = "info") => {
    const id = `toast-${++toastCounter}`;
    const toast: ToastMessage = { id, type, message };

    if (toastCallback) {
      toastCallback(toast);
    }

    setTimeout(() => {
      if (toastCallback) {
        toastCallback({ ...toast, id: `${id}-remove` });
      }
    }, 4000);
  }, []);
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  toastCallback = useCallback((toast: ToastMessage) => {
    if (toast.id.includes("remove")) {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id.replace("-remove", "")));
    } else {
      setToasts((prev) => [...prev, toast]);
    }
  }, []);

  return (
    <div className="toastContainer">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.type}`}>
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
