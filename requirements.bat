@echo off
title Instalador de Requerimientos Django
echo ===================================================
echo   Instalando dependencias del proyecto Python...
echo ===================================================
echo.

:: Verifica si Python esta instalado 
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta instalado o no se encuentra en el PATH.
    echo Por favor, instala Python antes de continuar.
    pause
    exit /b
)

:: Actualizar pip primero
echo [*] Actualizando pip...
python -m pip install --upgrade pip

echo.
echo [*] Instalando librerias...
echo ---------------------------------------------------

:: Instalar cada uno de los requerimientos
pip install Django gunicorn mysqlclient Pillow whitenoise django-cloudinary-storage

echo ---------------------------------------------------
if %errorlevel% equ 0 (
    echo [OK] !Todas las librerias se instalaron correctamente!
) else (
    echo [ALERTA] Hubo un problema con la instalacion de alguna libreria.
    echo Asegurate de tener las herramientas de compilacion de C++ instaladas (necesario para mysqlclient).
)

echo.
pause
