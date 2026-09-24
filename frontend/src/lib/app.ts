export const APP_NAME = "Mobile Systems";

export const PUBLIC_PAGES = new Set(["/login", "/register"]);

// The backend's origin (see .env.example).
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
