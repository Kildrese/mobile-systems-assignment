import type { Metadata } from "next";
import { DeleteAccount } from "@/components/account/delete-account";
import { EmailForm } from "@/components/account/email-form";
import { PasswordForm } from "@/components/account/password-form";
import { ProfileForm } from "@/components/account/profile-form";
import { requireSession } from "@/lib/session";

export const metadata: Metadata = { title: "Account" };

export default async function AccountPage() {
  const { user } = await requireSession();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Account</h1>
      <ProfileForm firstName={user.firstName} lastName={user.lastName} />
      <EmailForm email={user.email} />
      <PasswordForm />
      <DeleteAccount />
    </div>
  );
}
