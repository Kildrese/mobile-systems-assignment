// Builds the OpenAPI 3.1 document from the contracts. Like contracts.ts, this
// only imports `zod` and `zod-openapi`, so it runs without a server or DB.
import {
  createDocument,
  type ZodOpenApiOperationObject,
  type ZodOpenApiPathsObject,
  type ZodOpenApiResponsesObject,
} from "zod-openapi";
import { contracts, type Contract } from "./contracts";

function toOperation(contract: Contract): ZodOpenApiOperationObject {
  const responses: ZodOpenApiResponsesObject = {};
  for (const [status, spec] of Object.entries(contract.responses)) {
    responses[status as `${1 | 2 | 3 | 4 | 5}${string}`] = spec.schema
      ? {
          description: spec.description,
          content: { "application/json": { schema: spec.schema } },
        }
      : { description: spec.description };
  }

  return {
    operationId: contract.operationId,
    summary: contract.summary,
    tags: contract.tags,
    ...(contract.auth ? { security: [{ bearerAuth: [] }] } : {}),
    ...(contract.params ? { requestParams: { path: contract.params } } : {}),
    ...(contract.body
      ? {
          requestBody: {
            required: true,
            content: { "application/json": { schema: contract.body } },
          },
        }
      : {}),
    responses,
  };
}

export function buildOpenApiDocument() {
  const paths: ZodOpenApiPathsObject = {};
  for (const contract of contracts) {
    paths[contract.path] = {
      ...paths[contract.path],
      [contract.method]: toOperation(contract),
    };
  }

  return createDocument({
    openapi: "3.1.0",
    info: {
      title: "Mobile Systems API",
      version: "0.1.0",
      description:
        "JSON API for accounts and users. Log in with `POST /api/auth/login`, then send the token as `Authorization: Bearer <token>`.",
    },
    tags: [{ name: "Health" }, { name: "Auth" }, { name: "Users" }],
    components: {
      securitySchemes: {
        bearerAuth: {
          type: "http",
          scheme: "bearer",
          description: "The `token` returned by `POST /api/auth/login`.",
        },
      },
    },
    paths,
  });
}
