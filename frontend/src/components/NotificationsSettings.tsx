import { useState, useEffect } from "preact/hooks";
import type { JSX } from "preact";

interface Notification {
  id: string;
  name: string;
  url: string;
  event: string;
  body: string;
  body_type: string;
  headers: Record<string, string>;
  enabled: boolean;
  serialized_headers: string;
}

const EVENT_TYPES = [
  "book_requested",
  "book_downloaded",
  "book_failed",
  "book_approved",
  "book_denied",
];

const BODY_TYPES = ["json", "text"];

export default function NotificationsSettingsComponent() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => {
    loadNotifications();
  }, []);

  const loadNotifications = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/settings/notifications", {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Failed to load notifications");
      }
      const data = await response.json();
      setNotifications(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load notifications",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCreateNotification = async (
    e: JSX.TargetedEvent<HTMLFormElement>,
  ) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);
    const body = {
      name: formData.get("name") as string,
      url: formData.get("url") as string,
      event_type: formData.get("event_type") as string,
      body: formData.get("body") as string,
      body_type: formData.get("body_type") as string,
      headers: (formData.get("headers") as string) || "{}",
    };

    try {
      const response = await fetch("/api/settings/notifications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to create notification");
      }

      setSuccess("Notification created successfully");
      e.currentTarget.reset();
      await loadNotifications();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create notification",
      );
    }
  };

  const handleUpdateNotification = async (
    e: JSX.TargetedEvent<HTMLFormElement>,
    id: string,
  ) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(e.currentTarget);
    const body = {
      id,
      name: formData.get("name") as string,
      url: formData.get("url") as string,
      event_type: formData.get("event_type") as string,
      body: formData.get("body") as string,
      body_type: formData.get("body_type") as string,
      headers: (formData.get("headers") as string) || "{}",
    };

    try {
      const response = await fetch("/api/settings/notifications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to update notification");
      }

      setSuccess("Notification updated successfully");
      setEditingId(null);
      await loadNotifications();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update notification",
      );
    }
  };

  const handleDeleteNotification = async (id: string) => {
    if (!confirm("Are you sure you want to delete this notification?")) {
      return;
    }

    setError(null);
    try {
      const response = await fetch(`/api/settings/notifications/${id}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to delete notification");
      }

      setSuccess("Notification deleted successfully");
      await loadNotifications();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete notification",
      );
    }
  };

  const handleToggleNotification = async (id: string) => {
    setError(null);
    try {
      const response = await fetch(`/api/settings/notifications/${id}/enable`, {
        method: "PATCH",
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Failed to toggle notification");
      }

      await loadNotifications();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to toggle notification",
      );
    }
  };

  const handleTestNotification = async (id: string) => {
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch(`/api/settings/notifications/${id}/test`, {
        method: "POST",
        credentials: "include",
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to test notification");
      }

      setSuccess("Test notification sent successfully");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to test notification",
      );
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

      <form
        id="add-notification-form"
        class="flex flex-col gap-2"
        onSubmit={handleCreateNotification}
      >
        <label for="name">
          Name<span class="text-error">*</span>
        </label>
        <input
          id="name"
          name="name"
          minLength={1}
          type="text"
          class="input w-full"
          required
        />

        <label for="event">
          Event<span class="text-error">*</span>
        </label>
        <select id="event" name="event_type" class="select w-full" required>
          {EVENT_TYPES.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>

        <label for="url" class="flex gap-0 flex-col">
          <span>
            Notification URL<span class="text-error">*</span>
          </span>
          <br />
          <span class="text-xs font-mono">(http://.../notify/c2h3fg...)</span>
        </label>
        <input
          id="url"
          name="url"
          minLength={1}
          type="text"
          class="input w-full"
          required
        />

        <label for="body_type">
          Body Type<span class="text-error">*</span>
        </label>
        <select id="body_type" name="body_type" class="select w-full" required>
          {BODY_TYPES.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>

        <label for="body">
          Body<span class="text-error">*</span>
        </label>
        <textarea
          id="body"
          required
          name="body"
          class="textarea w-full font-mono"
          placeholder='{"eventType": {"book": "{bookTitle}"}}'
        />

        <label for="headers">
          Headers
          <span class="text-xs">(JSON format, optional)</span>
        </label>
        <input
          id="headers"
          name="headers"
          type="text"
          class="input w-full font-mono"
          placeholder='{"username": "admin", "password": "password123"}'
        />

        <p class="flex flex-col text-xs opacity-60">
          Possible event variables:
          <span class="font-mono">
            eventType, eventUser, eventUserExtraData, bookTitle, bookAuthors,
            bookNarrators, bookASIN, torrentInfoHash, sourceSizeMB, sourceTitle,
            indexerName, sourceProtocol
          </span>
          <span class="mt-1">Failed download event additionally has:</span>
          <span class="font-mono">errorStatus, errorReason</span>
        </p>
        <button type="submit" class="btn btn-primary">
          Add
        </button>
      </form>

      <div class="pt-4 border-t border-base-200 mt-4">
        <h2 class="text-lg mb-4">Apprise Notifications</h2>
        <div class="max-h-[30rem] overflow-x-auto">
          <table class="table table-pin-rows">
            <thead>
              <tr>
                <th></th>
                <th>Name</th>
                <th>Event</th>
                <th>URL</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((n, index) => (
                <tr key={n.id}>
                  <th>{index + 1}</th>
                  <td>{n.name}</td>
                  <td>{n.event}</td>
                  <td class="truncate max-w-xs">{n.url}</td>
                  <td class="grid grid-cols-2 min-w-[8rem] gap-1">
                    <button
                      title="Test"
                      class="btn btn-square btn-sm"
                      onClick={() => handleTestNotification(n.id)}
                    >
                      🧪
                    </button>
                    <button
                      title="Edit"
                      class="btn btn-square btn-sm"
                      onClick={() =>
                        setEditingId(editingId === n.id ? null : n.id)
                      }
                    >
                      ✏️
                    </button>
                    <button
                      title={n.enabled ? "Enabled" : "Disabled"}
                      class={`btn btn-square btn-sm ${n.enabled ? "btn-success" : "btn-error"}`}
                      onClick={() => handleToggleNotification(n.id)}
                    >
                      {n.enabled ? "✓" : "✕"}
                    </button>
                    <button
                      title="Delete"
                      class="btn btn-error btn-square btn-sm"
                      onClick={() => handleDeleteNotification(n.id)}
                    >
                      🗑️
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {notifications.map(
          (n) =>
            editingId === n.id && (
              <form
                key={n.id}
                class="flex flex-col gap-2 mt-4 p-4 border border-base-300 rounded"
                onSubmit={(e) => handleUpdateNotification(e, n.id)}
              >
                <h3 class="text-lg">Edit: {n.name}</h3>
                <label for={`name-edit-${n.id}`}>
                  Name<span class="text-error">*</span>
                </label>
                <input
                  id={`name-edit-${n.id}`}
                  name="name"
                  minLength={1}
                  type="text"
                  class="input w-full"
                  defaultValue={n.name}
                  required
                />

                <label for={`event-edit-${n.id}`}>
                  Event<span class="text-error">*</span>
                </label>
                <select
                  id={`event-edit-${n.id}`}
                  name="event_type"
                  class="select w-full"
                  defaultValue={n.event}
                  required
                >
                  {EVENT_TYPES.map((e) => (
                    <option key={e} value={e}>
                      {e}
                    </option>
                  ))}
                </select>

                <label for={`url-edit-${n.id}`}>
                  Notification URL<span class="text-error">*</span>
                  <br />
                  <span class="text-xs font-mono">
                    (http://.../notify/c2h3fg...)
                  </span>
                </label>
                <input
                  id={`url-edit-${n.id}`}
                  name="url"
                  minLength={1}
                  type="text"
                  class="input w-full"
                  defaultValue={n.url}
                  required
                />

                <label for={`body_type-edit-${n.id}`}>
                  Body Type<span class="text-error">*</span>
                </label>
                <select
                  id={`body_type-edit-${n.id}`}
                  name="body_type"
                  class="select w-full"
                  defaultValue={n.body_type}
                  required
                >
                  {BODY_TYPES.map((e) => (
                    <option key={e} value={e}>
                      {e}
                    </option>
                  ))}
                </select>

                <label for={`body-edit-${n.id}`}>
                  Body<span class="text-error">*</span>
                </label>
                <textarea
                  id={`body-edit-${n.id}`}
                  required
                  name="body"
                  class="textarea w-full font-mono"
                  defaultValue={n.body}
                />

                <label for={`headers-edit-${n.id}`}>
                  Headers
                  <span class="text-xs font-mono">(JSON format, optional)</span>
                </label>
                <input
                  id={`headers-edit-${n.id}`}
                  name="headers"
                  type="text"
                  class="input w-full font-mono"
                  defaultValue={n.serialized_headers}
                />

                <div class="flex gap-2">
                  <button type="submit" class="btn btn-primary">
                    Update
                  </button>
                  <button
                    type="button"
                    class="btn"
                    onClick={() => setEditingId(null)}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            ),
        )}
      </div>
    </div>
  );
}
