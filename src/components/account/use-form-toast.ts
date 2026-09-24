"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import type { FormState } from "@/lib/forms";

// Toasts each new success (`success.at` changes on every one).
export function useFormToast(state: FormState) {
  const at = state.success?.at;
  const message = state.success?.message;
  useEffect(() => {
    if (at && message) toast.success(message);
  }, [at, message]);
}
