# Estado Fase 0 y Fase 1

## Alcance interpretado

Este documento cierra la lectura operativa de las fases iniciales segun los MD originales.

- **Fase 0: Fundacion** corresponde a arquitectura, estructura del repo, contratos, documentacion, reglas iniciales Firebase y semillas.
- **Fase 1: Admin operativo / fundacion tecnica** corresponde a tener admin navegable, estructura de roles, verticales, productos, usuarios, formularios base, app Android inicial, autenticacion preparada y repositorios listos para Firebase.

No significa que el MVP comercial completo este listo para operar con clientes reales. Eso empieza en las siguientes fases.

## Fase 0

Estado: **cerrada tecnicamente**.

- Monorepo creado.
- Apps `admin` y `mobile` creadas.
- Paquetes `domain`, `shared` y `ui` creados.
- Backend `functions` creado.
- Infraestructura Firebase inicial creada.
- Documentacion viva organizada.
- Contratos de dominio iniciales creados.
- Reglas e indices Firestore iniciales creados.
- Seeds MVP creados.

## Fase 1

Estado: **cerrada como fundacion operativa inicial**.

- Admin Next.js navegable.
- Dashboard operativo.
- Modulos admin: verticales, productos, empresas, ordenes B2C, B2B, servicios, cotizaciones, pagos, ubicaciones, usuarios, auditoria y settings.
- Formularios base para productos y verticales.
- Detalles base para productos y verticales.
- Datos MVP mock centralizados.
- Repositorio admin desacoplado de la UI.
- App Android Flutter base con pantallas principales.
- Firebase preparado con reglas, indices, env example y adaptadores.
- Typecheck y build admin verificados.

## Lo que queda para fases siguientes

- Firebase real con proyecto y credenciales.
- Login real con Firebase Auth.
- Server actions o Cloud Functions para crear/editar datos.
- CRUD persistente.
- App Android conectada a backend.
- Pagos reales.
- Ordenes reales con calculo backend.
- Auditoria real en cada accion sensible.
- Tests de flujos criticos.

