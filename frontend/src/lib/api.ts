// Configures the generated client (src/api) once, at startup: the backend
// URL, the bearer token, and what a 401 means.
import { client } from "@/api/client.gen";
import { API_URL } from "@/lib/app";
import { getToken, setToken } from "@/lib/token";

client.setConfig({
  baseUrl: API_URL,
  // Only endpoints that declare `bearerAuth` get the header, so the token is
  // never sent to register or login.
  auth: () => getToken() ?? undefined,
});

// A 401 means the token is missing, expired or revoked: forget it, and the
// auth context sends the user to /login. Wrong passwords on the
// password-confirming endpoints are 403s, so they never land here. Login's
// own 401 (wrong credentials) happens without a token and changes nothing.
client.interceptors.response.use((response) => {
  if (response.status === 401 && getToken()) setToken(null);
  return response;
});
