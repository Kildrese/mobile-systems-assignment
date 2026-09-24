import { useMutation } from "@tanstack/react-query";
import { LogOutIcon, UserIcon } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { logoutMutation } from "@/api/@tanstack/react-query.gen";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth, useUser } from "@/lib/use-auth";

export function UserMenu() {
  const { username, firstName, lastName, email } = useUser();
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const logout = useMutation(logoutMutation());
  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();

  // Revokes the token on the server, then forgets it and goes to /login,
  // even when the server call fails (the token may already be gone).
  function onSignOut() {
    logout.mutate(
      {},
      {
        onSettled: () => {
          signOut();
          navigate("/login", { replace: true });
        },
      },
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-auto gap-2 px-2 py-1">
          <Avatar className="size-7">
            <AvatarFallback className="text-xs">{initials}</AvatarFallback>
          </Avatar>
          <span className="hidden text-sm font-medium sm:inline">{firstName}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="flex flex-col font-normal">
          <span className="font-medium text-foreground">
            {[firstName, lastName].filter(Boolean).join(" ")}
          </span>
          <span className="truncate text-xs text-muted-foreground">@{username}</span>
          {email && <span className="truncate text-xs text-muted-foreground">{email}</span>}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/account">
            <UserIcon />
            Account
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={logout.isPending} onSelect={onSignOut}>
          <LogOutIcon />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
