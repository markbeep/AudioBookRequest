import type { APIRoute } from "astro";

export const GET = (async ({ params }) => {
  if (!params.path) {
    return new Response("Not found", { status: 404 });
  }
  const path = params.path.replace(/\/+$/, ""); // remove trailing slashes
  console.log(params);
  return new Response();
}) satisfies APIRoute;
