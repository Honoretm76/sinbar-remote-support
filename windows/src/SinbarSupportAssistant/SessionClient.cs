using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace Sinbar.Support.Assistant;

internal sealed class SessionClient : IDisposable
{
    private static readonly Uri ConsumeEndpoint = new(
        SecurityPolicy.ApiOrigin + SecurityPolicy.SessionConsumePath,
        UriKind.Absolute);

    private readonly HttpClient client;

    internal SessionClient()
    {
        HttpClientHandler handler = new()
        {
            AllowAutoRedirect = false,
            AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate,
        };

        client = new HttpClient(handler)
        {
            Timeout = TimeSpan.FromSeconds(20),
        };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        client.DefaultRequestHeaders.UserAgent.ParseAdd(
            $"SinbarSupportAssistant/{SecurityPolicy.AssistantVersion} (Windows)");
    }

    internal async Task<string> ConsumeAsync(
        string token,
        string architecture,
        CancellationToken cancellationToken)
    {
        SessionConsumeRequest request = new(
            Token: token,
            Platform: SecurityPolicy.RequiredPlatform,
            Architecture: architecture,
            AssistantVersion: SecurityPolicy.AssistantVersion);

        using HttpResponseMessage response = await client.PostAsJsonAsync(
            ConsumeEndpoint,
            request,
            cancellationToken).ConfigureAwait(false);

        if (response.StatusCode != HttpStatusCode.OK)
        {
            throw new InvalidOperationException(
                "The support request could not be authorized. Return to the support page and try again.");
        }

        string? mediaType = response.Content.Headers.ContentType?.MediaType;
        if (!string.Equals(mediaType, "application/json", StringComparison.OrdinalIgnoreCase))
        {
            throw new SecurityException("The support service returned an unexpected response type.");
        }

        if (response.Content.Headers.ContentLength is long contentLength &&
            contentLength > SecurityPolicy.MaximumEnvelopeBytes)
        {
            throw new SecurityException("The support service response is too large.");
        }

        await response.Content.LoadIntoBufferAsync(SecurityPolicy.MaximumEnvelopeBytes, cancellationToken)
            .ConfigureAwait(false);
        return await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
    }

    public void Dispose() => client.Dispose();
}
