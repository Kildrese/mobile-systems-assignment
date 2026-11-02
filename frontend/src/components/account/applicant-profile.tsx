// The applicant profile: four files that drive CV tailoring. Only the owner sees it, and
// only names, sizes and upload time come back, never the contents.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import {
  getProfileOptions,
  getProfileQueryKey,
  uploadProfileMutation,
} from "@/api/@tanstack/react-query.gen";
import { QueryFallback } from "@/components/query-fallback";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/forms";
import { formatRunTime } from "@/lib/run-id";

const FILES = [
  { key: "cvDocx", name: "cv.docx", accept: ".docx" },
  { key: "factBank", name: "fact_bank.yaml", accept: ".yaml,.yml" },
  { key: "rulesMd", name: "rules.md", accept: ".md,.txt" },
  { key: "checksYaml", name: "checks.yaml", accept: ".yaml,.yml" },
] as const;

function size(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export function ApplicantProfile() {
  const queryClient = useQueryClient();
  const profile = useQuery(getProfileOptions());
  const upload = useMutation(uploadProfileMutation());
  const [error, setError] = useState<string>();

  if (!profile.isSuccess) return <QueryFallback query={profile} what="profile" />;
  const { files, uploadedAt, canDraft } = profile.data;
  if (!canDraft && files.length === 0) return null;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const body = Object.fromEntries(FILES.map(({ key }) => [key, data.get(key) as File]));
    setError(undefined);
    upload.mutate(
      { body },
      {
        onSuccess: (stored) => {
          queryClient.setQueryData(getProfileQueryKey(), stored);
          form.reset();
          toast.success("Profile uploaded.");
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Applicant profile</CardTitle>
        <CardDescription>
          Your master CV and the files that tailor it. Only you can see them. Upload all four together.
        </CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit} className="contents">
        <CardContent className="flex flex-col gap-4">
          {files.length > 0 ? (
            <div className="text-sm">
              <p className="text-muted-foreground">
                Uploaded {uploadedAt && formatRunTime(new Date(uploadedAt))}
              </p>
              <ul className="mt-1">
                {files.map((f) => (
                  <li key={f.name}>
                    {f.name} <span className="text-muted-foreground">· {size(f.size)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No profile uploaded yet.</p>
          )}
          {canDraft && (
            <FieldGroup>
              {error && <FieldError>{error}</FieldError>}
              <div className="grid gap-4 sm:grid-cols-2">
                {FILES.map(({ key, name, accept }) => (
                  <Field key={key}>
                    <FieldLabel htmlFor={key}>{name}</FieldLabel>
                    <Input id={key} name={key} type="file" accept={accept} required />
                  </Field>
                ))}
              </div>
            </FieldGroup>
          )}
        </CardContent>
        {canDraft && (
          <CardFooter className="justify-end">
            <Button type="submit" disabled={upload.isPending}>
              {upload.isPending ? "Uploading…" : "Upload profile"}
            </Button>
          </CardFooter>
        )}
      </form>
    </Card>
  );
}
