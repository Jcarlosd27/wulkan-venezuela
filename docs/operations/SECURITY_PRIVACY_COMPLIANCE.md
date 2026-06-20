# Seguridad y privacidad - matriz operativa

Ultima revision tecnica: 2026-06-17.

Este documento no reemplaza una revision legal local. Su objetivo es dejar una base tecnica y operativa
auditable para FVENTAS/Wulkan en admin panel, landing, API movil, app iOS y app Android.

## Alcance

- Mercados objetivo: Chile, Venezuela, Peru, Argentina, Colombia y Ecuador.
- Perfiles cubiertos: super administrador de plataforma, administradores de empresa suscriptora,
  vendedores, clientes B2B y usuarios moviles.
- Datos protegidos: credenciales, datos de contacto, empresa, RUT/documentos locales, direcciones,
  pedidos, credito solicitado/aprobado, comisiones, auditoria, tokens moviles y solicitudes de eliminacion.
- Principio comercial obligatorio: una empresa suscriptora solo puede ver, editar y explotar datos de su
  propia empresa, sus vendedores, sus clientes, su catalogo, sus condiciones de compra, sus pedidos y sus
  solicitudes de privacidad.

## Referencias normativas usadas

- Chile: Ley 19.628 y Ley 21.719. La Ley 21.719 regula el tratamiento de datos personales y crea la
  Agencia de Proteccion de Datos Personales; su entrada en vigencia indicada por fuentes oficiales es el
  2026-12-01.
  - https://www.leychile.cl/leychile/Navegar/imprimir?idNorma=1209272&idParte=10527468&idVersion=2026-12-01
  - https://digital.gob.cl/biblioteca/regulacion/ley-n-19628-sobre-proteccion-de-la-vida-privada/
- Peru: Ley 29733 y autoridad nacional de datos personales.
  - https://www.leyes.congreso.gob.pe/documentos/leyes/29733.pdf
  - https://www.gob.pe/anpd
- Argentina: Ley 25.326 y AAIP.
  - https://servicios.infoleg.gob.ar/infolegInternet/anexos/60000-64999/64790/texact.htm
  - https://www.argentina.gob.ar/aaip/datospersonales
- Colombia: Ley 1581 de 2012 y SIC.
  - https://www.sic.gov.co/proteccion-de-datos-personales
  - https://sedeelectronica.sic.gov.co/noticias/abc-del-proyecto-de-ley-de-proteccion-de-datos-personales-en-colombia
- Ecuador: Ley Organica de Proteccion de Datos Personales y reglamento.
  - https://www.telecomunicaciones.gob.ec/ley-y-reglamento-de-la-ley-de-proteccion-de-datos-personales/
- Venezuela: validar con asesoria local por no existir un regimen unico equivalente a las leyes modernas
  de proteccion de datos de otros paises. El proyecto debe aplicar controles equivalentes de transparencia,
  minimizacion, acceso, rectificacion, eliminacion, confidencialidad y seguridad.
- Apple App Store: las apps con creacion de cuenta deben permitir iniciar eliminacion de cuenta dentro de
  la app.
  - https://developer.apple.com/news/?id=12m75xbj
- Google Play: si la app permite cuentas, debe existir ruta in-app de eliminacion y enlace web funcional.
  - https://support.google.com/googleplay/android-developer/answer/13327111
  - https://support.google.com/googleplay/android-developer/answer/10787469
- Seguridad tecnica: OWASP ASVS y OWASP API Security.
  - https://owasp.org/www-project-application-security-verification-standard/
  - https://owasp.org/www-project-api-security/

## Controles implementados en el proyecto

- Consentimiento legal en alta de empresa:
  - `backend/api/app.py`: `/signup` exige aceptar terminos y politica de privacidad.
  - Se guarda version de terminos, version de privacidad, fecha, correo, IP y user agent en
    `company.legalAcceptance`.
- Paginas legales publicas:
  - `backend/api/templates/privacy_policy.html`
  - `backend/api/templates/terms_of_service.html`
  - `backend/api/templates/account_deletion.html`
- Eliminacion de cuenta:
  - Web publica: `/delete-account`.
  - API movil: `/api/v1/mobile/auth/request-account-deletion`.
  - Panel plataforma: modulo `platform_privacy` para revisar, aprobar, procesar o rechazar solicitudes.
  - La eliminacion completa anonimiza clientes/usuarios y deja trazabilidad comercial minima cuando aplica.
- Aislamiento multiempresa:
  - Tokens moviles incluyen `companyId`.
  - Las busquedas moviles validan que el sujeto y el token pertenezcan a la misma empresa.
  - El catalogo, pedidos, clientes, vendedores, condiciones de compra, anuncios y servicios tecnicos usan
    `companyId` como alcance.
- Seguridad del admin panel:
  - CSRF en POST del admin.
  - Cookies HttpOnly, SameSite y Secure en produccion.
  - Logout y revocacion de sesiones registran auditoria.
  - Permisos por rol y modulo para crear, editar, eliminar, exportar y aprobar.
- Cabeceras de seguridad:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: SAMEORIGIN`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy`
  - CSP en modo bloqueo para staging/produccion; modo reporte en desarrollo.
  - HSTS en produccion.
- Verificacion automatizada:
  - `backend/api/scripts/smoke_security.py`
  - `backend/api/scripts/smoke_admin_actions.py`
  - `backend/api/scripts/readiness_check.py`

## Requisitos de release antes de produccion

1. Ejecutar `python scripts/readiness_check.py --strict` en `backend/api`.
2. Ejecutar smoke de seguridad, acciones admin, reglas comerciales y flujo comercial.
3. Usar `FVENTAS_ENV=production`, PostgreSQL, S3/Spaces y `FVENTAS_REQUIRE_MOBILE_TOKEN=1`.
4. Definir `FVENTAS_SECRET_KEY` unico por ambiente y rotarlo si fue expuesto.
5. Confirmar que no existan cuentas demo activas ni productos demo en la base productiva.
6. Confirmar que todas las empresas activas tengan `legalAcceptance.accepted=true`.
7. Publicar enlaces de politica de privacidad, terminos y eliminacion en landing, App Store Connect y Play Console.
8. Revisar la declaracion de datos de Google Play y App Privacy de Apple con la conducta real de la app.
9. Mantener contratos/DPA con proveedores de hosting, almacenamiento, analitica, correo, pagos y soporte.
10. Documentar plazos de retencion por pais para facturacion, impuestos, auditoria, fraude y soporte.
11. Mantener rate limits activos para login, recuperacion, preferencias anonimas de landing y solicitudes publicas de eliminacion.
12. Confirmar que documentos internos no queden publicados por URL directa de storage; deben abrirse con enlace firmado y auditoria.

## Riesgos residuales que requieren decision operativa/legal

- Redaccion final de politica de privacidad por pais y razon social controladora/procesadora.
- Plazos exactos de retencion y eliminacion segun documentos tributarios y comerciales de cada pais.
- Transferencias internacionales y subencargados de tratamiento.
- Procedimiento formal de incidentes de seguridad, notificacion y bitacora.
- Registro de bases de datos o designacion de responsable/oficial cuando la ley local lo exija.
- Remover `unsafe-inline` de CSP mediante nonces o assets empaquetados para subir el nivel OWASP.
- Definir un calendario de auditoria periodica: mensual para readiness, trimestral para permisos y anual legal.
