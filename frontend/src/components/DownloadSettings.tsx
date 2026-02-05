import { useState, useEffect } from "preact/hooks";
import type { TargetedEvent } from "preact";

interface QualityRange {
  from_kbits: number;
  to_kbits: number;
}

interface IndexerFlag {
  flag: string;
  score: number;
}

interface DownloadSettings {
  auto_download: boolean;
  flac_range: QualityRange;
  m4b_range: QualityRange;
  mp3_range: QualityRange;
  unknown_audio_range: QualityRange;
  unknown_range: QualityRange;
  min_seeders: number;
  name_ratio: number;
  title_ratio: number;
  indexer_flags: IndexerFlag[];
}

export default function DownloadSettingsComponent() {
  const [settings, setSettings] = useState<DownloadSettings | null>(null);
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
    try {
      const response = await fetch("/api/settings/download", {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to load download settings");
      }
      const data = await response.json();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: TargetedEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!settings) return;

    setSaving(true);
    setError(null);
    setSuccess(null);

    const form = e.currentTarget;
    const formData = new FormData(form);

    const body = {
      auto_download: formData.get("auto_download") === "on",
      flac_range: {
        from_kbits: parseInt(formData.get("flac_from") as string) || 0,
        to_kbits: parseInt(formData.get("flac_to") as string) || 1000,
      },
      m4b_range: {
        from_kbits: parseInt(formData.get("m4b_from") as string) || 0,
        to_kbits: parseInt(formData.get("m4b_to") as string) || 1000,
      },
      mp3_range: {
        from_kbits: parseInt(formData.get("mp3_from") as string) || 0,
        to_kbits: parseInt(formData.get("mp3_to") as string) || 1000,
      },
      unknown_audio_range: {
        from_kbits: parseInt(formData.get("unknown_audio_from") as string) || 0,
        to_kbits: parseInt(formData.get("unknown_audio_to") as string) || 1000,
      },
      unknown_range: {
        from_kbits: parseInt(formData.get("unknown_from") as string) || 0,
        to_kbits: parseInt(formData.get("unknown_to") as string) || 1000,
      },
      min_seeders: parseInt(formData.get("min_seeders") as string) || 0,
      name_ratio: parseInt(formData.get("name_ratio") as string) || 75,
      title_ratio: parseInt(formData.get("title_ratio") as string) || 90,
    };

    try {
      const response = await fetch("/api/settings/download", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error("Failed to save settings");
      }

      setSuccess("Settings saved successfully");
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Are you sure you want to reset download settings?")) {
      return;
    }

    try {
      const response = await fetch("/api/settings/download", {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to reset settings");
      }

      setSuccess("Settings reset successfully");
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset settings");
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
        <div class="w-full flex items-center justify-between gap-2 border-t pt-2 border-base-200">
          <label for="auto-download">Auto Download</label>
          <input
            id="auto-download"
            name="auto_download"
            type="checkbox"
            class="checkbox"
            checked={settings.auto_download}
          />
        </div>

        <h3 class="border-t pt-2 border-base-200">
          Quality <span class="text-xs">(kbit/s)</span>
        </h3>

        <div>
          <label for="flac-from">FLAC</label>
          <div class="flex w-full items-center gap-2">
            <input
              id="flac-from"
              name="flac_from"
              type="number"
              class="input w-full"
              value={
                settings.flac_range.from_kbits >= 1000
                  ? "Infinity"
                  : settings.flac_range.from_kbits
              }
              placeholder="0"
            />
            <span>-</span>
            <input
              id="flac-to"
              name="flac_to"
              type="number"
              class="input w-full"
              value={
                settings.flac_range.to_kbits >= 1000
                  ? "Infinity"
                  : settings.flac_range.to_kbits
              }
              placeholder="1000"
            />
          </div>
        </div>

        <div>
          <label for="m4b-from">M4B</label>
          <div class="flex w-full items-center gap-2">
            <input
              id="m4b-from"
              name="m4b_from"
              type="number"
              class="input w-full"
              value={
                settings.m4b_range.from_kbits >= 1000
                  ? "Infinity"
                  : settings.m4b_range.from_kbits
              }
              placeholder="0"
            />
            <span>-</span>
            <input
              id="m4b-to"
              name="m4b_to"
              type="number"
              class="input w-full"
              value={
                settings.m4b_range.to_kbits >= 1000
                  ? "Infinity"
                  : settings.m4b_range.to_kbits
              }
              placeholder="1000"
            />
          </div>
        </div>

        <div>
          <label for="mp3-from">MP3</label>
          <div class="flex w-full items-center gap-2">
            <input
              id="mp3-from"
              name="mp3_from"
              type="number"
              class="input w-full"
              value={
                settings.mp3_range.from_kbits >= 1000
                  ? "Infinity"
                  : settings.mp3_range.from_kbits
              }
              placeholder="0"
            />
            <span>-</span>
            <input
              id="mp3-to"
              name="mp3_to"
              type="number"
              class="input w-full"
              value={
                settings.mp3_range.to_kbits >= 1000
                  ? "Infinity"
                  : settings.mp3_range.to_kbits
              }
              placeholder="1000"
            />
          </div>
        </div>

        <div>
          <label for="unknown_audio-from">Unknown Audio</label>
          <div class="flex w-full items-center gap-2">
            <input
              id="unknown_audio-from"
              name="unknown_audio_from"
              type="number"
              class="input w-full"
              value={
                settings.unknown_audio_range.from_kbits >= 1000
                  ? "Infinity"
                  : settings.unknown_audio_range.from_kbits
              }
              placeholder="0"
            />
            <span>-</span>
            <input
              id="unknown_audio-to"
              name="unknown_audio_to"
              type="number"
              class="input w-full"
              value={
                settings.unknown_audio_range.to_kbits >= 1000
                  ? "Infinity"
                  : settings.unknown_audio_range.to_kbits
              }
              placeholder="1000"
            />
          </div>
        </div>

        <div>
          <label for="unknown-from">Unknown</label>
          <div class="flex w-full items-center gap-2">
            <input
              id="unknown-from"
              name="unknown_from"
              type="number"
              class="input w-full"
              value={
                settings.unknown_range.from_kbits >= 1000
                  ? "Infinity"
                  : settings.unknown_range.from_kbits
              }
              placeholder="0"
            />
            <span>-</span>
            <input
              id="unknown-to"
              name="unknown_to"
              type="number"
              class="input w-full"
              value={
                settings.unknown_range.to_kbits >= 1000
                  ? "Infinity"
                  : settings.unknown_range.to_kbits
              }
              placeholder="1000"
            />
          </div>
        </div>

        <div class="w-full flex items-center justify-between">
          <label for="min-seeders">Min Seeders</label>
          <input
            id="min-seeders"
            name="min_seeders"
            type="number"
            class="input"
            placeholder="2"
            value={settings.min_seeders}
          />
        </div>

        <div class="w-full flex items-center justify-between">
          <label for="name-ratio">Author/Narrator Similarity Ratio</label>
          <input
            id="name-ratio"
            name="name_ratio"
            type="number"
            class="input"
            placeholder="75"
            value={settings.name_ratio}
          />
        </div>

        <div class="w-full flex items-center justify-between">
          <label for="title-ratio">Title Similarity Ratio</label>
          <input
            id="title-ratio"
            name="title_ratio"
            type="number"
            class="input"
            placeholder="90"
            value={settings.title_ratio}
          />
        </div>

        <button
          id="save-button"
          type="submit"
          class="btn btn-primary"
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

      <hr class="my-4 border-base-200" />

      <div class="flex flex-col gap-2">
        <h3 class="text-lg">Indexer Flags</h3>
        {settings.indexer_flags.length > 0 ? (
          <table class="table">
            <thead>
              <tr>
                <th>Flag</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {settings.indexer_flags.map((flag) => (
                <tr key={flag.flag}>
                  <td>{flag.flag}</td>
                  <td>{flag.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p class="text-sm opacity-60">No indexer flags configured</p>
        )}
      </div>

      <hr class="my-4 border-base-200" />

      <div class="flex flex-col gap-2">
        <h2 class="text-lg text-error">Danger Zone</h2>
        <button type="button" class="btn btn-error" onClick={handleReset}>
          Reset download settings
        </button>
      </div>
    </div>
  );
}
