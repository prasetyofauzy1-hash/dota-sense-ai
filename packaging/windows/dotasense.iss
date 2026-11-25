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

[INI]
Filename: "{app}\release.ini"; Section: "DotaSense"; Key: "Version"; String: "{#AppVersion}"

[Icons]
Name: "{group}\DotaSense AI"; Filename: "{app}\DotaSenseAI.exe"
Name: "{group}\Uninstall DotaSense AI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DotaSense AI"; Filename: "{app}\DotaSenseAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DotaSenseAI.exe"; WorkingDir: "{app}"; Flags: nowait; Check: IsAppUpdate
Filename: "{app}\DotaSenseAI.exe"; Description: "{cm:LaunchProgram,DotaSense AI}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM DotaSenseAI.exe"; Flags: runhidden; RunOnceId: "StopDotaSense"

[UninstallDelete]
Type: files; Name: "{app}\release.ini"

[Code]
function OpenProcess(Access: Cardinal; InheritHandle: Boolean; ProcessId: Cardinal): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: Cardinal): Cardinal;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function UpdatePid: Integer;
begin
  Result := StrToIntDef(ExpandConstant('{param:DOTASENSEUPDATEPID|0}'), 0);
end;

function IsAppUpdate: Boolean;
begin
  Result := UpdatePid > 0;
end;

function InitializeSetup: Boolean;
var
  ProcessHandle: THandle;
begin
  Result := True;
  if not IsAppUpdate then
    Exit;
  ProcessHandle := OpenProcess($00100000, False, UpdatePid);
  if ProcessHandle = 0 then
    Exit; { The launcher may already have exited. }
  try
    Result := WaitForSingleObject(ProcessHandle, 30000) = 0;
  finally
    CloseHandle(ProcessHandle);
  end;
  if not Result then
    MsgBox('DotaSense AI is still running. Quit it and try again.', mbError, MB_OK);
end;
