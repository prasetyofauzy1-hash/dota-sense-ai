; Inno Setup script: iscc /DAppVersion=0.2.0.1 packaging\windows\dotasense.iss
; Installs per user (no admin rights) into %LOCALAPPDATA%\Programs\DotaSense AI.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8D3E2B5A-6F1C-4C2B-9E7A-3D5F1A2B4C6D}
AppName=DotaSense AI
AppVersion={#AppVersion}
AppVerName=DotaSense AI {#AppVersion}
AppPublisher=DotaSense AI
DefaultDirName={localappdata}\Programs\DotaSense AI
DefaultGroupName=DotaSense AI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist\installer
OutputBaseFilename=DotaSenseAI-Setup
SetupIconFile=dotasense.ico
UninstallDisplayIcon={app}\DotaSenseAI.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\..\dist\DotaSenseAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DotaSense AI"; Filename: "{app}\DotaSenseAI.exe"
Name: "{group}\Uninstall DotaSense AI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DotaSense AI"; Filename: "{app}\DotaSenseAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DotaSenseAI.exe"; Description: "{cm:LaunchProgram,DotaSense AI}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM DotaSenseAI.exe"; Flags: runhidden; RunOnceId: "StopDotaSense"
