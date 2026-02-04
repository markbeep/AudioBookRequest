import { useState, useEffect } from "preact/hooks";
import {
  getSecuritySettingsApiSettingsSecurityGet,
  updateSecuritySettingsApiSettingsSecurityPatch,
  resetAuthSecretApiSettingsSecurityResetAuthPost,
  type SecuritySettings,
  type LoginTypeEnum,
} from "@/client";
import { client } from "@/lib/client";

export default function SecuritySettingsComponent() {
  const [settings, setSettings] = useState<SecuritySettings | null>(null);
  const [loginType, setLoginType] = useState<LoginTypeEnum>("none");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    const { data, error: err } = await getSecuritySettingsApiSettingsSecurityGet({
      client,
    });

    if (err) {
      setError("Failed to load security settings");
      setLoading(false);
      return;
    }

    if (data) {
      setSettings(data);
      setLoginType(data.login_type);
    }
    setLoading(false);
  };

  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);

    const form = e.target as HTMLFormElement;
    const formData = new FormData(form);

    const body = {
      login_type: formData.get("login_type") as LoginTypeEnum,
      access_token_expiry: formData.get("access_token_expiry")
        ? parseInt(formData.get("access_token_expiry") as string)
        : undefined,
      min_password_length: formData.get("min_password_length")
        ? parseInt(formData.get("min_password_length") as string)
        : undefined,
      oidc_endpoint: formData.get("oidc_endpoint") as string | undefined,
      oidc_client_id: formData.get("oidc_client_id") as string | undefined,
      oidc_client_secret: formData.get("oidc_client_secret") as string | undefined,
      oidc_scope: formData.get("oidc_scope") as string | undefined,
      oidc_username_claim: formData.get("oidc_username_claim") as string | undefined,
      oidc_group_claim: formData.get("oidc_group_claim") as string | undefined,
      oidc_redirect_https: formData.get("oidc_redirect_https") === "true",
      oidc_logout_url: formData.get("oidc_logout_url") as string | undefined,
    };

    const { error: err } = await updateSecuritySettingsApiSettingsSecurityPatch({
      client,
      body,
    });

    if (err) {
      setError(err.detail?.toString() || "Failed to save settings");
      setSaving(false);
      return;
    }

    setSuccess("Settings saved successfully");
    setSaving(false);
    await loadSettings();
  };

  const handleResetAuth = async () => {
    if (
      !confirm(
        "Are you sure you want to reset the authentication secret? This will invalidate everyone's login session forcing them to log in again."
      )
    ) {
      return;
    }

    const { error: err } = await resetAuthSecretApiSettingsSecurityResetAuthPost({
      client,
    });

    if (err) {
      setError("Failed to reset authentication secret");
      return;
    }

    setSuccess("Authentication secret reset successfully");
  };

  if (loading) {
    return (
      <div class="flex justify-center items-center p-8">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (!settings) {
    return (
      <div class="alert alert-error">
        <span>Failed to load settings</span>
      </div>
    );
  }

  return (
    <div class="flex flex-col">
      {error && (
        <div class="alert alert-error mb-4">
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div class="alert alert-success mb-4">
          <span>{success}</span>
        </div>
      )}

      <form class="flex flex-col gap-2" onSubmit={handleSubmit}>
        <h2 class="text-lg">Login/Security</h2>

        <label for="login-type">Login Type</label>
        <select
          id="login-type"
          name="login_type"
          class="select w-full"
          value={loginType}
          onChange={(e) => setLoginType((e.target as HTMLSelectElement).value as LoginTypeEnum)}
          disabled={settings.force_login_type !== null}
        >
          <option value="basic">Basic Auth (Dialog)</option>
          <option value="forms">Forms Login</option>
          <option value="oidc">OpenID Connect</option>
          <option value="none">None (Insecure)</option>
        </select>
        {settings.force_login_type && (
          <p class="text-xs opacity-60">
            Login type is forced by the environment variable{" "}
            <code>ABR_APP__FORCE_LOGIN_TYPE</code>.
          </p>
        )}

        {loginType === "forms" && (
          <>
            <label for="expiry-input">Access Token Expiry (minutes)</label>
            <input
              id="expiry-input"
              type="number"
              name="access_token_expiry"
              class="input w-full"
              defaultValue={settings.access_token_expiry}
            />
          </>
        )}

        {(loginType === "forms" || loginType === "basic") && (
          <>
            <label for="pw-len-input">Minimum Password Length</label>
            <input
              id="pw-len-input"
              type="number"
              name="min_password_length"
              class="input w-full"
              placeholder="1"
              defaultValue={settings.min_password_length}
            />
          </>
        )}

        {loginType === "oidc" && (
          <>
            <label for="oidc-client-id">
              OIDC Client ID <span class="text-error">*</span>
            </label>
            <input
              id="oidc-client-id"
              required
              type="text"
              autocomplete="off"
              name="oidc_client_id"
              class="input w-full"
              defaultValue={settings.oidc_client_id}
            />

            <label for="oidc-client-secret">
              OIDC Client Secret <span class="text-error">*</span>
            </label>
            <input
              id="oidc-client-secret"
              required
              type="text"
              autocomplete="off"
              name="oidc_client_secret"
              class="input w-full"
              defaultValue={settings.oidc_client_secret}
            />

            <div>
              <label for="oidc-endpoint">
                OIDC Configuration Endpoint
                <span class="text-error">*</span>
              </label>
              <p class="opacity-60 text-xs">
                The <span class="font-mono">.well-known/openid-configuration</span>{" "}
                endpoint containing all the OIDC information. You should be able to
                visit the page and view it yourself.
              </p>
            </div>
            <input
              id="oidc-endpoint"
              required
              type="text"
              placeholder="https://example.com/.well-known/openid-configuration"
              name="oidc_endpoint"
              class="input w-full"
              defaultValue={settings.oidc_endpoint}
            />

            <div>
              <label for="oidc-scope">
                OIDC Scopes <span class="text-error">*</span>
              </label>
              <p class="opacity-60 text-xs">
                The scopes that will be requested from the OIDC provider. "openid"
                is almost always required. Add the scopes required to fetch the
                username and group claims.
              </p>
            </div>
            <input
              id="oidc-scope"
              required
              type="text"
              placeholder="openid profile"
              autocomplete="off"
              name="oidc_scope"
              class="input w-full"
              defaultValue={settings.oidc_scope}
            />

            <div>
              <label for="oidc-username-claim">
                OIDC Username Claim <span class="text-error">*</span>
              </label>
              <p class="opacity-60 text-xs">
                The claim that will be used for the username. Make sure the
                respective scope is passed along above. For example some services
                expect the "email" claim to be able to use the email. "sub" is
                always available. You can head to the OIDC endpoint to see what
                claims are available.
              </p>
            </div>
            <input
              id="oidc-username-claim"
              required
              type="text"
              autocomplete="off"
              placeholder="sub"
              name="oidc_username_claim"
              class="input w-full"
              defaultValue={settings.oidc_username_claim}
            />

            <div>
              <label for="oidc-group-claim">OIDC Group Claim</label>
              <p class="opacity-60 text-xs">
                The claim that contains the group(s) the user is in. For example, if
                a user is in the group "trusted" they will be assigned the Trusted
                role here. The group claim can be a list of groups or a single one
                and is case-insensitive.
              </p>
            </div>
            <input
              id="oidc-group-claim"
              type="text"
              autocomplete="off"
              placeholder="group"
              name="oidc_group_claim"
              class="input w-full"
              defaultValue={settings.oidc_group_claim}
            />

            <div>
              <label for="oidc-redirect-https">
                Use http or https for the redirect URL
              </label>
              <p class="opacity-60 text-xs">
                After you login on your authentication server, you will be
                redirected to <span class="font-mono">/auth/oidc</span>. Determine
                if you should be redirected to http or https. This should match up
                with what you configured as the redirect URL in your OIDC provider.
              </p>
            </div>
            <select class="select" name="oidc_redirect_https">
              <option value="true" selected={settings.oidc_redirect_https}>
                https
              </option>
              <option value="false" selected={!settings.oidc_redirect_https}>
                http
              </option>
            </select>

            <div>
              <label for="oidc-logout-url">OIDC Logout URL</label>
              <p class="opacity-60 text-xs">
                The link you'll be redirected to upon logging out. If your OIDC
                provider has the <span class="font-mono">end_session_endpoint</span>{" "}
                defined, it'll use that as the logout url.
              </p>
            </div>
            <input
              id="oidc-logout-url"
              type="text"
              autocomplete="off"
              name="oidc_logout_url"
              class="input w-full"
              defaultValue={settings.oidc_logout_url}
            />

            <p class="text-error text-xs">
              Make sure all the settings are correct. In the case of a
              misconfiguration, you can log in at{" "}
              <a href="/login?backup=1" class="font-mono link whitespace-nowrap inline-block">
                /login?backup=1
              </a>{" "}
              to fix the settings.
              <br />
              <span class="font-semibold">Note:</span> To test your OpenID Connect
              settings you have to log out to invalidate your current session first.
            </p>
          </>
        )}

        <button
          id="save-button"
          name="submit"
          class="btn btn-primary"
          type="submit"
          disabled={saving}
        >
          {saving ? (
            <>
              <span class="loading loading-spinner"></span>
              Saving...
            </>
          ) : (
            "Save"
          )}
        </button>
      </form>

      <hr class="my-8 border-base-200" />

      <div class="flex flex-col gap-2">
        <h2 class="text-lg text-error">Danger Zone</h2>
        <button
          type="button"
          class="btn btn-error"
          onClick={handleResetAuth}
        >
          Reset Authentication Secret (invalidates all logins)
        </button>
      </div>
    </div>
  );
}
