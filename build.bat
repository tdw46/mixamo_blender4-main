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

REM Check if the build package was created (ignore Blender's exit code due to addon conflicts)
echo.
if exist "%EXTENSION_DIR%\mixamo_rig-*.zip" (
    echo ========================================
    echo Build completed successfully!
    echo ========================================
    echo.
    for %%F in ("%EXTENSION_DIR%\mixamo_rig-*.zip") do (
        echo Package created: %%~nxF
        echo Size: %%~zF bytes
    )
    echo Location: %EXTENSION_DIR%
    echo.
) else (
    echo ========================================
    echo Build failed - package not created
    echo ========================================
    echo.
)

pause
