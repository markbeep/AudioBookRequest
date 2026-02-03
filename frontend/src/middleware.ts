import { defineMiddleware } from "astro:middleware";

/**
 * Compress responses using gzip or deflate
 * TODO: astro static files are not compressed as they
 * don't go through the middleware
 */
export const onRequest = defineMiddleware(async (context, next) => {
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
