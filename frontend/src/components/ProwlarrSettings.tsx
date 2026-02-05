import { useState, useEffect } from "preact/hooks";
import type { JSX } from "preact";

interface ProwlarrSettings {
  base_url: string;
  api_key: string;
  selected_categories: number[];
  selected_indexers: number[];
  all_categories: Record<number, string>;
  indexers: {
    ok: boolean;
    error?: string;
    json_string?: string;
  };
}

export default function ProwlarrSettingsComponent() {
  const [settings, setSettings] = useState<ProwlarrSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedCategories, setSelectedCategories] = useState<number[]>([]);
  const [selectedIndexers, setSelectedIndexers] = useState<number[]>([]);
  const [indexersData, setIndexersData] = useState<
    Record<number, { name: string }>
  >({});

  useEffect(() => {
    loadSettings();
  }, []);

  useEffect(() => {
    if (settings) {
      setSelectedCategories(settings.selected_categories);
      setSelectedIndexers(settings.selected_indexers);
      if (settings.indexers.json_string) {
        try {
          setIndexersData(JSON.parse(settings.indexers.json_string));
        } catch (e) {
          console.error("Failed to parse indexers", e);
        }
      }
    }
  }, [settings]);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/prowlarr", {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to load Prowlarr settings");
      }
      const data = await response.json();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateApiKey = async (e: JSX.TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);
    const apiKey = formData.get("api_key") as string;

    try {
      const response = await fetch("/api/settings/prowlarr/api-key", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ api_key: apiKey }),
      });

      if (!response.ok) {
        throw new Error("Failed to update API key");
      }

      setSuccess("API key updated successfully");
      await loadSettings();
      e.currentTarget.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update API key");
    }
  };

  const handleUpdateBaseUrl = async (e: JSX.TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);
    const baseUrl = formData.get("base_url") as string;

    try {
      const response = await fetch("/api/settings/prowlarr/base-url", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ base_url: baseUrl }),
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

  const handleUpdateCategories = async () => {
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch("/api/settings/prowlarr/categories", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ categories: selectedCategories }),
      });

      if (!response.ok) {
        throw new Error("Failed to update categories");
      }

      setSuccess("Categories updated successfully");
      await loadSettings();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update categories",
      );
    }
  };

  const handleUpdateIndexers = async () => {
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch("/api/settings/prowlarr/indexers", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ indexers: selectedIndexers }),
      });

      if (!response.ok) {
        throw new Error("Failed to update indexers");
      }

      setSuccess("Indexers updated successfully");
      await loadSettings();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update indexers",
      );
    }
  };

  const addCategory = (category: number) => {
    if (!selectedCategories.includes(category)) {
      setSelectedCategories(
        [...selectedCategories, category].sort((a, b) => a - b),
      );
    }
  };

  const removeCategory = (category: number) => {
    setSelectedCategories(selectedCategories.filter((c) => c !== category));
  };

  const addIndexer = (indexerId: number) => {
    if (!selectedIndexers.includes(indexerId)) {
      setSelectedIndexers(
        [...selectedIndexers, indexerId].sort((a, b) => a - b),
      );
    }
  };

  const removeIndexer = (indexerId: number) => {
    setSelectedIndexers(selectedIndexers.filter((i) => i !== indexerId));
  };

  const categoriesChanged = () => {
    if (!settings) return false;
    return (
      JSON.stringify(selectedCategories.sort()) !==
      JSON.stringify(settings.selected_categories.sort())
    );
  };

  const indexersChanged = () => {
    if (!settings) return false;
    return (
      JSON.stringify(selectedIndexers.sort()) !==
      JSON.stringify(settings.selected_indexers.sort())
    );
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

      <label for="prowlarr-api-key">API Key</label>
      <form class="join w-full" onSubmit={handleUpdateApiKey}>
        <input
          id="prowlarr-api-key"
          name="api_key"
          type="password"
          placeholder={settings.api_key ? "●●●●●●●●●●●●●●●●●" : ""}
          class="input join-item w-full"
          minLength={1}
          required
        />
        <button class="join-item btn">
          {settings.api_key ? "Update" : "Add"}
        </button>
      </form>

      <label for="prowlarr-base-url" class="pt-2">
        Base URL
      </label>
      <form class="join w-full" onSubmit={handleUpdateBaseUrl}>
        <input
          id="prowlarr-base-url"
          name="base_url"
          type="url"
          value={settings.base_url}
          class="input join-item w-full"
          minLength={1}
          required
        />
        <button class="join-item btn">
          {settings.base_url ? "Update" : "Add"}
        </button>
      </form>

      <div class="flex flex-col gap-2">
        <label for="categories">Categories</label>
        <p class="text-xs opacity-60">
          Categories to search for using Prowlarr. If none are selected, all
          categories will be searched for.
        </p>
        <div class="flex flex-wrap gap-1">
          {selectedCategories.map((cat) => (
            <div
              key={cat}
              class="badge badge-secondary badge-sm w-[13rem] justify-between h-fit"
            >
              <span>
                {String(cat).padStart(4, "0")} - {settings.all_categories[cat]}
              </span>
              <button
                class="cursor-pointer hover:opacity-70 transition-opacity duration-150"
                onClick={() => removeCategory(cat)}
                type="button"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <select
          id="categories"
          class="select w-full"
          value=""
          onChange={(e) => {
            const value = (e.target as HTMLSelectElement).value;
            if (value) {
              addCategory(Number(value));
              (e.target as HTMLSelectElement).value = "";
            }
          }}
        >
          <option disabled selected value="">
            -- select a category --
          </option>
          {Object.entries(settings.all_categories)
            .filter(([cat]) => !selectedCategories.includes(Number(cat)))
            .map(([cat, name]) => (
              <option key={cat} value={cat}>
                {String(cat).padStart(4, "0")} - {name}
              </option>
            ))}
        </select>
        <button
          class="btn"
          onClick={handleUpdateCategories}
          disabled={!categoriesChanged()}
        >
          Save categories
        </button>
      </div>

      <div class="flex flex-col gap-2">
        <label for="indexers">Indexers</label>
        <p class="text-xs opacity-60">
          Select the indexers to use with Prowlarr. If none are selected, all
          indexers will be used.
          {!settings.indexers.ok && (
            <span class="text-error font-semibold">
              <br />
              No indexers found. {settings.indexers.error || ""}
            </span>
          )}
        </p>
        {settings.indexers.ok && (
          <>
            <div class="flex flex-wrap gap-1">
              {selectedIndexers.map((indexerId) => (
                <div
                  key={indexerId}
                  class="badge badge-secondary badge-sm w-[13rem] justify-between h-fit"
                >
                  <span>{indexersData[indexerId]?.name || indexerId}</span>
                  <button
                    class="cursor-pointer hover:opacity-70 transition-opacity duration-150"
                    onClick={() => removeIndexer(indexerId)}
                    type="button"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <select
              id="indexers"
              class="select w-full"
              value=""
              onChange={(e) => {
                const value = (e.target as HTMLSelectElement).value;
                if (value) {
                  addIndexer(Number(value));
                  (e.target as HTMLSelectElement).value = "";
                }
              }}
            >
              <option disabled selected value="">
                -- select an indexer --
              </option>
              {Object.entries(indexersData)
                .filter(([id]) => !selectedIndexers.includes(Number(id)))
                .map(([id, indexer]) => (
                  <option key={id} value={id}>
                    {indexer.name}
                  </option>
                ))}
            </select>
            <button
              class="btn"
              onClick={handleUpdateIndexers}
              disabled={!indexersChanged()}
            >
              Save indexers
            </button>
          </>
        )}
      </div>
    </div>
  );
}
