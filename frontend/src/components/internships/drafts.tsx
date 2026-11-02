// Application drafts on an offer card: the owner's own and those shared with the viewer.
// Check details and letter text are rendered as text, never HTML.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, FileText } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { createDraftMutation, listDraftsQueryKey } from "@/api/@tanstack/react-query.gen";
import { downloadDraftCv, downloadDraftLetter } from "@/api/sdk.gen";
import type { Draft, InternshipOffer } from "@/api/types.gen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/forms";

const STATUS = {
  pending: { label: "Drafting…", variant: "outline" },
  ready: { label: "Draft ready", variant: "secondary" },
  partial: { label: "Partial draft", variant: "outline" },
  failed: { label: "Draft failed", variant: "destructive" },
} as const;

function safe(text: string): string {
  return text.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

// Fetched through the client (it needs the bearer header), then saved as a file.
async function save(draft: Draft, offer: InternshipOffer, kind: "cv" | "letter") {
  const fetchFile = kind === "cv" ? downloadDraftCv : downloadDraftLetter;
  const { data, error } = await fetchFile({ path: { id: draft.id }, parseAs: "blob" });
  if (error || !(data instanceof Blob)) {
    toast.error("The file couldn't be downloaded.");
    return;
  }
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safe(offer.company)}_${safe(offer.title)}_${kind === "cv" ? "CV" : "Cover_Letter"}.docx`;
  link.click();
  URL.revokeObjectURL(url);
}

function DraftRow({ draft, offer }: { draft: Draft; offer: InternshipOffer }) {
  const { label, variant } = STATUS[draft.status];
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={variant}>{label}</Badge>
        {!draft.mine && <span className="text-muted-foreground">by {draft.owner}</span>}
        {draft.profileOutdated && (
          <span className="text-muted-foreground">made with an older profile</span>
        )}
        {draft.hasCv && (
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => void save(draft, offer, "cv")}>
            <Download data-icon="inline-start" />
            Download CV
          </Button>
        )}
        {draft.hasLetter && (
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => void save(draft, offer, "letter")}>
            <FileText data-icon="inline-start" />
            Download cover letter
          </Button>
        )}
        {draft.letterText && (
          <Button
            variant="ghost"
            size="sm"
            className="cursor-pointer"
            onClick={() =>
              void navigator.clipboard
                .writeText(draft.letterText ?? "")
                .then(() => toast.success("Letter text copied."))
            }
          >
            <Copy data-icon="inline-start" />
            Copy letter text
          </Button>
        )}
      </div>
      {draft.error && <p className="text-muted-foreground">{draft.error}</p>}
      {draft.checks.length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted-foreground">
            Checks ({draft.checks.length})
          </summary>
          <ul className="mt-1 list-disc pl-5">
            {draft.checks.map((c, i) => (
              <li key={i}>
                {c.name} ({c.outcome}): {c.detail}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function OfferDrafts({
  offer,
  drafts,
  canDraft,
}: {
  offer: InternshipOffer;
  drafts: Draft[];
  canDraft: boolean;
}) {
  const queryClient = useQueryClient();
  const create = useMutation(createDraftMutation());
  const [letter, setLetter] = useState(false);
  const mine = drafts.find((d) => d.mine);

  if (!canDraft && drafts.length === 0 && !offer.deadlinePassed) return null;

  function draft() {
    create.mutate(
      { body: { opportunityId: offer.opportunityId, coverLetter: letter } },
      {
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: listDraftsQueryKey() }),
        onError: (err) => toast.error(errorMessage(err)),
      },
    );
  }

  return (
    <div className="flex flex-col gap-2 border-t pt-2 text-sm">
      {drafts.map((d) => (
        <DraftRow key={d.id} draft={d} offer={offer} />
      ))}
      {offer.deadlinePassed ? (
        <p className="text-muted-foreground">Deadline passed</p>
      ) : (
        canDraft && (
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" className="cursor-pointer" disabled={create.isPending} onClick={draft}>
              {create.isPending ? "Drafting… (up to two minutes)" : mine ? "Draft again" : "Draft application"}
            </Button>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={letter} onChange={(e) => setLetter(e.target.checked)} />
              Include cover letter
            </label>
          </div>
        )
      )}
    </div>
  );
}
