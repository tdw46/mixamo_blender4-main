@echo off
REM Build script for Mixamo Rig Blender Extension
REM This script builds the extension package using Blender's command line tools

echo ========================================
echo Building Mixamo Rig Extension
echo ========================================
echo.

REM Set the Blender executable path
set BLENDER_PATH=C:\Program Files\Blender Foundation\Blender 4.5\blender.exe

REM Set the extension directory (current directory)
set EXTENSION_DIR=%~dp0

REM Remove trailing backslash
set EXTENSION_DIR=%EXTENSION_DIR:~0,-1%

echo Blender Path: %BLENDER_PATH%
echo Extension Directory: %EXTENSION_DIR%
echo.

REM Run the build command
echo Running Blender extension build...
"%BLENDER_PATH%" --command extension build --source-dir "%EXTENSION_DIR%" --output-dir "%EXTENSION_DIR%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Build completed successfully!
    echo ========================================
    echo.
    echo Package created in: %EXTENSION_DIR%
    echo.
) else (
    echo.
    echo ========================================
    echo Build failed with error code: %ERRORLEVEL%
    echo ========================================
    echo.
)

pause
