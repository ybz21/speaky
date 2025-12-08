@echo off
cd /d "%~dp0"

echo Starting Speaky...
echo.

:: Activate conda base environment
call conda activate base
if errorlevel 1 (
    echo Failed to activate conda base
    pause
    exit /b 1
)

:: Check if already installed
python -c "import speaky" 2>nul
if errorlevel 1 (
    echo First run, installing dependencies...
    pip install PyQt5 pynput pyaudio numpy pyyaml openai requests websockets -i https://pypi.tuna.tsinghua.edu.cn/simple -q

    echo Installing speaky...
    pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple -q
    if errorlevel 1 (
        echo Failed to install project
        pause
        exit /b 1
    )
    echo Installation complete!
    echo.
)

:: Run the application
echo Press Ctrl+C to exit
echo.
python -m speaky.main %*

:: Keep window open if error
if errorlevel 1 (
    echo.
    echo Application exited with error
    pause
)
