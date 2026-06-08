import { users } from "./mvp-data";

export type AdminAuthMode = "mock" | "firebase";

export interface AdminSession {
  user: {
    id: string;
    name: string;
    email: string;
    role: string;
    permissions: string[];
    companyId?: string;
  };
  authMode: AdminAuthMode;
  signedIn: boolean;
  claimsReady: boolean;
}

function getAuthMode(): AdminAuthMode {
  return process.env.WULKAN_ADMIN_AUTH_MODE === "firebase" || process.env.WULKAN_AUTH_MODE === "firebase"
    ? "firebase"
    : "mock";
}

export function getMockSession(): AdminSession {
  const user = users[0];

  if (!user) {
    throw new Error("No mock admin user configured.");
  }

  return {
    user,
    authMode: "mock",
    signedIn: true,
    claimsReady: true
  };
}

export function getFirebaseSessionPlaceholder(): AdminSession {
  return {
    user: {
      id: "firebase-session-pending",
      name: "Sesion Firebase pendiente",
      email: "auth@wulkan.local",
      role: "pending",
      permissions: [],
    },
    authMode: "firebase",
    signedIn: false,
    claimsReady: false
  };
}

export function getAdminSession(): AdminSession {
  return getAuthMode() === "firebase" ? getFirebaseSessionPlaceholder() : getMockSession();
}
