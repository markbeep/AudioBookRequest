---
title: OpenID Connect
description: Setting up OIDC login
---

OIDC allows you to use the same login across multiple apps. This guide will show
you how to set up OIDC with Authentik, but the concepts are the same or similar
for other providers.

## Setup a provider on Authentik

1.  You want to first create an application on Authentik. The settings here
    don't play a role for AudioBookRequest though.

2.  You then want to create an OAuth2/OpenID Provider:

    ![Authentik OIDC](authentik-oidc.png)

3.  Configure the settings as preferred. The important two values are the
    `Client ID` and `Client Secret`. Take note of those. You should also set the
    redirect URL that the OIDC provider will redirect you to after a succesful
    login. This has to be the domain of your ABR instance with `/auth/oidc`
    appended. If you access ABR through multiple URLs (e.g., local VPN and
    external domain), add **all** of them as separate redirect URIs in your
    provider.

    ![Authentik Provider](authentik-provider.png)

4.  Set the scopes that ABR can get access to. You should always allow for the
    `openid` scope. Any other scopes are optional. You'll have to check with
    your OIDC provider to see what what scopes are required to get a
    name/username and groups. "Subject mode" is a unique identifier for the
    user. This can be used as the username on ABR.

    ![Authentik Scopes](authentik-scopes.png)

5.  Assign your newly created provider to the ABR application.

## Reverse Proxy Configuration

If you access AudioBookRequest through a reverse proxy (Nginx, Traefik, Caddy, etc.), it automatically works! The protocol (http/https) is detected from the proxy headers.

### How It Works

When behind a reverse proxy with SSL termination:
1. External users access: `https://domain.com`
2. Reverse proxy forwards to ABR: `http://backend:8000` (terminates SSL)
3. Proxy sends `X-Forwarded-Proto: https` header
4. ABR automatically reads this and generates correct OIDC redirect URIs

### Default Behavior (No Configuration Needed)

By default, AudioBookRequest **allows all proxy IPs** (`0.0.0.0/0`) for compatibility:
- ✅ Works out-of-the-box for all reverse proxies
- ✅ Great for home labs and self-hosted setups
- ⚠️ Less secure on shared infrastructure (susceptible to header spoofing)

If you see this warning in your logs:
```
🔐 SECURITY WARNING: Proxy headers detected (X-Forwarded-Proto) but
FORWARDED_ALLOW_IPS is set to allow all IPs (0.0.0.0/0).
```

It means you should configure specific proxy IPs for security.

### Secure Setup (Recommended for Production)

To only trust your reverse proxy, configure `FORWARDED_ALLOW_IPS`:

Find your proxy's IP address:
```bash
docker exec audiobookrequest ip route | grep default
# Output: default via 172.17.0.1 dev eth0
```

Set it in docker-compose:
```yaml
# docker-compose.yml
services:
  abr:
    image: ghcr.io/markbeep/audiobookrequest:latest
    environment:
      - FORWARDED_ALLOW_IPS=172.17.0.1
```

**Multiple proxies:** `FORWARDED_ALLOW_IPS=172.17.0.1,10.0.0.1`

**IP ranges:** `FORWARDED_ALLOW_IPS=172.17.0.0/16`

**Kubernetes:**
```yaml
env:
  - name: FORWARDED_ALLOW_IPS
    value: "10.96.0.0/16"  # Service CIDR
```

### Ensure Proxy Sends Headers

### Configure OIDC Provider with Multiple Redirect URIs

In Authentik (or your OIDC provider), add **ALL** redirect URIs you'll use:
- `http://192.168.1.100:8000/auth/oidc` (local VPN access)
- `https://external.domain.com/auth/oidc` (external access)
- `http://localhost:8000/auth/oidc` (development)

ABR automatically uses the correct one based on how you accessed the login page!

{{< alert color="success" title="Automatic Detection" >}}
Protocol (http/https) is now detected automatically - no manual configuration in ABR settings!
{{< /alert >}}

{{< alert color="warning" title="Security Note" >}}
For production, use `FORWARDED_ALLOW_IPS` to only trust specific proxy IPs. This prevents header spoofing attacks.
{{< /alert >}}

## Setup settings in ABR

1. On AudioBookRequest, head to `Settings>Security` and set the "Login Type" to
   "OpenID Connect".
2. Paste the "Client ID" and "Client Secret" into the respective fields.
3. Your "OIDC Configuration Endpoint" depends on the OIDC provider you use. For
   Authentik, it's usually along the lines of
   https://domain.com/application/o/audiobookrequest/.well-known/openid-configuration.
   You'll have to find that for your own provider. Visiting the url should give
   you a JSON-formatted object with different endpoints and details given.
4. The "OIDC Scopes" are the ones defined above separated by a space. `openid`
   is always required. Any other scopes like `email` or `group` are only
   required if you intend to use the email for the username or respectively
   extract the group of the user.
5. "OIDC Username Claim" **has to be a unique identifier** which is used as the
   username for the user. `sub` is always available, but you might prefere to
   use `email` or `username` (with the correctly added scope).
6. _Optional_: The "OIDC Logout URL" is where you're redirected if you select to
   log out in ABR. OIDC Providers allow you to invalidate the session on this
   URL. While this value is optional, not adding it might break logging out
   slightly because the session can't properly be invalidated.

   {{< alert color="info" title="Protocol Detection" >}}
   The protocol (http/https) is now detected automatically from incoming requests!
   No manual configuration needed. {{< /alert >}}

## Groups

"OIDC Group Claim" is optional, but allows you to handle the role distribution
of users in your OIDC provider instead of in ABR. The exact claim that sends
along the information depends on your OIDC provider. The OIDC provider can
provide a single string or list of strings.

The groups have to be named exactly one of `untrusted`, `trusted`, or `admin`.
The letter case does not matter.

{{< alert >}} For Authentik, the group claim name is `groups` and requires the
`profile` scope. If you assign a user to a group named `trusted`, that user will
receive the `Trusted` role once they login to AudioBookRequest. {{< /alert >}}
