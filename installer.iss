[Setup]
AppName=Nodal
AppVersion=1.0
DefaultDirName={autopf}\Nodal
DefaultGroupName=Nodal
OutputDir=installer
OutputBaseFilename=Nodal-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
[Files]
Source: "dist\Nodal\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
[Icons]
Name: "{group}\Nodal"; Filename: "{app}\Nodal.exe"
Name: "{autodesktop}\Nodal"; Filename: "{app}\Nodal.exe"
[Run]
Filename: "{app}\Nodal.exe"; Description: "Launch Nodal"; Flags: postinstall nowait skipifsilent
