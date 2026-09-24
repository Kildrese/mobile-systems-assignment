// Shared shape of the web forms' Server Action state (`useActionState`), plus
// helpers to parse `FormData` with the API's Zod contracts.
import type { z } from "zod";

export type FormState = {
  fieldErrors?: Record<string, string[] | undefined>;
  formError?: string;
  // Non-secret inputs sent back so a failed submit doesn't clear them.
  // Passwords are never included.
  values?: Record<string, string>;
  // Set on success. `at` changes on every success so the form can toast again.
  success?: { message: string; at: number };
};

export const initialFormState: FormState = {};

// Only the named fields: `FormData` also carries React's internal `$ACTION_…`
// entries, which the strict contract schemas would reject.
export function pick(formData: FormData, keys: readonly string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of keys) {
    const value = formData.get(key);
    if (typeof value === "string") out[key] = value;
  }
  return out;
}

function message(issue: z.core.$ZodIssue): string {
  switch (issue.code) {
    case "too_small":
      return issue.minimum === 1 ? "Required" : `Must be at least ${issue.minimum} characters`;
    case "too_big":
      return `Must be at most ${issue.maximum} characters`;
    case "invalid_format":
      if (issue.format === "email") return "Enter a valid email address";
      // Our regex checks carry their own human-readable message.
      return issue.format === "regex" ? issue.message : "Invalid value";
    case "invalid_type":
      return "Required";
    default:
      return issue.message;
  }
}

// Field-keyed, human-readable messages. Issues without a path (e.g. a
// refinement on the whole object) go to `formError`.
export function fromZodError(error: z.ZodError): Pick<FormState, "fieldErrors" | "formError"> {
  const fieldErrors: Record<string, string[]> = {};
  let formError: string | undefined;
  for (const issue of error.issues) {
    const key = issue.path[0];
    if (typeof key === "string") (fieldErrors[key] ??= []).push(message(issue));
    else formError ??= issue.message;
  }
  return { fieldErrors, formError };
}

// For shadcn's `<FieldError errors={…} />`.
export function asErrors(messages: string[] | undefined) {
  return messages?.map((m) => ({ message: m }));
}
