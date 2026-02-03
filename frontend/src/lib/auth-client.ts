export async function signOut() {
  await fetch("/api/auth/signout", {
    method: "POST",
  });

  // Clear all cookies
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0].trim();
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
  });

  window.location.href = "/api/auth/login";
}

export async function signIn() {
  window.location.href = "/api/auth/login";
}
