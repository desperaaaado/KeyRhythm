Unicode True
ManifestDPIAware True
RequestExecutionLevel user
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif
!ifndef DIST_DIR
  !define DIST_DIR "..\dist\KeyRhythm"
!endif
!ifndef OUT_FILE
  !define OUT_FILE "..\dist\KeyRhythm-Setup-${APP_VERSION}-x64.exe"
!endif

Name "KeyRhythm ${APP_VERSION}"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\KeyRhythm"
InstallDirRegKey HKCU "Software\KeyRhythm" "InstallDir"
BrandingText "KeyRhythm ${APP_VERSION}"
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "1.0.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "KeyRhythm"
VIAddVersionKey /LANG=2052 "FileDescription" "KeyRhythm Installer"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright (c) 2026 KeyRhythm contributors"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\KeyRhythm.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch KeyRhythm"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "KeyRhythm requires 64-bit Windows 10 or 11."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "KeyRhythm requires Windows 10 or later."
    Abort
  ${EndIf}
FunctionEnd

Section "KeyRhythm" SEC_MAIN
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${DIST_DIR}\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\KeyRhythm" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "DisplayName" "KeyRhythm"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "Publisher" "KeyRhythm"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "DisplayIcon" "$INSTDIR\KeyRhythm.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "NoRepair" 1
  SectionGetSize ${SEC_MAIN} $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm" "EstimatedSize" $0

  CreateDirectory "$SMPROGRAMS\KeyRhythm"
  CreateShortcut "$SMPROGRAMS\KeyRhythm\KeyRhythm.lnk" "$INSTDIR\KeyRhythm.exe"
  CreateShortcut "$SMPROGRAMS\KeyRhythm\Uninstall KeyRhythm.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
  SetShellVarContext current
  Delete "$SMPROGRAMS\KeyRhythm\KeyRhythm.lnk"
  Delete "$SMPROGRAMS\KeyRhythm\Uninstall KeyRhythm.lnk"
  RMDir "$SMPROGRAMS\KeyRhythm"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\KeyRhythm"
  DeleteRegKey HKCU "Software\KeyRhythm"
  ; User songs, charts, settings, scores and logs live in
  ; %LOCALAPPDATA%\KeyRhythm and are intentionally preserved.
SectionEnd
