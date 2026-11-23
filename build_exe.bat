@echo off
title Build Vistle Standalone EXE
echo ===========================================
echo Building Vistle into standalone executable
echo ===========================================
echo.

pyinstaller --noconfirm --onedir --windowed ^
    --name "Vistle" ^
    --add-data "vistle;vistle" ^
    main.py

echo.
if exist "dist\Vistle\Vistle.exe" (
    echo [SUCCESS] Vistle.exe built successfully in dist\Vistle\
) else (
    echo [ERROR] Build failed. Please check above logs.
)
pause
