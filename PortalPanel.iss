; ============================================================
; PortalPanel Setup Script — Inno Setup 6
; Compile with: ISCC.exe PortalPanel.iss
; Files expected at: dist\PortalPanel\ (relative to this file)
; ============================================================

[Setup]
AppId={{f8cf8313-2f3b-4ead-9cdb-552189ae3ccd}
AppName=PortalPanel
AppVersion=1.1
AppPublisher=RonenGru
DefaultDirName={localappdata}\Programs\PortalPanel
DefaultGroupName=PortalPanel
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
OutputBaseFilename=PortalPanel-Setup-v1.1
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\PortalPanelLauncher.exe

[Files]
Source: "dist\PortalPanel\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\PortalPanel"; Filename: "{app}\PortalPanelLauncher.exe"
Name: "{autodesktop}\PortalPanel"; Filename: "{app}\PortalPanelLauncher.exe"

[Run]
Filename: "{app}\PortalPanelLauncher.exe"; Description: "Launch PortalPanel"; Flags: nowait postinstall skipifsilent

; Remove user runtime data on uninstall (config, generated launcher.html)
[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PortalPanel"

; ------------------------------------------------------------
; Post-install note about WebView2
; ------------------------------------------------------------
[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    MsgBox(
      'PortalPanel requires the Microsoft Edge WebView2 Runtime.' + #13#10 +
      'This is preinstalled on Windows 10 (21H2 or later) and Windows 11.' + #13#10#13#10 +
      'If you are running an older version of Windows 10, please download' + #13#10 +
      'the standalone installer from:' + #13#10 +
      'https://go.microsoft.com/fwlink/p/?LinkId=2124703',
      mbInformation, MB_OK);
end;
