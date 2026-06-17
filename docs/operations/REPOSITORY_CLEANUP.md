# Limpieza de repositorio

## Archivos eliminados

- Archivo IDE movil antiguo del proyecto previo.
- Archivo IDE Android antiguo con marca previa.
- `apps/mobile/fventas_mobile.iml`: archivo IDE generado localmente.
- Checksum antiguo de una entrega previa.
- `flutter_analyze.log` y `flutter_test.log`: logs locales generados.

## Archivos movidos

- `backend/api/README_DESKTOP_WINDOWS.md` se movio a `docs/operations/WINDOWS_DESKTOP.md`.
- `FVENTAS_ADMIN_APP_FUNCIONALIDADES.md` se movio a `docs/product/ADMIN_APP_FUNCIONALIDADES.md`.
- Modulos de infraestructura del backend se movieron a `backend/api/core`.

## Criterio

El repositorio debe separar codigo fuente, documentacion, infraestructura y entregables generados. Los artefactos compilados deben quedarse fuera del flujo normal de desarrollo y regenerarse cuando sea necesario.
