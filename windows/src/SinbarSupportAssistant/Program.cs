namespace Sinbar.Support.Assistant;

internal static class Program
{
    private const string RequestMutexName = "Local\\SinbarSupportAssistant-Request";
    private const string InstallMutexName = "Local\\SinbarSupportAssistant-Install";
    private const int CustomerCanceledExitCode = 2;

    [STAThread]
    private static async Task<int> Main(string[] args)
    {
        try
        {
            if (!OperatingSystem.IsWindows())
            {
                throw new PlatformNotSupportedException("Sinbar Support Assistant requires Windows.");
            }

            ValidateEmbeddedTrust();

            string architecture = RustDeskManager.GetNativeArchitecture();
            SignedManifestVerifier verifier = new(BuildTrust.ManifestPublicKeyX963Base64Url);
            (bool elevatedContinuation, string input) = ParseArguments(args);

            return elevatedContinuation
                ? await RunElevatedContinuationAsync(input, architecture, verifier).ConfigureAwait(false)
                : await RunStandardRequestAsync(input, architecture, verifier).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            AssistantLog.Write("ERROR", exception.Message);
            UserNotice.ShowError(
                "Sinbar Remote Support could not be started. Return to the support page and try again.");
            return 1;
        }
    }

    private static async Task<int> RunStandardRequestAsync(
        string protocolUrl,
        string architecture,
        SignedManifestVerifier verifier)
    {
        ProtocolRequest request = ProtocolRequest.Parse(protocolUrl);

        // Serialize the complete browser-request path, including token
        // consumption and the UAC wait. This prevents parallel protocol
        // activations from consuming multiple sessions or presenting multiple
        // elevation prompts.
        using Mutex requestMutex = new(initiallyOwned: false, RequestMutexName);
        bool ownsRequestMutex = AcquireMutex(
            requestMutex,
            TimeSpan.FromSeconds(2),
            "Another Sinbar support request is already running.");

        try
        {
            using SessionClient sessionClient = new();
            using CancellationTokenSource cancellation = new(TimeSpan.FromMinutes(4));
            string envelope = await sessionClient.ConsumeAsync(
                request.Token,
                architecture,
                cancellation.Token).ConfigureAwait(false);
            SupportManifest manifest = verifier.Verify(envelope, architecture);

            // This confirmation is intentionally after server authorization
            // and signature verification, but before either UAC or launching
            // an already-installed support client.
            if (!UserNotice.ConfirmAttendedSupport(manifest.SessionId, installationConfirmation: false))
            {
                AssistantLog.Write("INFO", "The customer canceled the attended-support request.");
                return CustomerCanceledExitCode;
            }

            // A random or attacker-generated protocol link cannot reach the
            // elevation branch: the one-time token was consumed and the signed
            // manifest was verified first. Only then may Windows display UAC.
            if (RustDeskManager.NeedsInstallation())
            {
                if (RustDeskManager.IsAdministrator())
                {
                    await InstallAuthorizedAsync(
                        manifest,
                        architecture,
                        verifier,
                        cancellation.Token).ConfigureAwait(false);
                }
                else
                {
                    int elevatedExitCode = RustDeskManager.ElevateAndContinueWithVerifiedEnvelope(envelope);
                    if (elevatedExitCode != 0)
                    {
                        return elevatedExitCode;
                    }
                }
            }

            // Always launch from the original customer process after an
            // elevated install, so RustDesk is not unnecessarily left running
            // at high integrity.
            RustDeskManager.LaunchTrusted();
            AssistantLog.Write("PASS", "RustDesk opened in attended-support mode.");
            return 0;
        }
        finally
        {
            if (ownsRequestMutex)
            {
                requestMutex.ReleaseMutex();
            }
        }
    }

    private static async Task<int> RunElevatedContinuationAsync(
        string encodedEnvelope,
        string architecture,
        SignedManifestVerifier verifier)
    {
        if (!RustDeskManager.IsAdministrator())
        {
            throw new SecurityException("The elevated continuation was not approved by Windows.");
        }

        byte[] envelopeBytes = Base64Url.DecodeBounded(
            encodedEnvelope,
            SecurityPolicy.MaximumEnvelopeBytes,
            "elevated manifest envelope");
        string envelope = new System.Text.UTF8Encoding(
            encoderShouldEmitUTF8Identifier: false,
            throwOnInvalidBytes: true).GetString(envelopeBytes);
        SupportManifest manifest = verifier.Verify(envelope, architecture);

        using CancellationTokenSource cancellation = new(TimeSpan.FromMinutes(4));
        if (RustDeskManager.NeedsInstallation())
        {
            // A direct local replay of --elevated-envelope must not bypass
            // explicit customer consent. The first-install path therefore has
            // a second confirmation inside the elevated process.
            if (!UserNotice.ConfirmAttendedSupport(manifest.SessionId, installationConfirmation: true))
            {
                AssistantLog.Write("INFO", "The customer canceled the RustDesk installation.");
                return CustomerCanceledExitCode;
            }

            await InstallAuthorizedAsync(
                manifest,
                architecture,
                verifier,
                cancellation.Token).ConfigureAwait(false);
        }

        // The original medium-integrity process performs the launch.
        AssistantLog.Write("PASS", "RustDesk installation completed; returning to the customer session.");
        return 0;
    }

    private static async Task InstallAuthorizedAsync(
        SupportManifest manifest,
        string architecture,
        SignedManifestVerifier verifier,
        CancellationToken cancellationToken)
    {
        using Mutex installMutex = new(initiallyOwned: false, InstallMutexName);
        bool ownsInstallMutex = AcquireMutex(
            installMutex,
            TimeSpan.FromSeconds(2),
            "Another Sinbar support installation is already running.");

        try
        {
            // Recheck after acquiring the installation gate. A concurrent
            // authorized request may already have completed installation.
            if (!RustDeskManager.NeedsInstallation())
            {
                return;
            }

            AssistantLog.Write("INFO", "Installing the authorized attended-support client.");
            using ArtifactDownloader downloader = new();
            using DownloadedArtifact installer = await downloader.DownloadAndVerifyAsync(
                manifest.Artifact,
                cancellationToken).ConfigureAwait(false);

            RustDeskManager.Install(
                installer.Path,
                manifest.Artifact,
                () => verifier.EnsureCurrent(manifest, architecture));
        }
        finally
        {
            if (ownsInstallMutex)
            {
                installMutex.ReleaseMutex();
            }
        }
    }

    private static bool AcquireMutex(Mutex mutex, TimeSpan timeout, string failureMessage)
    {
        try
        {
            if (!mutex.WaitOne(timeout))
            {
                throw new InvalidOperationException(failureMessage);
            }
        }
        catch (AbandonedMutexException)
        {
            // The abandoned mutex is acquired by the current thread. Continue
            // with all normal validations rather than leaving the flow wedged.
        }

        return true;
    }

    private static void ValidateEmbeddedTrust()
    {
        if (string.Equals(
                BuildTrust.ManifestPublicKeyX963Base64Url,
                "UNCONFIGURED",
                StringComparison.Ordinal))
        {
            throw new SecurityException(
                "This assistant build does not contain the production manifest verification key.");
        }

        if (string.Equals(
                BuildTrust.RustDeskPublisherSpkiSha256,
                "UNCONFIGURED",
                StringComparison.Ordinal) ||
            BuildTrust.RustDeskPublisherSpkiSha256.Length != 64 ||
            BuildTrust.RustDeskPublisherSpkiSha256.Any(character => !Uri.IsHexDigit(character)))
        {
            throw new SecurityException(
                "This assistant build does not contain the approved RustDesk signer-key pin.");
        }
    }

    private static (bool ElevatedContinuation, string Input) ParseArguments(string[] args)
    {
        if (args.Length == 1)
        {
            return (false, args[0]);
        }

        if (args.Length == 2 && string.Equals(args[0], "--elevated-envelope", StringComparison.Ordinal))
        {
            return (true, args[1]);
        }

        throw new SecurityException("The assistant accepts only a Sinbar support link.");
    }
}
