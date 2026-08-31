using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Principal;

namespace Sinbar.Support.Assistant;

internal static class RustDeskManager
{
    internal static string GetNativeArchitecture() => RuntimeInformation.OSArchitecture switch
    {
        Architecture.X64 => "x86_64",
        Architecture.Arm64 => "arm64",
        _ => throw new PlatformNotSupportedException(
            "Sinbar Support Assistant supports 64-bit Intel/AMD and ARM64 Windows devices."),
    };

    internal static bool IsAdministrator()
    {
        using WindowsIdentity identity = WindowsIdentity.GetCurrent();
        WindowsPrincipal principal = new(identity);
        return principal.IsInRole(WindowsBuiltInRole.Administrator);
    }

    internal static bool NeedsInstallation()
    {
        string? executable = FindExecutable();
        if (executable is null || !VersionMatches(executable))
        {
            return true;
        }

        try
        {
            AuthenticodeVerifier.VerifyTrustedPublisher(
                executable,
                SecurityPolicy.RequiredPublisherSubjectFragment,
                BuildTrust.RustDeskPublisherSpkiSha256);
            return false;
        }
        catch
        {
            return true;
        }
    }

    internal static int ElevateAndContinueWithVerifiedEnvelope(string signedEnvelope)
    {
        string executable = Environment.ProcessPath
            ?? throw new InvalidOperationException("The assistant executable path is unavailable.");

        ProcessStartInfo startInfo = new()
        {
            FileName = executable,
            UseShellExecute = true,
            Verb = "runas",
        };
        startInfo.ArgumentList.Add("--elevated-envelope");
        startInfo.ArgumentList.Add(Base64Url.Encode(System.Text.Encoding.UTF8.GetBytes(signedEnvelope)));

        try
        {
            using Process process = Process.Start(startInfo)
                ?? throw new InvalidOperationException("The approved installer process could not be started.");
            process.WaitForExit();
            return process.ExitCode;
        }
        catch (Win32Exception exception) when (exception.NativeErrorCode == 1223)
        {
            throw new InvalidOperationException(
                "Administrator approval was canceled. RustDesk was not installed.",
                exception);
        }
    }

    internal static void Install(
        string installerPath,
        RustDeskArtifact artifact,
        Action revalidateAuthorization)
    {
        if (!IsAdministrator())
        {
            throw new SecurityException("Administrator approval is required to install RustDesk.");
        }

        // Deliberately repeat both validations immediately before msiexec. The
        // downloader already performed them; this closes the authorization-to-
        // execution gap and ensures the exact on-disk bytes are still trusted.
        VerifyInstallerImmediatelyBeforeExecution(installerPath, artifact);
        revalidateAuthorization();

        string msiexec = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.Windows),
            "System32",
            "msiexec.exe");
        string msiLog = Path.Combine(
            Path.GetDirectoryName(installerPath)
                ?? throw new SecurityException("The RustDesk staging path is invalid."),
            "rustdesk-msi.log");

        ProcessStartInfo startInfo = new()
        {
            FileName = msiexec,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        foreach (string argument in new[]
        {
            "/i",
            installerPath,
            "/qn",
            "/norestart",
            "CREATESTARTMENUSHORTCUTS=Y",
            "CREATEDESKTOPSHORTCUTS=N",
            "INSTALLPRINTER=N",
            "/l*v",
            msiLog,
        })
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Windows Installer could not be started.");
        process.WaitForExit();

        if (process.ExitCode is not (0 or 1641 or 3010))
        {
            throw new InvalidOperationException(
                $"RustDesk installation failed with Windows Installer code {process.ExitCode}.");
        }
    }

    private static void VerifyInstallerImmediatelyBeforeExecution(
        string installerPath,
        RustDeskArtifact artifact)
    {
        using FileStream stream = new(
            installerPath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 64 * 1024,
            options: FileOptions.SequentialScan);
        byte[] digest = System.Security.Cryptography.SHA256.HashData(stream);
        byte[] expected = Convert.FromHexString(artifact.Sha256);

        if (!System.Security.Cryptography.CryptographicOperations.FixedTimeEquals(digest, expected))
        {
            throw new SecurityException("The RustDesk installer changed before installation.");
        }

        AuthenticodeVerifier.VerifyTrustedPublisher(
            installerPath,
            SecurityPolicy.RequiredPublisherSubjectFragment,
            BuildTrust.RustDeskPublisherSpkiSha256);
    }

    internal static void LaunchTrusted()
    {
        string executable = WaitForExecutable(TimeSpan.FromSeconds(60))
            ?? throw new InvalidOperationException("RustDesk was installed but could not be found.");

        if (!VersionMatches(executable))
        {
            throw new SecurityException("The installed RustDesk version does not match the approved release.");
        }

        AuthenticodeVerifier.VerifyTrustedPublisher(
            executable,
            SecurityPolicy.RequiredPublisherSubjectFragment,
            BuildTrust.RustDeskPublisherSpkiSha256);

        ProcessStartInfo startInfo = new()
        {
            FileName = executable,
            UseShellExecute = true,
            WorkingDirectory = Path.GetDirectoryName(executable)!,
        };

        _ = Process.Start(startInfo)
            ?? throw new InvalidOperationException("RustDesk could not be opened.");
    }

    private static string? FindExecutable()
    {
        string[] candidates =
        {
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                "RustDesk",
                "rustdesk.exe"),
            Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "RustDesk",
                "rustdesk.exe"),
        };

        return candidates.FirstOrDefault(File.Exists);
    }

    private static string? WaitForExecutable(TimeSpan timeout)
    {
        Stopwatch stopwatch = Stopwatch.StartNew();
        do
        {
            string? executable = FindExecutable();
            if (executable is not null)
            {
                return executable;
            }

            Thread.Sleep(TimeSpan.FromSeconds(2));
        }
        while (stopwatch.Elapsed < timeout);

        return null;
    }

    private static bool VersionMatches(string executable)
    {
        FileVersionInfo version = FileVersionInfo.GetVersionInfo(executable);
        string observed = version.ProductVersion ?? version.FileVersion ?? string.Empty;
        return observed.Equals(SecurityPolicy.RequiredRustDeskVersion, StringComparison.Ordinal) ||
               observed.StartsWith(SecurityPolicy.RequiredRustDeskVersion + ".", StringComparison.Ordinal) ||
               observed.StartsWith(SecurityPolicy.RequiredRustDeskVersion + "-", StringComparison.Ordinal) ||
               observed.StartsWith(SecurityPolicy.RequiredRustDeskVersion + "+", StringComparison.Ordinal);
    }
}
