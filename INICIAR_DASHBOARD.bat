@echo off
setlocal
cd /d "%~dp0"
set "DASH_PY=python"
where py >nul 2>nul
if not errorlevel 1 set "DASH_PY=py -3"
%DASH_PY% -c "import openpyxl, waitress" >nul 2>nul
if errorlevel 1 goto dependencias
set "DASH_CONFIG=configuracao.json"
if exist "configuracao.local.json" set "DASH_CONFIG=configuracao.local.json"
echo Importando as planilhas configuradas em %DASH_CONFIG%...
%DASH_PY% integracao.py --config "%DASH_CONFIG%"
if errorlevel 1 goto falha
echo.
echo Abra http://127.0.0.1:8000 no navegador.
echo Mantenha esta janela aberta. Para encerrar, pressione Ctrl+C.
%DASH_PY% servidor.py --config "%DASH_CONFIG%"
pause
exit /b 0
:dependencias
echo Execute INSTALAR_DEPENDENCIAS.bat primeiro. Requer Python 3.10 ou superior.
pause
exit /b 1
:falha
echo A importacao foi recusada. A base anterior foi mantida.
echo Consulte a mensagem acima e, para prospeccao, relatorios\validacao_prospeccao.json.
pause
exit /b 1
