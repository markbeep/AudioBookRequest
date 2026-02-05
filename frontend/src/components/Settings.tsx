import { useState, useEffect } from "preact/hooks";
import AccountSettingsComponent from "@/components/AccountSettings";
import SecuritySettingsComponent from "@/components/SecuritySettings";
import DownloadSettingsComponent from "@/components/DownloadSettings";
import ProwlarrSettingsComponent from "@/components/ProwlarrSettings";
import AudiobookshelfSettingsComponent from "@/components/AudiobookshelfSettings";
import NotificationsSettingsComponent from "@/components/NotificationsSettings";
import { getCurrentUserApiUsersMeGet } from "@/client";

type SettingsTab =
  | "account"
  | "security"
  | "download"
  | "prowlarr"
  | "audiobookshelf"
  | "notifications";

export default function SettingsComponent() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("account");
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAdminAccess();
  }, []);

  const checkAdminAccess = async () => {
    setLoading(true);
    const { data: user, error } = await getCurrentUserApiUsersMeGet();
    if (user?.group === "admin") {
      setIsAdmin(true);
    }

    try {
      // Try to access an admin-only endpoint to check if user is admin
      const response = await fetch("/api/settings/security", {
        credentials: "include",
      });

      // If we can access security settings, user is admin
      setIsAdmin(response.ok);
    } catch (err) {
      setIsAdmin(false);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div class="flex justify-center items-center p-8">
        <span class="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Non-admin users only see account settings
  if (!isAdmin) {
    return (
      <div class="flex flex-col gap-6">
        <div class="mb-6">
          <h1 class="text-2xl font-bold mb-2">Account Settings</h1>
          <p class="text-base-content/70">
            Manage your password and API keys for external access.
          </p>
        </div>
        <AccountSettingsComponent />
      </div>
    );
  }

  // Admin users see all settings with tabs
  return (
    <div class="flex flex-col gap-6">
      <div role="tablist" class="tabs tabs-boxed">
        <button
          role="tab"
          class={`tab ${activeTab === "account" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("account")}
        >
          Account
        </button>
        <button
          role="tab"
          class={`tab ${activeTab === "prowlarr" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("prowlarr")}
        >
          Prowlarr
        </button>
        <button
          role="tab"
          class={`tab ${activeTab === "audiobookshelf" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("audiobookshelf")}
        >
          Audiobookshelf
        </button>
        <button
          role="tab"
          class={`tab ${activeTab === "download" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("download")}
        >
          Download
        </button>
        <button
          role="tab"
          class={`tab ${activeTab === "notifications" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("notifications")}
        >
          Notifications
        </button>
        <button
          role="tab"
          class={`tab ${activeTab === "security" ? "tab-active" : ""}`}
          onClick={() => setActiveTab("security")}
        >
          Security
        </button>
      </div>

      <div class="flex flex-col">
        <div class={activeTab === "account" ? "" : "hidden"}>
          <h2 class="text-lg mb-4">Account Settings</h2>
          <AccountSettingsComponent />
        </div>
        <div class={activeTab === "security" ? "" : "hidden"}>
          <h2 class="text-lg mb-4">Security Settings</h2>
          <SecuritySettingsComponent />
        </div>
        <div class={activeTab === "download" ? "" : "hidden"}>
          <h2 class="text-lg mb-4">Download Settings</h2>
          <DownloadSettingsComponent />
        </div>
        <div class={activeTab === "prowlarr" ? "" : "hidden"}>
          <h2 class="text-lg mb-4">Prowlarr Settings</h2>
          <ProwlarrSettingsComponent />
        </div>
        <div class={activeTab === "audiobookshelf" ? "" : "hidden"}>
          <h2 class="text-lg mb-4">Audiobookshelf Settings</h2>
          <AudiobookshelfSettingsComponent />
        </div>
        <div class={activeTab === "notifications" ? "" : "hidden"}>
          <h2 class="text-lg mb-4">Notification Settings</h2>
          <NotificationsSettingsComponent />
        </div>
      </div>
    </div>
  );
}
