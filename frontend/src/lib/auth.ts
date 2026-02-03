import { getCurrentUserApiUsersMeGet, type UserResponse } from "@/client";

export async function getUser(headers: Headers): Promise<UserResponse | null> {
  const cookies = headers.get("cookie");
  if (!cookies) {
    return null;
  }
  const session = cookies.match(/(?:^|; )session=([^;]*)/)?.[1];
  const { data: user, error } = await getCurrentUserApiUsersMeGet({
    headers: {
      Cookie: `session=${session}`,
    },
  });
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
