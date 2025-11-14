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

REM Read extension ID and version from blender_manifest.toml
for /f "tokens=2 delims== " %%a in ('findstr /r "^id" "%EXTENSION_DIR%\blender_manifest.toml"') do set EXTENSION_ID=%%a
for /f "tokens=2 delims== " %%a in ('findstr /r "^version" "%EXTENSION_DIR%\blender_manifest.toml"') do set EXTENSION_VERSION=%%a

REM Remove quotes from the values
set EXTENSION_ID=%EXTENSION_ID:"=%
set EXTENSION_VERSION=%EXTENSION_VERSION:"=%

REM Construct the expected package filename
set PACKAGE_NAME=%EXTENSION_ID%-%EXTENSION_VERSION%.zip
set PACKAGE_PATH=%EXTENSION_DIR%\%PACKAGE_NAME%

echo Building package: %PACKAGE_NAME%
echo.

REM Delete existing package if present to ensure fresh build detection
if exist "%PACKAGE_PATH%" (
    echo Removing existing package...
    del "%PACKAGE_PATH%"
    echo.
)

REM Run the build command
echo Running Blender extension build...
"%BLENDER_PATH%" --command extension build --source-dir "%EXTENSION_DIR%" --output-dir "%EXTENSION_DIR%"

REM Check if the package was created (ignore Blender's exit code due to addon conflicts)
echo.
if exist "%PACKAGE_PATH%" (
    echo ========================================
    echo Build completed successfully!
    echo ========================================
    echo.
    echo Package: %PACKAGE_NAME%
    for %%F in ("%PACKAGE_PATH%") do echo Size: %%~zF bytes
    echo Location: %EXTENSION_DIR%
    echo.
) else (
    echo ========================================
    echo Build FAILED - package not created
    echo ========================================
    echo.
    echo Expected package: %PACKAGE_NAME%
    echo Check the output above for errors.
    echo.
)

pause
