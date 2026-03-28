@echo off
REM OCR Tool - Windows run script
REM Usage: run.bat input_file.png [output_file.md]

if "%1"=="" (
    echo Usage: run.bat input_file [output_file]
    echo Example: run.bat page_1.png output/page_1.md
    exit /b 1
)

if "%DATALAB_API_KEY%"=="" (
    if exist .env (
        for /f "tokens=1,2 delims==" %%a in (.env) do (
            if "%%a"=="DATALAB_API_KEY" set DATALAB_API_KEY=%%b
        )
    )
)

py -3.10 api.py %1 %2 %3 %4 %5
