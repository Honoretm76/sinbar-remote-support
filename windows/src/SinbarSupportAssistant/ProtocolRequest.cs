using System.Text.RegularExpressions;

namespace Sinbar.Support.Assistant;

internal sealed record ProtocolRequest(string Token)
{
    private static readonly Regex ExactProtocolPattern = new(
        @"\Asinbarsupport://start\?token=([A-Za-z0-9_-]{43})\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking,
        TimeSpan.FromMilliseconds(100));

    internal static ProtocolRequest Parse(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw) || raw.Length > 256)
        {
            throw new SecurityException("The support request is malformed.");
        }

        Match match = ExactProtocolPattern.Match(raw);
        if (!match.Success)
        {
            throw new SecurityException("The support request is malformed.");
        }

        return new ProtocolRequest(match.Groups[1].Value);
    }
}
