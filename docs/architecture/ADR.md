# Registro de decisiones tecnicas

## ADR-001: Monolito modular para el inicio

**Decision:** construir Wulkan como monolito modular con apps y paquetes separados.

**Motivo:** permite lanzar rapido, mantener el dominio ordenado y evitar complejidad operativa prematura.

**Alternativas descartadas:** microservicios desde el inicio y backend empresarial completo antes de validar traccion.

**Revision:** cuando existan volumen alto de ordenes, reportes complejos o costos Firebase relevantes.

## ADR-002: Firebase como backend MVP

**Decision:** usar Firebase Auth, Firestore, Storage, Functions, Hosting y FCM en la primera etapa.

**Motivo:** reduce infraestructura inicial y permite concentrarse en operacion real del negocio.

**Condicion:** reglas criticas como pagos, permisos, auditoria y cambios de estado deben vivir en backend.

## ADR-003: Next.js para admin

**Decision:** construir el admin web con Next.js, TypeScript y Tailwind.

**Motivo:** el admin sera una herramienta operativa con tablas, filtros, permisos y reportes.

## ADR-004: Flutter para Android

**Decision:** construir la app movil inicial con Flutter.

**Motivo:** permite lanzar Android rapido y mantener base extensible a iOS futuro.

