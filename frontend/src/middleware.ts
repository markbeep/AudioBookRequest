import { getUser } from "@/lib/auth";
import { ABR_INTERNAL__API_PORT } from "astro:env/client";
import { defineMiddleware, sequence } from "astro:middleware";

async function proxyRequest(request: Request, targetBaseUrl: string) {
  const url = new URL(request.url);
  const target = new URL(url.pathname + url.search, targetBaseUrl);

  const upstreamResponse = await fetch(target, {
    method: request.method,
    headers: request.headers,
    body: request.body,
    // @ts-expect-error - duplex is required for streaming bodies
    duplex: "half",
  });

  const headers = new Headers(upstreamResponse.headers);
  headers.delete("content-encoding");
  headers.delete("content-length");

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers,
  });
}

export const onRequest = defineMiddleware(async (context, next) => {
  const pathname = new URL(context.request.url).pathname;

  // Handle auth (api/auth) and api on fastapi side
  if (
    pathname.startsWith("/api") ||
    pathname.startsWith("/docs") ||
    pathname.startsWith("/openapi.json")
  ) {
    const apiPort = ABR_INTERNAL__API_PORT || "42456";
    const apiUrl = `http://localhost:${apiPort}`;
    return proxyRequest(context.request, apiUrl);
  }

  const user = await getUser(context.request.headers);
  if (user) {
    context.locals.user = user;
    return next();
  }

  if (pathname.startsWith("/auth")) {
    return next();
  }

  return context.redirect("/auth/login");
});
