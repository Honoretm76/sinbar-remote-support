namespace Sinbar.Support.Assistant;

internal static class AssistantLog
{
    private const long MaximumLogBytes = 1024 * 1024;
    private static readonly object Gate = new();

    internal static void Write(string level, string message)
    {
        try
        {
            string directory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Sinbar",
                "SupportAssistant");
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "assistant.log");

            lock (Gate)
            {
                if (File.Exists(path) && new FileInfo(path).Length > MaximumLogBytes)
                {
                    File.Move(path, path + ".previous", overwrite: true);
                }

                File.AppendAllText(
                    path,
                    $"{DateTimeOffset.UtcNow:yyyy-MM-ddTHH:mm:ssZ} [{level}] {Sanitize(message)}{Environment.NewLine}");
            }
        }
        catch
        {
            // Diagnostics must never prevent or weaken the support flow.
        }
    }

    private static string Sanitize(string value)
    {
        string oneLine = value.Replace('\r', ' ').Replace('\n', ' ');
        return oneLine.Length <= 500 ? oneLine : oneLine[..500];
    }
}
