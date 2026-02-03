import { createClient } from "@/client/client";

export const client = createClient({ baseUrl: import.meta.env.BASE_URL });
