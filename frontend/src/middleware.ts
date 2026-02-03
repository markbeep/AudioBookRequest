import { getUser } from "@/lib/auth";
import { ABR_INTERNAL__API_PORT } from "astro:env/client";
import { defineMiddleware, sequence } from "astro:middleware";

export const auth = defineMiddleware(async (context, next) => {
  const pathname = new URL(context.request.url).pathname;

  // Pass through /auth requests without modification
  if (pathname.startsWith("/auth")) {
    return next();
  }

  // Forward /api requests to the backend API
  if (
    pathname.startsWith("/api") ||
    pathname.startsWith("/docs") ||
    pathname.startsWith("/openapi.json")
  ) {
    const apiPort = ABR_INTERNAL__API_PORT || "42456";
    const url = new URL(context.request.url);
    const apiUrl = `http://localhost:${apiPort}${pathname}${url.search}`;

    // Forward the request to the backend API
    const response = await fetch(apiUrl, {
      method: context.request.method,
      body: context.request.body,
      headers: context.request.headers,
    });

    const headers = new Headers(response.headers);
    headers.delete("content-encoding");
    headers.delete("content-length");
    headers.set(
      "content-length",
      Buffer.byteLength(await response.clone().arrayBuffer()).toString(),
    );

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  }

  // TODO: if not logged in, redirect to /login
  const user = await getUser(context.request.headers);
  context.locals.user = user;

  return next();
});

/**
 * Compress responses using gzip or deflate
 * TODO: astro static files are not compressed as they
 * don't go through the middleware
 */
const compress = defineMiddleware(async (context, next) => {
  const response = await next();
  const accept = context.request.headers.get("accept-encoding") || "";
  const alreadyEncoded = response.headers.get("content-encoding");

  let body: BodyInit | null | undefined = response.body;
  let encoding: string | null = null;
  if (!alreadyEncoded && accept.includes("gzip")) {
    body = response.body?.pipeThrough(new CompressionStream("gzip"));
    encoding = "gzip";
  } else if (!alreadyEncoded && accept.includes("deflate")) {
    body = response.body?.pipeThrough(new CompressionStream("deflate"));
    encoding = "deflate";
  }

  if (encoding) {
    return new Response(body, {
      ...response,
      headers: {
        ...response.headers,
        "Content-Encoding": encoding,
      },
    });
  }

  return response;
});

export const onRequest = sequence(auth, compress);
