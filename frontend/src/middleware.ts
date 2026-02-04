import { getLoginTypeApiAuthTypeGet } from "@/client";
import { getUser } from "@/lib/auth";
import { ABR_INTERNAL__API_PORT } from "astro:env/client";
import { defineMiddleware } from "astro:middleware";

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

  // Handle api on fastapi side
  if (
    pathname.startsWith("/api") ||
    pathname.startsWith("/docs") ||
    pathname.startsWith("/openapi.json")
  ) {
    const apiPort = ABR_INTERNAL__API_PORT || "42456";
    const apiUrl = `http://localhost:${apiPort}`;
    return proxyRequest(context.request, apiUrl);
  }

  const { data: loginType } = await getLoginTypeApiAuthTypeGet();
  context.locals.loginType = loginType?.login_type ?? null;

  const user = await getUser(
    context.request.headers,
    loginType?.login_type === "none",
  );
  if (user) {
    // user is already logged in, redirect to root
    if (pathname.startsWith("/auth")) {
      return context.redirect("/");
    }

    context.locals.user = user;
    return next();
  }

  // user is not authenticated, allow to pass through auth endpoints without redirection
  if (pathname.startsWith("/auth")) {
    return next();
  }

  // check if basic auth is enabled. Return error to get browser to use basic auth
  if (loginType?.login_type === "basic") {
    return new Response("Invalid credentials", {
      status: 401,
      headers: { "WWW-Authenticate": "Basic" },
    });
  }

  const redirectUri = pathname.replace(/^\/+/, "");
  if (redirectUri) {
    return context.redirect(
      `/auth/login?redirect_uri=${encodeURIComponent(redirectUri)}`,
    );
  }
  return context.redirect("/auth/login");
});
