@echo off
setlocal
cd /d "%~dp0"
set "DASH_PY=python"
where py >nul 2>nul
if not errorlevel 1 set "DASH_PY=py -3"
%DASH_PY% --version
if errorlevel 1 goto sem_python
%DASH_PY% -m pip install -r requirements.txt
if errorlevel 1 goto falha
echo.
echo Dependencias instaladas. Execute INICIAR_DASHBOARD.bat.
pause
exit /b 0
:sem_python
echo Instale o Python 3.10 ou superior e tente novamente.
pause
exit /b 1
:falha
echo A instalacao falhou. Consulte a mensagem acima ou o suporte de TI.
pause
exit /b 1
