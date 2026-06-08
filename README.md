# Wulkan

Wulkan es una plataforma tecnica B2B2C enfocada inicialmente en Venezuela para venta, abastecimiento, repuestos, servicios tecnicos, instalaciones y soporte autorizado.

La base del proyecto sigue una estrategia de monolito modular:

- `apps/mobile`: app Android Flutter para clientes, ferreteros y servicios tecnicos.
- `apps/admin`: admin web Next.js para Wulkan, operadores y empresas.
- `packages/domain`: contratos y entidades puras del negocio.
- `packages/shared`: constantes, estados y utilidades comunes.
- `packages/ui`: componentes visuales compartidos para web.
- `packages/config`: configuracion compartida de ambientes y colecciones.
- `backend/functions`: Cloud Functions iniciales para reglas criticas.
- `backend/api`: espacio reservado para una futura API NestJS.
- `infra/firebase`: reglas, indices y configuracion Firebase.
- `docs`: documentacion viva de producto, arquitectura y operacion.

## Prioridad MVP

1. Venezuela como unico pais operativo inicial.
2. Catalogo tecnico multi-vertical.
3. Productos, repuestos, compatibilidades simples y busqueda.
4. Ordenes B2C.
5. Ordenes B2B para ferreteros.
6. Casos de servicio tecnico.
7. Pagos asistidos y validacion por operador.
8. Auditoria de acciones sensibles.

## Comandos previstos

Estos comandos quedaran activos cuando se instalen dependencias:

```bash
pnpm install
pnpm dev:admin
pnpm test
pnpm lint
```
