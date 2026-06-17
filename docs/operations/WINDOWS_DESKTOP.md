# FVENTAS Desktop para Windows

Esta variante ejecuta el panel FVENTAS como aplicacion de escritorio Windows. Mantiene las pantallas y reglas actuales, pero embebe Flask dentro de una ventana nativa mediante `pywebview` y permite generar un `.exe` con PyInstaller.

## Ejecutar en modo escritorio

```powershell
cd backend\api
python -m pip install -r requirements-desktop.txt
python desktop_app.py
```

## Verificar sin abrir ventana

```powershell
cd backend\api
python desktop_app.py --check
```

El primer arranque crea un administrador local si no existe. Las credenciales quedan en:

```text
%LOCALAPPDATA%\FVENTAS Desktop\primer-acceso.txt
```

## Generar EXE

```powershell
cd backend\api
.\scripts\build_windows_exe.ps1 -OneFile
```

Salida esperada:

```text
backend\api\dist\FVENTAS Desktop.exe
```

Si prefieres una carpeta distribuible en lugar de un solo archivo:

```powershell
.\scripts\build_windows_exe.ps1
```

Salida esperada:

```text
backend\api\dist\FVENTAS Desktop\FVENTAS Desktop.exe
```

## Datos locales

La aplicacion desktop guarda datos fuera del ejecutable para que no se pierdan al actualizar:

```text
%LOCALAPPDATA%\FVENTAS Desktop\data\fventas.db
%LOCALAPPDATA%\FVENTAS Desktop\uploads
%LOCALAPPDATA%\FVENTAS Desktop\backups
%LOCALAPPDATA%\FVENTAS Desktop\secret.key
```

## Requisito Windows

`pywebview` usa Microsoft Edge WebView2 en Windows. La mayoria de equipos actuales ya lo incluye. Si una maquina no abre la ventana, instala el runtime oficial de Microsoft Edge WebView2.
