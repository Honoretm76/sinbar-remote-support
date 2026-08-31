using System.Runtime.InteropServices;

namespace Sinbar.Support.Assistant;

internal static class UserNotice
{
    private const int IdYes = 6;
    private const uint MbYesNo = 0x00000004u;
    private const uint MbIconQuestion = 0x00000020u;
    private const uint MbDefaultButton2 = 0x00000100u;
    private const uint MbSetForeground = 0x00010000u;
    private const uint MbTopmost = 0x00040000u;

    internal static bool ConfirmAttendedSupport(
        string signedSessionId,
        bool installationConfirmation)
    {
        if (!OperatingSystem.IsWindows())
        {
            return false;
        }

        string reference = Guid.ParseExact(signedSessionId, "D")
            .ToString("N", System.Globalization.CultureInfo.InvariantCulture)[..8]
            .ToUpperInvariant();
        string action = installationConfirmation
            ? "Windows is ready to install the approved RustDesk support client."
            : "Sinbar Remote Support is ready to open an attended support session.";

        string message =
            $"{action}\r\n\r\n" +
            "Choose Yes only if you clicked Start Remote Support while speaking " +
            "with Sinbar Consultants. A Sinbar technician will still need you to " +
            "share the temporary RustDesk connection details.\r\n\r\n" +
            "No permanent support password will be created.\r\n" +
            $"Session reference: {reference}";

        return MessageBox(
            IntPtr.Zero,
            message,
            "Confirm Sinbar Remote Support",
            MbYesNo | MbIconQuestion | MbDefaultButton2 | MbSetForeground | MbTopmost) == IdYes;
    }

    internal static void ShowError(string message)
    {
        if (OperatingSystem.IsWindows())
        {
            _ = MessageBox(
                IntPtr.Zero,
                message + "\r\n\r\nCall Sinbar Consultants at 347-720-0367 if you need help.",
                "Sinbar Remote Support",
                0x00000010u | MbTopmost);
        }
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "MessageBoxW")]
    private static extern int MessageBox(
        IntPtr windowHandle,
        string text,
        string caption,
        uint type);
}
