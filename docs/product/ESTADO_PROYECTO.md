# Estado del proyecto Wulkan

Fecha: 2026-05-20

## Porcentaje actual

Estimacion ejecutiva: **70% del proyecto total**.

El checklist ponderado por items marca **62.4%**:

- Hecho: 129 items.
- En progreso: 100 items.
- Pendiente: 58 items.
- Formula usada: `hecho + en progreso * 0.5`.

Ese 62.4% no representa el producto completo en produccion porque muchas piezas terminadas son arquitectura, documentacion, mocks, contratos y preparacion tecnica. Al ponderar por riesgo real de lanzamiento, el avance total queda en **70%** porque ya hay Server Actions persistentes para verticales, productos, empresas, ubicaciones, casos tecnicos, ordenes B2B, proyectos, pagos y cotizaciones; Firestore Emulator fue ejecutado con seed MVP validado; Android SDK quedo instalado; y la app movil fue compilada, instalada y ejecutada en un telefono Android fisico.

## Lectura por bloque

| Bloque | Estado | Avance estimado |
| --- | --- | --- |
| Arquitectura, negocio y stack | Cerrado como base | 90% |
| Monorepo, dominio y shared | Solido para MVP | 75% |
| Admin web | Navegable, con permisos, Firestore y CRUD inicial amplio preparado | 78% |
| Backend/Firebase | Functions, reglas, seed y Firestore Emulator validados localmente | 65% |
| App movil | Mock funcional instalada en telefono Android fisico; contrato, entorno, Flutter SDK, Android SDK, runner, repositorio mock/Firestore, bootstrap Firebase, Auth, carrito/checkout y tests | 72% |
| Datos persistentes | Seed ejecutado contra Firestore Emulator; falta probar Server Actions completas | 62% |
| Pagos Venezuela | Validacion manual persistente preparada; falta integracion real | 42% |
| Testing/QA | Typecheck/build, faltan pruebas de flujo | 20% |
| Operacion real | Documentada, falta validacion comercial | 15% |

## Fase actual

Estamos entre:

- **Fase 1 cerrada**: fundacion tecnica y admin operativo inicial.
- **Fase 2 avanzada**: ecommerce/catalogo/carrito/checkout en mock.
- **Fases 3, 4 y 5 iniciadas/avanzadas**: B2B, servicio tecnico y red fisica con backend preparado.

La etapa real ahora es: **transicion de prototipo avanzado a MVP conectado**.

## Lo que ya esta fuerte

- Contratos de dominio.
- Admin navegable.
- Reglas e indices Firestore.
- Repositorio mock/Firestore.
- Seed Firestore.
- Cloud Functions criticas iniciales.
- Sesion mock/Firebase preparada.
- Custom claims preparados.
- Matriz de permisos admin.
- App movil mock con flujos principales.
- Contrato de integracion movil.
- Configuracion movil por `--dart-define`.
- Flutter SDK estable instalado.
- Android Studio instalado.
- Android SDK instalado y licencias aceptadas.
- Runner Android creado con package `com.wulkan.mobile`.
- App movil instalada y ejecutada en telefono fisico `25098RA98G`.
- Repositorio movil preparado para mock/Firestore.
- Pantallas moviles principales desacopladas de datos hardcodeados.
- Bootstrap Firebase condicional preparado.
- Auth movil mock/Firebase preparado.
- Mapper Firestore alineado con seed MVP.
- Carrito/checkout movil preparado con payload de orden segura.
- Tests moviles para repositorio y shell.

## Lo que mas bloquea el salto de porcentaje

- Firebase real o emuladores corriendo.
- Login real admin y movil.
- CRUD persistente.
- Pruebas de flujos criticos.
- Pagos reales o integracion inicial.
- Firebase Android real.
- Storage para imagenes/comprobantes.

## Proximo objetivo

Subir de **70% a 75%** requiere:

1. Probar admin en `WULKAN_ADMIN_DATA_SOURCE=firestore`.
2. Probar CRUD y acciones persistentes contra Firestore Emulator.
3. Crear login admin real con Firebase Auth.
4. Activar Storage para imagenes/comprobantes.
5. Configurar Firebase Android real.
6. Conectar catalogo movil a Firestore Emulator.
7. Agregar pruebas de flujos criticos.

## Bloqueo actual

El bloqueo de Firebase CLI fue resuelto instalando `firebase-tools` y JDK 21. Firestore Emulator corrio en `127.0.0.1:8085` y el seed escribio 17 documentos en `wulkan-dev`.

El bloqueo movil bajo un nivel importante: Flutter SDK 3.44.0 esta instalado en `C:\Users\sidne\development\flutter`, Android Studio y Android SDK estan instalados, el runner Android existe, la app pasa `flutter analyze` y `flutter test`, y Wulkan Mobile fue instalada y ejecutada en el telefono fisico `25098RA98G`. Falta Firebase Android real para pasar de mock a datos conectados.
