const host = "com.makeepoch.vault_updater";
const alarm = "makeepoch-local-update";

export async function isMakeEpochLocalBuild() {
  try {
    const response = await fetch(chrome.runtime.getURL("makeepoch-local.json"));
    return response.ok && (await response.json()).channel === "local";
  } catch {
    return false;
  }
}

export async function localUpdateRequest(operation: "status" | "stage" | "apply") {
  const response: { ok: boolean; state?: string } = await chrome.runtime.sendNativeMessage(host, {
    operation,
    version: chrome.runtime.getManifest().version,
  });
  if (!response.ok) {
    throw new Error("MakeEpoch local updater failed");
  }
  return response.state;
}

export function registerLocalUpdateChecks(startup: Promise<unknown>) {
  if (
    typeof chrome.idle?.queryState !== "function" ||
    typeof chrome.runtime.getContexts !== "function"
  ) {
    return;
  }

  const allowedToReload = async () =>
    (await chrome.idle.queryState(60)) !== "active" &&
    (
      await chrome.runtime.getContexts({
        contextTypes: ["POPUP", "TAB", "SIDE_PANEL"] as chrome.runtime.ContextType[],
      })
    ).length === 0;

  const localInstallation = isMakeEpochLocalBuild()
    .then(
      async (enabled) =>
        enabled && (await chrome.management.getSelf()).installType === "development",
    )
    .catch(() => false);
  let checking = false;
  const check = async () => {
    if (checking) {
      return;
    }
    checking = true;
    try {
      await startup;
      if (
        !(await localInstallation) ||
        !(await chrome.permissions.contains({ permissions: ["nativeMessaging"] })) ||
        !(await allowedToReload()) ||
        (await localUpdateRequest("stage")) !== "ready" ||
        !(await allowedToReload())
      ) {
        return;
      }

      if ((await localUpdateRequest("apply")) === "installed") {
        chrome.runtime.reload();
      }
    } catch {
      // A missing host or temporary download failure is retried on the next idle check.
    } finally {
      checking = false;
    }
  };

  chrome.alarms.onAlarm.addListener((event) => {
    if (event.name === alarm) {
      void check();
    }
  });
  void localInstallation
    .then(async (enabled) => {
      if (!enabled) {
        await chrome.alarms.clear(alarm);
      } else if (!(await chrome.alarms.get(alarm))) {
        await chrome.alarms.create(alarm, { delayInMinutes: 2, periodInMinutes: 120 });
      }
    })
    .catch(() => {});
}
