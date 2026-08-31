using System.Net;
using System.Security.Cryptography;

namespace Sinbar.Support.Assistant;

internal sealed class ArtifactDownloader : IDisposable
{
    private readonly HttpClient client;

    internal ArtifactDownloader()
    {
        client = new HttpClient(new HttpClientHandler
        {
            AllowAutoRedirect = false,
            AutomaticDecompression = DecompressionMethods.None,
        })
        {
            Timeout = TimeSpan.FromMinutes(3),
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd(
            $"SinbarSupportAssistant/{SecurityPolicy.AssistantVersion} (Windows)");
    }

    internal async Task<DownloadedArtifact> DownloadAndVerifyAsync(
        RustDeskArtifact artifact,
        CancellationToken cancellationToken)
    {
        Uri artifactUri = new(artifact.Url, UriKind.Absolute);
        SecureStagingDirectory staging = SecureStagingDirectory.Create();
        string finalFilename = Path.GetFileName(artifactUri.AbsolutePath);
        string partialFilename = finalFilename + ".partial";
        string partialPath = Path.Combine(staging.Path, partialFilename);
        string finalPath = Path.Combine(staging.Path, finalFilename);

        try
        {
            using HttpResponseMessage response = await client.GetAsync(
                artifactUri,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken).ConfigureAwait(false);

            if (response.StatusCode != HttpStatusCode.OK)
            {
                throw new InvalidOperationException("The RustDesk installer could not be downloaded.");
            }

            if (response.Content.Headers.ContentLength is long contentLength &&
                (contentLength <= 0 || contentLength > SecurityPolicy.MaximumArtifactBytes))
            {
                throw new SecurityException("The RustDesk installer size is invalid.");
            }

            await using Stream source = await response.Content.ReadAsStreamAsync(cancellationToken)
                .ConfigureAwait(false);
            await using FileStream destination = staging.CreateRestrictedFile(partialFilename);

            byte[] buffer = new byte[64 * 1024];
            long total = 0;
            while (true)
            {
                int read = await source.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
                if (read == 0)
                {
                    break;
                }

                total += read;
                if (total > SecurityPolicy.MaximumArtifactBytes)
                {
                    throw new SecurityException("The RustDesk installer exceeded the maximum permitted size.");
                }

                await destination.WriteAsync(buffer.AsMemory(0, read), cancellationToken)
                    .ConfigureAwait(false);
            }

            await destination.FlushAsync(cancellationToken).ConfigureAwait(false);
            if (total == 0)
            {
                throw new SecurityException("The RustDesk installer was empty.");
            }

            destination.Close();

            string actualSha256 = await ComputeSha256Async(partialPath, cancellationToken)
                .ConfigureAwait(false);
            if (!CryptographicOperations.FixedTimeEquals(
                    Convert.FromHexString(actualSha256),
                    Convert.FromHexString(artifact.Sha256)))
            {
                throw new SecurityException("The RustDesk installer checksum did not match.");
            }

            AuthenticodeVerifier.VerifyTrustedPublisher(
                partialPath,
                SecurityPolicy.RequiredPublisherSubjectFragment,
                BuildTrust.RustDeskPublisherSpkiSha256);

            File.Move(partialPath, finalPath, overwrite: false);
            return new DownloadedArtifact(staging, finalPath);
        }
        catch
        {
            staging.Dispose();
            throw;
        }
    }

    private static async Task<string> ComputeSha256Async(
        string path,
        CancellationToken cancellationToken)
    {
        await using FileStream stream = new(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 64 * 1024,
            options: FileOptions.Asynchronous | FileOptions.SequentialScan);
        byte[] digest = await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false);
        return Convert.ToHexString(digest).ToLowerInvariant();
    }

    public void Dispose() => client.Dispose();
}
