namespace Sinbar.Support.Assistant;

internal static class Base64Url
{
    internal static string Encode(ReadOnlySpan<byte> value) =>
        Convert.ToBase64String(value)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');

    internal static byte[] Decode(string value, int exactLength, string fieldName)
    {
        if (string.IsNullOrEmpty(value) || value.Contains('=') ||
            value.Any(character => !(char.IsAsciiLetterOrDigit(character) || character is '-' or '_')))
        {
            throw new SecurityException($"The {fieldName} encoding is invalid.");
        }

        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += padded.Length % 4 switch
        {
            0 => string.Empty,
            2 => "==",
            3 => "=",
            _ => throw new SecurityException($"The {fieldName} encoding is invalid."),
        };

        byte[] decoded;
        try
        {
            decoded = Convert.FromBase64String(padded);
        }
        catch (FormatException exception)
        {
            throw new SecurityException($"The {fieldName} encoding is invalid.", exception);
        }

        if (decoded.Length != exactLength)
        {
            throw new SecurityException($"The {fieldName} length is invalid.");
        }

        if (!string.Equals(Encode(decoded), value, StringComparison.Ordinal))
        {
            throw new SecurityException($"The {fieldName} encoding is not canonical.");
        }

        return decoded;
    }

    internal static byte[] DecodeBounded(string value, int maximumLength, string fieldName)
    {
        if (string.IsNullOrEmpty(value) || value.Contains('=') ||
            value.Any(character => !(char.IsAsciiLetterOrDigit(character) || character is '-' or '_')))
        {
            throw new SecurityException($"The {fieldName} encoding is invalid.");
        }

        if (value.Length > ((maximumLength + 2) / 3) * 4)
        {
            throw new SecurityException($"The {fieldName} is too large.");
        }

        string padded = value.Replace('-', '+').Replace('_', '/');
        padded += padded.Length % 4 switch
        {
            0 => string.Empty,
            2 => "==",
            3 => "=",
            _ => throw new SecurityException($"The {fieldName} encoding is invalid."),
        };

        byte[] decoded;
        try
        {
            decoded = Convert.FromBase64String(padded);
        }
        catch (FormatException exception)
        {
            throw new SecurityException($"The {fieldName} encoding is invalid.", exception);
        }

        if (decoded.Length > maximumLength)
        {
            throw new SecurityException($"The {fieldName} is too large.");
        }

        if (!string.Equals(Encode(decoded), value, StringComparison.Ordinal))
        {
            throw new SecurityException($"The {fieldName} encoding is not canonical.");
        }

        return decoded;
    }
}
