using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace Sinbar.Support.Assistant;

internal static class AuthenticodeVerifier
{
    private static readonly Guid ActionGenericVerifyV2 =
        new("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");

    internal static string VerifyTrustedPublisher(
        string path,
        string requiredSubjectFragment,
        string requiredSpkiSha256)
    {
        if (!OperatingSystem.IsWindows())
        {
            throw new PlatformNotSupportedException("Authenticode validation requires Windows.");
        }

        string fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("The signed file was not found.", fullPath);
        }

        int trustStatus = VerifyWithWinTrust(fullPath);
        if (trustStatus != 0)
        {
            throw new SecurityException(
                $"Windows rejected the Authenticode signature (0x{trustStatus:X8}).");
        }

        using X509Certificate signer = X509Certificate.CreateFromSignedFile(fullPath);
        using X509Certificate2 signerCertificate = new(signer);
        string subject = signerCertificate.Subject;

        if (string.IsNullOrWhiteSpace(subject) ||
            !subject.Contains(requiredSubjectFragment, StringComparison.OrdinalIgnoreCase))
        {
            throw new SecurityException("The file was not signed by the approved RustDesk publisher.");
        }

        byte[] expectedSpkiHash;
        try
        {
            expectedSpkiHash = Convert.FromHexString(requiredSpkiSha256);
        }
        catch (FormatException exception)
        {
            throw new SecurityException("The approved RustDesk signer-key pin is invalid.", exception);
        }

        byte[] signerSpki = signerCertificate.PublicKey.ExportSubjectPublicKeyInfo();
        byte[] observedSpkiHash = SHA256.HashData(signerSpki);
        if (expectedSpkiHash.Length != 32 ||
            !CryptographicOperations.FixedTimeEquals(observedSpkiHash, expectedSpkiHash))
        {
            throw new SecurityException("The file's signing key is not the approved RustDesk signer key.");
        }

        return subject;
    }

    private static int VerifyWithWinTrust(string path)
    {
        IntPtr pathPointer = IntPtr.Zero;
        IntPtr fileInfoPointer = IntPtr.Zero;

        try
        {
            pathPointer = Marshal.StringToCoTaskMemUni(path);
            WinTrustFileInfo fileInfo = new()
            {
                StructureSize = (uint)Marshal.SizeOf<WinTrustFileInfo>(),
                FilePath = pathPointer,
                FileHandle = IntPtr.Zero,
                KnownSubject = IntPtr.Zero,
            };

            fileInfoPointer = Marshal.AllocCoTaskMem(Marshal.SizeOf<WinTrustFileInfo>());
            Marshal.StructureToPtr(fileInfo, fileInfoPointer, false);

            WinTrustData trustData = new()
            {
                StructureSize = (uint)Marshal.SizeOf<WinTrustData>(),
                PolicyCallbackData = IntPtr.Zero,
                SipClientData = IntPtr.Zero,
                UiChoice = 2, // WTD_UI_NONE
                RevocationChecks = 1, // WTD_REVOKE_WHOLECHAIN
                UnionChoice = 1, // WTD_CHOICE_FILE
                InfoStruct = fileInfoPointer,
                StateAction = 0, // WTD_STATEACTION_IGNORE
                StateData = IntPtr.Zero,
                UrlReference = IntPtr.Zero,
                ProviderFlags = 0x00000080, // WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT
                UiContext = 0,
            };

            Guid action = ActionGenericVerifyV2;
            return WinVerifyTrust(IntPtr.Zero, ref action, ref trustData);
        }
        finally
        {
            if (fileInfoPointer != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(fileInfoPointer);
            }

            if (pathPointer != IntPtr.Zero)
            {
                Marshal.FreeCoTaskMem(pathPointer);
            }
        }
    }

    [DllImport("wintrust.dll", ExactSpelling = true, SetLastError = false)]
    private static extern int WinVerifyTrust(
        IntPtr windowHandle,
        ref Guid actionId,
        ref WinTrustData trustData);

    [StructLayout(LayoutKind.Sequential)]
    private struct WinTrustFileInfo
    {
        internal uint StructureSize;
        internal IntPtr FilePath;
        internal IntPtr FileHandle;
        internal IntPtr KnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WinTrustData
    {
        internal uint StructureSize;
        internal IntPtr PolicyCallbackData;
        internal IntPtr SipClientData;
        internal uint UiChoice;
        internal uint RevocationChecks;
        internal uint UnionChoice;
        internal IntPtr InfoStruct;
        internal uint StateAction;
        internal IntPtr StateData;
        internal IntPtr UrlReference;
        internal uint ProviderFlags;
        internal uint UiContext;
    }
}
