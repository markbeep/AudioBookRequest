import { useState, useEffect } from "preact/hooks";
import type { JSX } from "preact";

interface ABSLibrary {
  id: string;
  name: string;
  mediaType: string;
}

interface ABSSettings {
  abs_base_url: string;
  abs_api_token: string;
  abs_library_id: string;
  abs_check_downloaded: boolean;
  abs_libraries: ABSLibrary[];
}

export default function AudiobookshelfSettingsComponent() {
  const [settings, setSettings] = useState<ABSSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/audiobookshelf", {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to load Audiobookshelf settings");
      }
      const data = await response.json();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateApiToken = async (
    e: JSX.TargetedEvent<HTMLFormElement>,
  ) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);

    try {
      const response = await fetch("/api/settings/audiobookshelf/api-token", {
        method: "PUT",
        body: formData,
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to update API token");
      }

      setSuccess("API token updated successfully");
      await loadSettings();
      e.currentTarget.reset();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update API token",
      );
    }
  };

  const handleUpdateBaseUrl = async (e: JSX.TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);

    try {
      const response = await fetch("/api/settings/audiobookshelf/base-url", {
        method: "PUT",
        body: formData,
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to update base URL");
      }

      setSuccess("Base URL updated successfully");
      await loadSettings();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update base URL",
      );
    }
  };

  const handleUpdateLibrary = async (e: JSX.TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);

    try {
      const response = await fetch("/api/settings/audiobookshelf/library", {
        method: "PUT",
        body: formData,
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to update library");
      }

      setSuccess("Library updated successfully");
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update library");
    }
  };

  const handleToggleCheckDownloaded = async (
    e: JSX.TargetedEvent<HTMLInputElement>,
  ) => {
    setError(null);
    setSuccess(null);

    const checked = e.currentTarget.checked;
    const formData = new FormData();
    formData.append("check_downloaded", checked ? "true" : "false");

    try {
      const response = await fetch(
        "/api/settings/audiobookshelf/check-downloaded",
        {
          method: "PUT",
          body: formData,
          credentials: "include",
        },
      );

      if (!response.ok) {
        throw new Error("Failed to update check downloaded setting");
      }

      setSuccess("Setting updated successfully");
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update setting");
    }
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
    <div class="flex flex-col gap-2">
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

      <label for="abs-api-token">API Token</label>
      <form class="join w-full" onSubmit={handleUpdateApiToken}>
        <input
          id="abs-api-token"
          name="api_token"
          type="password"
          placeholder={settings.abs_api_token ? "●●●●●●●●●●●●●●●●●" : ""}
          class="input join-item w-full"
          minLength={1}
          required
        />
        <button class="join-item btn">
          {settings.abs_api_token ? "Update" : "Add"}
        </button>
      </form>

      <label for="abs-base-url" class="pt-2">
        Base URL
      </label>
      <form class="join w-full" onSubmit={handleUpdateBaseUrl}>
        <input
          id="abs-base-url"
          name="base_url"
          type="url"
          value={settings.abs_base_url}
          class="input join-item w-full"
          minLength={1}
          required
        />
        <button class="join-item btn">
          {settings.abs_base_url ? "Update" : "Add"}
        </button>
      </form>

      <label for="abs-library" class="pt-2">
        Library
      </label>
      <form class="join w-full" onSubmit={handleUpdateLibrary}>
        <select
          id="abs-library"
          name="library_id"
          class="select join-item w-full"
          value={settings.abs_library_id}
        >
          {!settings.abs_libraries || settings.abs_libraries.length === 0 ? (
            <option disabled selected>
              Enter URL and API token first
            </option>
          ) : (
            settings.abs_libraries.map((lib) => (
              <option
                key={lib.id}
                value={lib.id}
                selected={settings.abs_library_id === lib.id}
              >
                {lib.name} ({lib.mediaType})
              </option>
            ))
          )}
        </select>
        <button class="join-item btn">Save</button>
      </form>

      <div class="form-control pt-4">
        <label class="label cursor-pointer">
          <span class="label-text">
            Use ABS to mark existing books as downloaded
          </span>
          <input
            type="checkbox"
            class="toggle"
            checked={settings.abs_check_downloaded}
            onChange={handleToggleCheckDownloaded}
          />
        </label>
        <p class="text-xs opacity-60">
          When enabled, search results will be checked against Audiobookshelf
          and marked as downloaded if found to avoid duplicate requests. Will
          likely make search and recommendations slower as they are checked
          against ABS.
        </p>
      </div>
    </div>
  );
}
