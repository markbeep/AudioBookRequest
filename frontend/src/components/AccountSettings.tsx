import { useState, useEffect } from "preact/hooks";
import type { JSX, TargetedEvent } from "preact";

interface APIKey {
  id: string;
  name: string;
  created_at: string;
  last_used: string | null;
  enabled: boolean;
}

export default function AccountSettingsComponent() {
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [newApiKey, setNewApiKey] = useState<string | null>(null);
  const [showNewKey, setShowNewKey] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/account/api-keys", {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to load API keys");
      }
      const data = await response.json();
      setApiKeys(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load API keys");
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordChange = async (e: TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    setChangingPassword(true);
    setError(null);
    setSuccess(null);

    const form = e.currentTarget;
    const formData = new FormData(form);

    const body = {
      old_password: formData.get("old_password") as string,
      new_password: formData.get("password") as string,
      confirm_password: formData.get("confirm_password") as string,
    };

    try {
      const response = await fetch("/api/settings/account/password", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to change password");
      }

      setSuccess("Password changed successfully");
      form.reset();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to change password",
      );
    } finally {
      setChangingPassword(false);
    }
  };

  const handleCreateApiKey = async (e: JSX.TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const form = e.currentTarget;
    const formData = new FormData(form);

    const body = {
      name: formData.get("name") as string,
    };

    try {
      const response = await fetch("/api/settings/account/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to create API key");
      }

      const data = await response.json();
      setNewApiKey(data.key);
      setShowNewKey(true);
      form.reset();
      await loadApiKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create API key");
    }
  };

  const handleToggleApiKey = async (id: string) => {
    setError(null);
    try {
      const response = await fetch(
        `/api/settings/account/api-keys/${id}/toggle`,
        {
          method: "PATCH",
          credentials: "include",
        },
      );

      if (!response.ok) {
        throw new Error("Failed to toggle API key");
      }

      await loadApiKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle API key");
    }
  };

  const handleDeleteApiKey = async (id: string) => {
    if (!confirm("Are you sure you want to delete this API key?")) {
      return;
    }

    setError(null);
    try {
      const response = await fetch(`/api/settings/account/api-keys/${id}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to delete API key");
      }

      setSuccess("API key deleted successfully");
      await loadApiKeys();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete API key");
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setSuccess("API key copied to clipboard");
    } catch (err) {
      setError("Failed to copy to clipboard");
    }
  };

  if (loading) {
    return (
      <div class="flex justify-center items-center p-8">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  return (
    <div class="flex flex-col gap-6">
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

      <form
        id="change-password-form"
        class="flex flex-col gap-2"
        onSubmit={handlePasswordChange}
      >
        <h2 class="text-lg">Change Password</h2>
        <label for="old-password">Old password</label>
        <input
          id="old-password"
          name="old_password"
          type="password"
          class="input w-full"
          required
        />
        <label for="change-password-1">New Password</label>
        <input
          id="change-password-1"
          name="password"
          type="password"
          class="input w-full"
          required
        />
        <label for="change-password-2">Confirm password</label>
        <input
          id="change-password-2"
          name="confirm_password"
          type="password"
          class="input w-full"
          required
        />
        <button
          name="submit"
          class="btn btn-primary"
          type="submit"
          disabled={changingPassword}
        >
          {changingPassword ? (
            <>
              <span class="loading loading-spinner"></span>
              Changing...
            </>
          ) : (
            "Change password"
          )}
        </button>
      </form>

      <hr class="w-48 h-1 mx-auto my-4 bg-gray-100 border-0 rounded-sm md:my-10 dark:bg-gray-700" />

      <div id="api_keys">
        <h2 class="text-lg mb-2">API Keys</h2>
        <p class="text-sm text-gray-600 mb-4">
          API keys allow external applications to access your account.
        </p>

        <form
          id="create-api-key-form"
          class="flex flex-col gap-2 mb-4"
          onSubmit={handleCreateApiKey}
        >
          <div class="flex gap-2">
            <input
              name="name"
              type="text"
              placeholder="API Key Name"
              class="input w-full"
              required
            />
            <button type="submit" class="btn btn-primary">
              Create API Key
            </button>
          </div>
        </form>

        {showNewKey && newApiKey && (
          <div class="card mb-4 shadow-sm dark:border dark:border-gray-700 bg-base-200">
            <div class="flex flex-col card-body gap-2">
              <p>
                <strong>Your new API key:</strong>
              </p>
              <div class="flex gap-2">
                <code class="bg-base-300 p-2 rounded flex-1 break-all">
                  {newApiKey}
                </code>
                <div class="relative">
                  <button
                    type="button"
                    onClick={() => copyToClipboard(newApiKey)}
                    class="btn text-xs transition-all duration-500 min-w-20"
                  >
                    Copy
                  </button>
                </div>
              </div>
              <p class="text-sm text-error">
                <strong>Important:</strong> This is the only time you'll see
                this key. Store it securely!
              </p>
              <button
                type="button"
                class="btn btn-sm"
                onClick={() => {
                  setShowNewKey(false);
                  setNewApiKey(null);
                }}
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {apiKeys.length > 0 ? (
          <div class="overflow-x-auto">
            <table class="table w-full">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Created</th>
                  <th>Last Used</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {apiKeys.map((apiKey) => (
                  <tr key={apiKey.id}>
                    <td>{apiKey.name}</td>
                    <td>
                      {new Date(apiKey.created_at).toLocaleString("en-US", {
                        timeZone: "GMT",
                      })}{" "}
                      GMT
                    </td>
                    <td>
                      {apiKey.last_used
                        ? `${new Date(apiKey.last_used).toLocaleString(
                            "en-US",
                            {
                              timeZone: "GMT",
                            },
                          )} GMT`
                        : "Never"}
                    </td>
                    <td>
                      <span
                        class={`badge ${
                          apiKey.enabled ? "badge-success" : "badge-error"
                        }`}
                      >
                        {apiKey.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </td>
                    <td>
                      <div class="flex gap-2">
                        <button
                          onClick={() => handleToggleApiKey(apiKey.id)}
                          class="btn btn-sm"
                        >
                          {apiKey.enabled ? "Disable" : "Enable"}
                        </button>
                        <button
                          onClick={() => handleDeleteApiKey(apiKey.id)}
                          class="btn btn-sm btn-error"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p class="text-gray-600">No API keys created yet.</p>
        )}
      </div>
    </div>
  );
}
