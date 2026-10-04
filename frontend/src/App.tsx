import { Navigate, Route, Routes } from "react-router";
import { PublicOnly, RequireAuth } from "@/routes/guards";
import { AppLayout, PublicLayout } from "@/routes/layouts";
import {
  AccountPage,
  HomePage,
  InternshipsPage,
  LoginPage,
  RegisterPage,
} from "@/routes/pages";

export function App() {
  return (
    <Routes>
      <Route element={<PublicOnly />}>
        <Route element={<PublicLayout />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>
      </Route>
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/internships" element={<InternshipsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
