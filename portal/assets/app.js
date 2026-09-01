"use strict";

(function () {
  var SERVER_CONFIG = "=0nI9sWYnZ2Yll1bPl1V3FmQ6hzRiZ2bytEWLl2R4pkTS1GZ15UUykkc4hDcQJnI6ISeltmIsIiI6ISawFmIsICdl5mLzRnbhRHb1NnbvNmchJmbpNnLlR3btVmciojI5FGblJnIsICdl5mLzRnbhRHb1NnbvNmchJmbpNnLlR3btVmciojI0N3boJye";
  var DOWNLOADS = Object.freeze({
    windows: Object.freeze({
      x86_64: "/download/windows/x64",
      arm64: "/download/windows/arm64"
    }),
    macos: Object.freeze({
      x86_64: "/download/macos/intel",
      arm64: "/download/macos/apple-silicon"
    })
  });

  var startButton = document.getElementById("start-support");
  var startButtonDetail = document.getElementById("start-button-detail");
  var deviceSummary = document.getElementById("device-summary");
  var launchStatus = document.getElementById("launch-status");
  var statusMessage = document.getElementById("status-message");
  var assistantDialog = document.getElementById("assistant-dialog");
  var dialogKicker = document.getElementById("dialog-kicker");
  var dialogTitle = document.getElementById("dialog-title");
  var dialogDescription = document.getElementById("dialog-description");
  var platformInstructions = document.getElementById("platform-instructions");
  var macPermissionNote = document.getElementById("mac-permission-note");
  var copyConfigButton = document.getElementById("copy-config");
  var downloadLinks = Array.prototype.slice.call(
    document.querySelectorAll(".installer-link")
  );

  var platform = detectPlatform();
  var architecturePromise = detectArchitecture(platform);

  configureDevicePresentation(platform);

  startButton.addEventListener("click", startSupport);
  copyConfigButton.addEventListener("click", copyServerConfiguration);

  downloadLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      setStatus("Download started. Open the file from your Downloads folder.", "success");
    });
  });

  assistantDialog.addEventListener("close", function () {
    startButton.focus();
  });

  function detectPlatform() {
    var rawPlatform = "";

    if (navigator.userAgentData && typeof navigator.userAgentData.platform === "string") {
      rawPlatform = navigator.userAgentData.platform;
    } else {
      rawPlatform = navigator.platform || navigator.userAgent || "";
    }

    if (/windows|win32|win64/i.test(rawPlatform)) {
      return "windows";
    }

    if (
      /macintosh|macintel|macos|mac/i.test(rawPlatform) &&
      !(navigator.maxTouchPoints > 1)
    ) {
      return "macos";
    }

    return "unknown";
  }

  async function detectArchitecture(currentPlatform) {
    if (currentPlatform === "unknown") {
      return "unknown";
    }

    if (
      navigator.userAgentData &&
      typeof navigator.userAgentData.getHighEntropyValues === "function"
    ) {
      try {
        var hints = await navigator.userAgentData.getHighEntropyValues(["architecture", "bitness"]);
        var architecture = String(hints.architecture || "").toLowerCase();
        var bitness = String(hints.bitness || "").toLowerCase();

        if (architecture.indexOf("arm") !== -1) {
          return "arm64";
        }

        if (architecture.indexOf("x86") !== -1 || bitness === "64") {
          return "x86_64";
        }
      } catch (error) {
        return "unknown";
      }
    }

    return "unknown";
  }

  function configureDevicePresentation(currentPlatform) {
    downloadLinks.forEach(function (link) {
      link.classList.remove("recommended");
    });

    if (currentPlatform === "windows") {
      deviceSummary.textContent = "Windows device detected";
      startButtonDetail.textContent = "Download secure support for Windows";
      document.getElementById("windows-x64").classList.add("recommended");
      document.getElementById("windows-arm64").classList.add("recommended");
      return;
    }

    if (currentPlatform === "macos") {
      deviceSummary.textContent = "Mac detected";
      startButtonDetail.textContent = "Choose the correct Mac download";
      document.getElementById("macos-arm64").classList.add("recommended");
      document.getElementById("macos-x64").classList.add("recommended");
      return;
    }

    deviceSummary.textContent = "Windows or macOS is required";
    startButtonDetail.textContent = "View supported download options";
  }

  async function startSupport() {
    startButton.disabled = true;
    startButton.setAttribute("aria-busy", "true");

    try {
      var architecture = await architecturePromise;

      if (platform === "windows") {
        var windowsArchitecture = architecture === "arm64" ? "arm64" : "x86_64";
        showInstructions("windows");
        beginDownload(DOWNLOADS.windows[windowsArchitecture]);
        return;
      }

      if (platform === "macos" && (architecture === "arm64" || architecture === "x86_64")) {
        showInstructions("macos");
        beginDownload(DOWNLOADS.macos[architecture]);
        return;
      }

      if (platform === "macos") {
        setStatus("Choose Apple silicon or Intel in the download window.", "success");
        showInstructions("macos");
        return;
      }

      setStatus("Choose the correct Windows or Mac download.", "success");
      showInstructions("unknown");
    } finally {
      startButton.disabled = false;
      startButton.setAttribute("aria-busy", "false");
    }
  }

  function beginDownload(url) {
    if (!isAllowedDownload(url)) {
      throw new Error("Blocked unexpected download URL");
    }

    setStatus("Download started. Open the file from your Downloads folder.", "success");
    window.location.assign(url);
  }

  function isAllowedDownload(url) {
    return Object.keys(DOWNLOADS).some(function (platformName) {
      return Object.keys(DOWNLOADS[platformName]).some(function (architectureName) {
        return DOWNLOADS[platformName][architectureName] === url;
      });
    });
  }

  function showInstructions(currentPlatform) {
    configureDevicePresentation(currentPlatform);
    copyConfigButton.hidden = currentPlatform !== "macos";
    macPermissionNote.hidden = currentPlatform !== "macos";

    if (currentPlatform === "windows") {
      dialogKicker.textContent = "Windows download";
      dialogTitle.textContent = "Open the downloaded EXE";
      dialogDescription.textContent = "Confirm that Windows shows PURSLANE as the publisher, approve the prompt, and share the one-time RustDesk code with your Sinbar technician.";
      platformInstructions.textContent = "Windows: Open the EXE and approve the security prompt. RustDesk starts without installing a permanent support service.";
    } else if (currentPlatform === "macos") {
      dialogKicker.textContent = "Mac download";
      dialogTitle.textContent = "Install and configure RustDesk";
      dialogDescription.textContent = "Choose Apple silicon or Intel, open the DMG, and move RustDesk to Applications.";
      platformInstructions.textContent = "Mac: Launch RustDesk, open Settings → Network, unlock the settings, choose Import Server Config, and paste the copied Sinbar configuration.";
    } else {
      dialogKicker.textContent = "Choose your computer";
      dialogTitle.textContent = "Select the correct secure download";
      dialogDescription.textContent = "Choose Windows x64, Windows ARM64, Mac Apple silicon, or Mac Intel.";
      platformInstructions.textContent = "If you are unsure which option applies, ask your Sinbar technician before opening a file.";
    }

    if (typeof assistantDialog.showModal === "function") {
      if (!assistantDialog.open) {
        assistantDialog.showModal();
      }
    } else {
      assistantDialog.setAttribute("open", "");
    }
  }

  async function copyServerConfiguration() {
    if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
      setStatus("Clipboard access is unavailable. Ask your Sinbar technician to provide the server configuration.", "error");
      return;
    }

    try {
      await navigator.clipboard.writeText(SERVER_CONFIG);
      copyConfigButton.textContent = "Configuration copied";
      setStatus("Sinbar server configuration copied. Paste it into RustDesk Import Server Config.", "success");
    } catch (error) {
      setStatus("The browser blocked clipboard access. Ask your Sinbar technician for the configuration.", "error");
    }
  }

  function setStatus(message, state) {
    launchStatus.hidden = false;
    launchStatus.classList.remove("error", "success");

    if (state === "error" || state === "success") {
      launchStatus.classList.add(state);
    }

    statusMessage.textContent = message;
  }
}());
