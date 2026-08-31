using System.Security.AccessControl;
using System.Security.Principal;

namespace Sinbar.Support.Assistant;

internal sealed class SecureStagingDirectory : IDisposable
{
    private const string Prefix = "Sinbar-SupportAssistant-";
    private readonly string commonApplicationData;
    private bool disposed;

    private SecureStagingDirectory(string path, string commonApplicationData)
    {
        Path = path;
        this.commonApplicationData = commonApplicationData;
    }

    internal string Path { get; }

    internal static SecureStagingDirectory Create()
    {
        if (!RustDeskManager.IsAdministrator())
        {
            throw new SecurityException("Secure RustDesk staging requires administrator approval.");
        }

        string commonData = System.IO.Path.GetFullPath(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
        string path = System.IO.Path.Combine(commonData, Prefix + Guid.NewGuid().ToString("N"));

        DirectorySecurity security = CreateDirectorySecurity();
        DirectoryInfo directory = new(path);
        FileSystemAclExtensions.Create(directory, security);
        directory.Refresh();

        if ((directory.Attributes & FileAttributes.ReparsePoint) != 0 ||
            !string.Equals(directory.FullName, path, StringComparison.OrdinalIgnoreCase))
        {
            throw new SecurityException("The RustDesk staging directory is not trusted.");
        }

        // Reapply the protected ACL in case the directory unexpectedly existed.
        FileSystemAclExtensions.SetAccessControl(directory, security);
        return new SecureStagingDirectory(path, commonData);
    }

    internal FileStream CreateRestrictedFile(string filename)
    {
        if (disposed || filename != System.IO.Path.GetFileName(filename))
        {
            throw new SecurityException("The RustDesk staging filename is invalid.");
        }

        string target = System.IO.Path.Combine(Path, filename);
        FileInfo file = new(target);
        FileSecurity security = CreateFileSecurity();

        return FileSystemAclExtensions.Create(
            file,
            FileMode.CreateNew,
            FileSystemRights.FullControl,
            FileShare.None,
            64 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan | FileOptions.WriteThrough,
            security);
    }

    public void Dispose()
    {
        if (disposed)
        {
            return;
        }

        disposed = true;
        try
        {
            string fullPath = System.IO.Path.GetFullPath(Path);
            string requiredPrefix = commonApplicationData.TrimEnd(
                System.IO.Path.DirectorySeparatorChar,
                System.IO.Path.AltDirectorySeparatorChar) +
                System.IO.Path.DirectorySeparatorChar + Prefix;

            if (!fullPath.StartsWith(requiredPrefix, StringComparison.OrdinalIgnoreCase) ||
                !Directory.Exists(fullPath) ||
                (File.GetAttributes(fullPath) & FileAttributes.ReparsePoint) != 0)
            {
                return;
            }

            Directory.Delete(fullPath, recursive: true);
        }
        catch
        {
            // A failed cleanup is diagnostic, not permission to weaken checks.
        }
    }

    private static DirectorySecurity CreateDirectorySecurity()
    {
        DirectorySecurity security = new();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);

        const InheritanceFlags inheritance =
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit;
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
            FileSystemRights.FullControl,
            inheritance,
            PropagationFlags.None,
            AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null),
            FileSystemRights.FullControl,
            inheritance,
            PropagationFlags.None,
            AccessControlType.Allow));
        return security;
    }

    private static FileSecurity CreateFileSecurity()
    {
        FileSecurity security = new();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
            FileSystemRights.FullControl,
            AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null),
            FileSystemRights.FullControl,
            AccessControlType.Allow));
        return security;
    }
}

internal sealed class DownloadedArtifact : IDisposable
{
    private readonly SecureStagingDirectory stagingDirectory;

    internal DownloadedArtifact(SecureStagingDirectory stagingDirectory, string path)
    {
        this.stagingDirectory = stagingDirectory;
        Path = path;
    }

    internal string Path { get; }

    public void Dispose() => stagingDirectory.Dispose();
}
