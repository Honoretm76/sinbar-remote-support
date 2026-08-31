"use strict";

(function () {
  var SESSION_ENDPOINT = "/api/v1/support/sessions";
  var SESSION_TIMEOUT_MS = 10000;
  var FALLBACK_DELAY_MS = 4200;
  // The server issues exactly 32 random bytes encoded as unpadded base64url
  // (43 characters) for a fixed 120-second lifetime. Allow a small clock/
  // transport margin when validating expiresAt, but reject every other shape.
  var MAX_SESSION_LIFETIME_MS = 3 * 60 * 1000;
  var TOKEN_PATTERN = /^[A-Za-z0-9_-]{43}$/;
  var PROTOCOL_PATTERN = /^sinbarsupport:\/\/start\?token=([A-Za-z0-9_-]{43})$/;
  var INSTALLERS = Object.freeze({
    windows: "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe",
    macos: "/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg"
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
  var windowsInstaller = document.getElementById("windows-installer");
  var macosInstaller = document.getElementById("macos-installer");
  var macPermissionNote = document.getElementById("mac-permission-note");
  var tryAgainButton = document.getElementById("try-again");

  var platform = detectPlatform();
  var architecturePromise = detectArchitecture(platform);
  var fallbackTimer = null;
  var launchInProgress = false;

  configureDevicePresentation(platform);

  startButton.addEventListener("click", startSupport);
  tryAgainButton.addEventListener("click", function () {
    closeDialog();
    startSupport();
  });

  [windowsInstaller, macosInstaller].forEach(function (link) {
    link.addEventListener("click", function () {
      setStatus(
        "The installer download has started. Open it from your Downloads folder and approve the operating-system prompt.",
        "success"
      );
    });
  });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden" && fallbackTimer !== null) {
      window.clearTimeout(fallbackTimer);
      fallbackTimer = null;
      setStatus("Sinbar Support was opened. Follow the instructions in the assistant.", "success");
    }
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
    windowsInstaller.classList.remove("recommended");
    macosInstaller.classList.remove("recommended");
    macPermissionNote.hidden = currentPlatform !== "macos";

    if (currentPlatform === "windows") {
      deviceSummary.textContent = "Windows device detected";
      startButtonDetail.textContent = "Open Sinbar Support for Windows";
      windowsInstaller.classList.add("recommended");
      return;
    }

    if (currentPlatform === "macos") {
      deviceSummary.textContent = "Mac detected";
      startButtonDetail.textContent = "Open Sinbar Support for macOS";
      macosInstaller.classList.add("recommended");
      return;
    }

    deviceSummary.textContent = "Windows or macOS is required";
    startButtonDetail.textContent = "View supported installation options";
  }

  async function startSupport() {
    if (launchInProgress) {
      return;
    }

    if (platform === "unknown") {
      setStatus("This device could not be identified as Windows or macOS.", "error");
      showFallback("unsupported");
      return;
    }

    launchInProgress = true;
    setLoading(true);
    setStatus("Creating a secure, one-time support session…", "loading");

    try {
      var architecture = await architecturePromise;
      var session = await createSession(platform, architecture);

      setStatus("Secure session ready. Approve the browser prompt to open Sinbar Support.", "success");
      scheduleFallback();
      openRegisteredAssistant(session.protocolUrl);
    } catch (error) {
      clearFallbackTimer();
      setStatus("We could not start a secure session. You can install the assistant below, then try again.", "error");
      showFallback("session-error");
    } finally {
      launchInProgress = false;
      setLoading(false);
    }
  }

  async function createSession(currentPlatform, architecture) {
    var abortController = new AbortController();
    var timeout = window.setTimeout(function () {
      abortController.abort();
    }, SESSION_TIMEOUT_MS);

    try {
      var response = await fetch(SESSION_ENDPOINT, {
        method: "POST",
        mode: "same-origin",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        referrerPolicy: "no-referrer",
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          platform: currentPlatform,
          architecture: architecture
        }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error("Session request failed");
      }

      var contentType = response.headers.get("content-type") || "";
      if (!/^application\/json(?:\s*;|$)/i.test(contentType)) {
        throw new Error("Unexpected session response");
      }

      var payload = await response.json();
      return validateSession(payload, currentPlatform);
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function validateSession(payload, currentPlatform) {
    if (!payload || Object.prototype.toString.call(payload) !== "[object Object]") {
      throw new Error("Invalid session response");
    }

    var protocolUrl = String(payload.protocolUrl || "");
    var protocolMatch = PROTOCOL_PATTERN.exec(protocolUrl);

    if (!protocolMatch || !TOKEN_PATTERN.test(protocolMatch[1])) {
      throw new Error("Invalid launch protocol");
    }

    var expectedProtocolUrl = "sinbarsupport://start?token=" + protocolMatch[1];
    if (protocolUrl !== expectedProtocolUrl) {
      throw new Error("Non-canonical launch protocol");
    }

    var expectedInstaller = INSTALLERS[currentPlatform];
    if (typeof payload.installerUrl !== "string" || payload.installerUrl !== expectedInstaller) {
      throw new Error("Invalid installer location");
    }

    var expiresAt = Date.parse(String(payload.expiresAt || ""));
    var now = Date.now();

    if (!Number.isFinite(expiresAt) || expiresAt <= now || expiresAt - now > MAX_SESSION_LIFETIME_MS) {
      throw new Error("Invalid session expiration");
    }

    return Object.freeze({
      protocolUrl: expectedProtocolUrl,
      installerUrl: expectedInstaller,
      expiresAt: expiresAt
    });
  }

  function openRegisteredAssistant(protocolUrl) {
    if (!PROTOCOL_PATTERN.test(protocolUrl)) {
      throw new Error("Unsafe launch target");
    }

    var launchLink = document.createElement("a");
    launchLink.href = protocolUrl;
    launchLink.rel = "noopener noreferrer";
    launchLink.setAttribute("aria-hidden", "true");
    launchLink.tabIndex = -1;

    document.body.appendChild(launchLink);
    launchLink.click();
    launchLink.remove();
  }

  function scheduleFallback() {
    clearFallbackTimer();
    fallbackTimer = window.setTimeout(function () {
      fallbackTimer = null;

      if (document.visibilityState === "visible") {
        showFallback("not-opened");
      }
    }, FALLBACK_DELAY_MS);
  }

  function clearFallbackTimer() {
    if (fallbackTimer !== null) {
      window.clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
  }

  function showFallback(reason) {
    configureDevicePresentation(platform);

    if (reason === "session-error") {
      dialogKicker.textContent = "Connection help";
      dialogTitle.textContent = "The secure session could not start";
      dialogDescription.textContent = "Install the Sinbar Support Assistant if this is your first visit. Then close this window and try again.";
    } else if (reason === "unsupported") {
      dialogKicker.textContent = "Supported devices";
      dialogTitle.textContent = "Choose a Windows or macOS installer";
      dialogDescription.textContent = "Sinbar Support Assistant is available for Windows 10 or 11 and current macOS computers.";
    } else {
      dialogKicker.textContent = "First visit";
      dialogTitle.textContent = "Did Sinbar Support open?";
      dialogDescription.textContent = "If your browser displayed an Open Sinbar Support prompt, approve it. If nothing opened, install the signed assistant once.";
    }

    if (typeof assistantDialog.showModal === "function") {
      if (!assistantDialog.open) {
        assistantDialog.showModal();
      }
    } else {
      assistantDialog.setAttribute("open", "");
    }
  }

  function closeDialog() {
    if (typeof assistantDialog.close === "function" && assistantDialog.open) {
      assistantDialog.close();
    } else {
      assistantDialog.removeAttribute("open");
    }
  }

  function setLoading(isLoading) {
    startButton.disabled = isLoading;
    startButton.setAttribute("aria-busy", isLoading ? "true" : "false");
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
