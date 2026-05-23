#ifndef SourceDir
  #error SourceDir must be provided with /DSourceDir=...
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8B9610FE-1B71-4C13-8D9F-2DFCB21A04B8}
AppName=Stacky Agents
AppVersion={#AppVersion}
AppPublisher=Stacky
DefaultDirName={localappdata}\Stacky Agents
DefaultGroupName=Stacky Agents
OutputDir={#OutputDir}
OutputBaseFilename=StackyAgents-{#AppVersion}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\backend\stacky-backend.exe

[Dirs]
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\projects"; Permissions: users-modify

[Files]
Source: "{#SourceDir}\backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\frontend\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\vscode_extension\*"; DestDir: "{app}\vscode_extension"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#SourceDir}\START.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\INSTALL.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\smoke_test.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\INSTALLER.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\OPERATOR_GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\release-manifest.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Stacky Agents"; Filename: "{app}\START.bat"; WorkingDir: "{app}"
Name: "{autodesktop}\Stacky Agents"; Filename: "{app}\START.bat"; WorkingDir: "{app}"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\INSTALL.ps1"""; Description: "Preparar Stacky Agents"; Flags: postinstall skipifsilent nowait

[UninstallDelete]
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\frontend"
Type: filesandordirs; Name: "{app}\vscode_extension"
Type: files; Name: "{app}\START.bat"
Type: files; Name: "{app}\INSTALL.ps1"
Type: files; Name: "{app}\smoke_test.ps1"
Type: files; Name: "{app}\INSTALLER.md"
Type: files; Name: "{app}\OPERATOR_GUIDE.md"
Type: files; Name: "{app}\release-manifest.json"
