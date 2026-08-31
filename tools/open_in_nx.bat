@echo off
REM tools\open_in_nx.bat - Open a STEP file in NX12 (ugraf)
REM Usage: open_in_nx.bat "C:\path\to\file.step"
if "%~1"=="" (
  echo Usage: %~nx0 ^"path_to_step^"
  exit /b 1
)
"D:\Program Files\Siemens\NX 12.0\NXBIN\ugraf.exe" -nx "%~1"
