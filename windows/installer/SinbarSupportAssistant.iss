#define MyAppName "Sinbar Support Assistant"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Sinbar Consultants LLC"
#define MyAppUrl "https://support.sinbarconsultants.com/"
#define MyAppExeName "SinbarSupportAssistant.exe"

#ifndef ArtifactRoot
  #error ArtifactRoot must point to the signed win-x64 and win-arm64 publish directories.
#endif

[Setup]
AppId={{2B619A4E-0E68-4FE9-8C9A-4A18796FE0C7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppUrl}
AppSupportURL={#MyAppUrl}
AppUpdatesURL={#MyAppUrl}
DefaultDirName={localappdata}\Programs\Sinbar Support Assistant
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible arm64
OutputDir={#ArtifactRoot}\installer
OutputBaseFilename=Sinbar-Support-Assistant-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
SignTool=SinbarCodeSign
SignedUninstaller=yes

[Files]
Source: "{#ArtifactRoot}\win-x64\{#MyAppExeName}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion signcheck; Check: not IsArm64
Source: "{#ArtifactRoot}\win-arm64\{#MyAppExeName}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion signcheck; Check: IsArm64

[Registry]
Root: HKCU; Subkey: "Software\Classes\sinbarsupport"; ValueType: string; ValueName: ""; ValueData: "URL:Sinbar Support Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\sinbarsupport"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\sinbarsupport\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\sinbarsupport\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "https://support.sinbarconsultants.com/?assistant=installed"; Flags: shellexec nowait skipifsilent; Description: "Return to Sinbar Remote Support"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := IsWin64;
  if not Result then
    MsgBox('Sinbar Support Assistant requires 64-bit Windows.', mbError, MB_OK);
end;
