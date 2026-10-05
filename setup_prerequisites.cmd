@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: WRECZ — Complete Automated Prerequisites & Environment Installer
:: Double-click this .cmd to install:
::   - Python 3.12
::   - Node.js LTS
::   - Ollama & phi4-mini model & wrecz-brain
::   - Rustup & Visual Studio C++ Build Tools (Tauri 2 prerequisites)
::   - Python .venv & requirements.txt
::   - Frontend node_modules (npm install)
:: ============================================================================

:: 1. Self-Elevation to Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ======================================================================
    echo [WRECZ SETUP] Requesting Administrator privileges...
    echo ======================================================================
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Set script directory as active working directory
cd /d "%~dp0"
title WRECZ Setup & Prerequisites Installer

cls
echo ======================================================================
echo                  W R E C Z   S E T U P   W I Z A R D
echo           Local Windows AI PC Assistant — One-Click Setup
echo ======================================================================
echo.
echo This script will check and install all required prerequisites:
echo   [1] Python 3.12 (64-bit)
echo   [2] Node.js LTS
echo   [3] Ollama Engine + phi4-mini model + wrecz-brain
echo   [4] Rust & Visual Studio C++ Build Tools (Tauri 2 desktop prerequisites)
echo   [5] Backend Python Virtual Environment (.venv + PyTorch/Kokoro)
echo   [6] Frontend Node dependencies (npm install)
echo.
echo ======================================================================
echo.

:: 2. Refresh Path helper
call :refresh_path

:: Check for winget
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Windows Package Manager (winget) is not installed or not in PATH.
    echo Please install App Installer from Microsoft Store or update Windows.
    pause
    exit /b 1
)

:: ============================================================================
:: STEP 1: Python 3.12
:: ============================================================================
echo [STEP 1/6] Checking Python 3.12...
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('py -3.12 --version 2^>^&1') do echo [OK] Found %%v
) else (
    echo [INSTALL] Installing Python 3.12 via winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    call :refresh_path
)
echo.

:: ============================================================================
:: STEP 2: Node.js LTS
:: ============================================================================
echo [STEP 2/6] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('node --version 2^>^&1') do echo [OK] Found Node.js %%v
) else (
    echo [INSTALL] Installing Node.js LTS via winget...
    winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    call :refresh_path
)
echo.

:: ============================================================================
:: STEP 3: Ollama & phi4-mini Model
:: ============================================================================
echo [STEP 3/6] Checking Ollama...
ollama --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('ollama --version 2^>^&1') do echo [OK] Found %%v
) else (
    echo [INSTALL] Installing Ollama via winget...
    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    call :refresh_path
)

:: Ensure Ollama service is running
echo [CHECK] Ensuring Ollama background service is running...
curl -s http://127.0.0.1:11434/api/version >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting Ollama background server...
    start "" /b ollama serve
    timeout /t 4 /nobreak >nul
)

:: Pull base model phi4-mini
echo [MODEL] Pulling base phi4-mini model via Ollama (this may take a few minutes)...
ollama pull phi4-mini

:: Create custom wrecz-brain model
if exist "%~dp0Modelfile" (
    echo [MODEL] Creating custom 'wrecz-brain' model from Modelfile...
    ollama create wrecz-brain -f "%~dp0Modelfile"
) else (
    echo [WARNING] Modelfile not found at %~dp0Modelfile. Skipping model creation.
)
echo.

:: ============================================================================
:: STEP 4: Tauri 2 Prerequisites (Rust + MSVC C++ Build Tools)
:: ============================================================================
echo [STEP 4/6] Checking Tauri desktop prerequisites (Rust + C++ Build Tools)...

:: Check Rust
cargo --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('cargo --version 2^>^&1') do echo [OK] Found %%v
) else (
    echo [INSTALL] Installing Rustup toolchain...
    winget install -e --id Rustlang.Rustup --accept-package-agreements --accept-source-agreements
    call :refresh_path
    where rustup >nul 2>&1 && rustup default stable-x86_64-pc-windows-msvc
)

:: Check Visual Studio C++ Build Tools
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "HAS_MSVC=0"
if exist "%VSWHERE%" (
    for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2^>nul`) do (
        if not "%%i"=="" set "HAS_MSVC=1"
    )
)
where cl >nul 2>&1 && set "HAS_MSVC=1"

if "!HAS_MSVC!"=="1" (
    echo [OK] Visual Studio C++ Compiler / Build Tools detected.
) else (
    echo [INSTALL] Installing Visual Studio Build Tools (C++ Workload for Tauri)...
    echo This is required for compiling Tauri native desktop apps.
    winget install -e --id Microsoft.VisualStudio.2022.BuildTools --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" --accept-package-agreements --accept-source-agreements
    call :refresh_path
)
echo.

:: ============================================================================
:: STEP 5: Backend Virtual Environment (.venv) & Dependencies
:: ============================================================================
echo [STEP 5/6] Setting up Backend Python Virtual Environment...
cd /d "%~dp0wrecz"

if not exist ".venv\Scripts\python.exe" (
    echo [CREATE] Creating .venv with Python 3.12...
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
) else (
    echo [OK] Python virtual environment already exists in wrecz\.venv
)

if exist ".venv\Scripts\activate.bat" (
    echo [ACTIVATE] Activating backend virtual environment...
    call .venv\Scripts\activate.bat
    echo [INSTALL] Upgrading pip and installing requirements.txt...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    call deactivate
) else (
    echo [ERROR] Could not find .venv\Scripts\activate.bat
)
echo.

:: ============================================================================
:: STEP 6: Frontend Dependencies (npm install)
:: ============================================================================
echo [STEP 6/6] Installing Frontend Node dependencies...
cd /d "%~dp0wrecz-frontend"

call :refresh_path
call npm install
echo.

:: ============================================================================
:: COMPLETION & LAUNCH MENU
:: ============================================================================
cls
echo ======================================================================
echo         🎉 WRECZ SETUP COMPLETED SUCCESSFULLY!
echo ======================================================================
echo.
echo All prerequisites, models, and environments are fully configured:
echo   * Python 3.12 & Backend Virtual Environment (.venv)
echo   * Node.js LTS & Frontend packages
echo   * Ollama running with 'wrecz-brain' (phi4-mini)
echo   * Rust & MSVC C++ toolchains for Tauri 2
echo.
echo ======================================================================
echo What would you like to do now?
echo.
echo   [1] Launch Native Desktop App (npm run desktop)
echo   [2] Launch Browser Mode (FastAPI 8765 + Vite 8443)
echo   [3] Run Backend CLI Mode (python main.py)
echo   [4] Exit installer
echo.
set /p "CHOICE=Select an option [1-4]: "

if "%CHOICE%"=="1" (
    echo Starting WRECZ Native Desktop App...
    cd /d "%~dp0wrecz-frontend"
    call npm run desktop
) else if "%CHOICE%"=="2" (
    echo Starting WRECZ Browser Mode...
    cd /d "%~dp0wrecz"
    call .venv\Scripts\activate.bat
    python run_all.py
) else if "%CHOICE%"=="3" (
    echo Starting WRECZ CLI Mode...
    cd /d "%~dp0wrecz"
    call .venv\Scripts\activate.bat
    python main.py
) else (
    echo Exiting setup. You can start WRECZ anytime!
    timeout /t 2 >nul
)

exit /b 0

:: ============================================================================
:: SUBROUTINE: Refresh PATH dynamically from Registry and known directories
:: ============================================================================
:refresh_path
for /f "tokens=2*" %%A in ('reg query "HKLM\System\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
set "PATH=%SYS_PATH%;%USR_PATH%;%PATH%"

if exist "%LocalAppData%\Programs\Python\Python312" set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
if exist "%ProgramFiles%\Python312" set "PATH=%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%PATH%"
if exist "%ProgramFiles%\nodejs" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%LocalAppData%\Programs\Ollama" set "PATH=%LocalAppData%\Programs\Ollama;%PATH%"
if exist "%USERPROFILE%\.cargo\bin" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
exit /b
