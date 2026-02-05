import {
  createInitAuthInitPost,
  logoutAuthLogoutPost,
  type LoginTypeEnum,
} from "@/client";

export async function signOut() {
  const { data } = await logoutAuthLogoutPost();

  // Clear all cookies
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0].trim();
    if (name !== "session") return;
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
  });

  if (data?.redirect) {
    window.location.href = data.redirect;
    return;
  }

  signIn();
}

export function signIn() {
  const currentPath = window.location.pathname + window.location.search;
  const redirectUrl = encodeURIComponent(currentPath);
  window.location.href = `/auth/login?redirect=${redirectUrl}`;
}

/**
 * Initializes the root user on the backend. Only possible if the instance hasn't
 * been initialized yet.
 *
 * @returns the error as a string if there is one, null otherwise.
 */
export async function initRootUser({
  loginType,
  username,
  password,
}: {
  loginType: LoginTypeEnum;
  username: string;
  password: string;
}): Promise<string | null> {
  const { error } = await createInitAuthInitPost({
    body: {
      login_type: loginType,
      username,
      password,
    },
  });
  if (!error) return null;
  const joinedError = error.detail?.join(",");
  return joinedError ?? "Unknown error";
}
