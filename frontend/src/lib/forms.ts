// Field errors for the forms, from client-side checks and from the API's
// `VALIDATION_ERROR` details.
import type { Error as ApiErrorBody, ValidationIssue } from "@/api/types.gen";

export type FieldErrors = Record<string, string[] | undefined>;

export type FormErrors = {
  fieldErrors?: FieldErrors;
  formError?: string;
};

function message(issue: ValidationIssue): string {
  switch (issue.code) {
    case "missing":
      return "Required";
    case "string_too_short":
      return /at least 1 character/.test(issue.message)
        ? "Required"
        : issue.message.replace(/^String should have/, "Must be");
    case "string_too_long":
      return issue.message.replace(/^String should have/, "Must be");
    case "string_pattern_mismatch":
      return "Use only letters, digits, underscores and periods";
    case "value_error":
      if (/email/i.test(issue.message)) return "Enter a valid email address";
      return issue.message.replace(/^Value error, /, "");
    default:
      return issue.message;
  }
}

// Field-keyed, human-readable messages. Issues without a field (e.g. a check
// on the whole body) go to `formError`.
export function fromApiError(error: unknown): FormErrors | null {
  const body = error as Partial<ApiErrorBody> | undefined;
  if (body?.error?.code !== "VALIDATION_ERROR") return null;
  const fieldErrors: FieldErrors = {};
  let formError: string | undefined;
  for (const issue of body.error.details ?? []) {
    const key = issue.path[0];
    if (typeof key === "string") (fieldErrors[key] ??= []).push(message(issue));
    else formError ??= message(issue);
  }
  return { fieldErrors, formError };
}

export function errorCode(error: unknown): string | undefined {
  return (error as Partial<ApiErrorBody> | undefined)?.error?.code;
}

// For shadcn's `<FieldError errors={…} />`.
export function asErrors(messages: string[] | undefined) {
  return messages?.map((m) => ({ message: m }));
}

// The form's string fields, by name.
export function formValues(form: HTMLFormElement): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of new FormData(form)) {
    if (typeof value === "string") out[key] = value;
  }
  return out;
}

export const SOMETHING_WENT_WRONG = "Something went wrong. Please try again.";
