import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { deleteUserMutation } from "@/api/@tanstack/react-query.gen";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth, useUser } from "@/lib/use-auth";
import { SOMETHING_WENT_WRONG } from "@/lib/forms";

export function DeleteAccount() {
  const { id } = useUser();
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const remove = useMutation(deleteUserMutation());

  function onConfirm() {
    remove.mutate(
      { path: { id } },
      {
        onSuccess: () => {
          signOut();
          navigate("/login", { replace: true });
        },
        onError: () => toast.error(SOMETHING_WENT_WRONG),
      },
    );
  }

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle>Danger zone</CardTitle>
        <CardDescription>Permanently delete your account and sign out everywhere.</CardDescription>
      </CardHeader>
      <CardFooter className="justify-end">
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive">Delete account</Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete your account?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently deletes your account and signs you out on every device. It
                can&apos;t be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              {/* A plain button, not AlertDialogAction, which would close the
                  dialog before the request finishes. */}
              <Button variant="destructive" disabled={remove.isPending} onClick={onConfirm}>
                {remove.isPending ? "Deleting…" : "Delete account"}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardFooter>
    </Card>
  );
}
