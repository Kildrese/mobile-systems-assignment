import { describe, expect, it } from "vitest";
import { asErrors, errorCode, fromApiError } from "@/lib/forms";

function validationError(details: { path: (string | number)[]; code: string; message: string }[]) {
  return { error: { code: "VALIDATION_ERROR", message: "Request body failed validation", details } };
}

describe("fromApiError", () => {
  it("ignores anything that isn't a validation error", () => {
    expect(fromApiError(undefined)).toBeNull();
    expect(fromApiError(new Error("network"))).toBeNull();
    expect(fromApiError({ error: { code: "USERNAME_TAKEN", message: "taken" } })).toBeNull();
  });

  it("maps each issue to a readable message on its field", () => {
    const result = fromApiError(
      validationError([
        { path: ["username"], code: "missing", message: "Field required" },
        {
          path: ["password"],
          code: "string_too_short",
          message: "String should have at least 8 characters",
        },
        {
          path: ["firstName"],
          code: "string_too_short",
          message: "String should have at least 1 character",
        },
        {
          path: ["lastName"],
          code: "string_too_long",
          message: "String should have at most 100 characters",
        },
        {
          path: ["username"],
          code: "string_pattern_mismatch",
          message: "String should match pattern",
        },
      ]),
    );
    expect(result).toEqual({
      fieldErrors: {
        username: ["Required", "Use only letters, digits, underscores and periods"],
        password: ["Must be at least 8 characters"],
        firstName: ["Required"],
        lastName: ["Must be at most 100 characters"],
      },
      formError: undefined,
    });
  });

  it("puts issues without a field on the form, first one wins", () => {
    const result = fromApiError(
      validationError([
        {
          path: [],
          code: "value_error",
          message: "Value error, Provide at least one of username, firstName or lastName",
        },
        { path: [], code: "other", message: "Second" },
      ]),
    );
    expect(result).toEqual({
      fieldErrors: {},
      formError: "Provide at least one of username, firstName or lastName",
    });
  });

  it("passes unknown codes through", () => {
    const result = fromApiError(
      validationError([{ path: ["username"], code: "string_type", message: "Input should be a valid string" }]),
    );
    expect(result?.fieldErrors?.username).toEqual(["Input should be a valid string"]);
  });

  it("handles a validation error without details", () => {
    expect(fromApiError({ error: { code: "VALIDATION_ERROR", message: "x" } })).toEqual({
      fieldErrors: {},
      formError: undefined,
    });
  });
});

describe("errorCode", () => {
  it("reads the API error code", () => {
    expect(errorCode({ error: { code: "INVALID_PASSWORD", message: "x" } })).toBe("INVALID_PASSWORD");
  });

  it("is undefined for anything else", () => {
    expect(errorCode(undefined)).toBeUndefined();
    expect(errorCode("boom")).toBeUndefined();
  });
});

describe("asErrors", () => {
  it("wraps messages for shadcn's FieldError", () => {
    expect(asErrors(["a", "b"])).toEqual([{ message: "a" }, { message: "b" }]);
    expect(asErrors(undefined)).toBeUndefined();
  });
});
