import { getCurrentUserApiUsersMeGet, type UserResponse } from "@/client";

export async function getUser(headers: Headers): Promise<UserResponse | null> {
  const cookies = headers.get("cookie");
  const authorization = headers.get("authorization");
  if (!cookies && !authorization) {
    return null;
  }
  let user: UserResponse | null = null;
  let error: unknown;

  if (cookies) {
    const session = cookies.match(/(?:^|; )session=([^;]*)/)?.[1];
    const resp = await getCurrentUserApiUsersMeGet({
      headers: {
        Cookie: `session=${session}`,
      },
    });
    user = resp.data ?? null;
    error = resp.error;
    if (!user) {
      console.warn("Authorization using cookie failed", { error });
    }
  }

  if (!user && authorization) {
    const resp = await getCurrentUserApiUsersMeGet({
      headers: {
        Authorization: authorization,
      },
    });
    user = resp.data ?? null;
    error = resp.error;
    if (!user) {
      console.warn("Authorization using header failed", { error });
    }
  }

  if (error) {
    if (error instanceof Error) {
      console.error("Error fetching user:", error.message);
    } else {
      console.error("Unknown error fetching user:", error);
    }
    return null;
  }
  return user ?? null;
}
