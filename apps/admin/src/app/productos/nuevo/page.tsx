import { AdminShell } from "../../../components/admin-shell";
import { Breadcrumb } from "../../../components/breadcrumb";
import { FormField } from "../../../components/form-field";
import { ErrorState } from "../../../components/error-state";
import { entityStatusOptions, productTypeOptions } from "../../../lib/form-options";
import { adminRepository } from "../../../lib/repositories";
import { createProductAction } from "../actions";

interface NewProductPageProps {
  searchParams?: Promise<{
    status?: string;
  }>;
}

export default async function NewProductPage({ searchParams }: NewProductPageProps) {
  const params = (await searchParams) ?? {};
  const verticals = await adminRepository.listVerticals();

  return (
    <AdminShell
      title="Nuevo producto"
      description="Agregar producto al catálogo técnico con precio, stock y validación comercial."
    >
      <Breadcrumb
        items={[
          { label: "Dashboard", href: "/" },
          { label: "Productos", href: "/productos" },
          { label: "Nuevo" }
        ]}
      />

      {params.status === "invalid" ? (
        <ErrorState
          title="Validación incompleta"
          message="Nombre, SKU y categoría principal son obligatorios."
        />
      ) : null}

      <form className="formPanel" action={createProductAction}>
        {/* ============================================
           SECCIÓN 1: INFO BÁSICA
           ============================================ */}
        <section className="formSection">
          <div className="formSectionHeader">
            <h2>Información básica</h2>
            <span>Datos identificativos del producto</span>
          </div>

          <div className="formGrid">
            <FormField label="Nombre comercial" required hint="Como aparece en catálogo público">
              <input name="title" placeholder="Ej: Motosierra 45cc" required />
            </FormField>
            <FormField label="SKU" required hint="Código único interno">
              <input name="sku" placeholder="WUL-MOT-45CC" required />
            </FormField>
            <FormField label="Categoría principal" required hint="Vertical de negocio">
              <select name="verticalId" defaultValue="" required aria-label="Selecciona categoría">
                <option value="" disabled>
                  Selecciona categoría
                </option>
                {verticals.map((vertical) => (
                  <option value={vertical.id} key={vertical.id}>
                    {vertical.name}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label="Tipo de producto" required>
              <select name="type" defaultValue="machine" required aria-label="Tipo de producto">
                {productTypeOptions.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FormField>
          </div>
        </section>

        {/* ============================================
           SECCIÓN 2: CLASIFICACIÓN
           ============================================ */}
        <section className="formSection">
          <div className="formSectionHeader">
            <h2>Clasificación interna</h2>
            <span>Configuración administrativa</span>
          </div>

          <div className="formGrid">
            <FormField label="Subcategoría interna" hint="Para reportes internos">
              <input name="categoryId" placeholder="Ej: motosierras, repuestos, jardinería" />
            </FormField>
            <FormField label="Empresa vendedora" required>
              <input name="sellerId" defaultValue="avalon-group" placeholder="avalon-group" required />
            </FormField>
            <FormField label="Estado" required>
              <select name="status" defaultValue="active" required aria-label="Estado del producto">
                {entityStatusOptions.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </FormField>
          </div>
        </section>

        {/* ============================================
           SECCIÓN 3: PRECIOS Y STOCK
           ============================================ */}
        <section className="formSection">
          <div className="formSectionHeader">
            <h2>Precios y disponibilidad</h2>
            <span>Configuración comercial en USD</span>
          </div>

          <div className="formGrid">
            <FormField label="Precio público (USD)" required hint="Precio al que ven clientes finales">
              <input name="publicPrice" inputMode="decimal" placeholder="0.00" required />
            </FormField>
            <FormField label="Precio B2B (USD)" hint="Descuento para ferreteros">
              <input name="b2bPrice" inputMode="decimal" placeholder="0.00" />
            </FormField>
            <FormField label="Stock inicial (unidades)" required hint="Cantidad disponible">
              <input name="stock" inputMode="numeric" placeholder="0" required />
            </FormField>
          </div>
        </section>

        {/* ============================================
           SECCIÓN 4: DESCRIPCIÓN
           ============================================ */}
        <section className="formSection">
          <div className="formSectionHeader">
            <h2>Descripción técnica</h2>
            <span>Contenido visible para clientes y operadores</span>
          </div>

          <FormField
            label="Descripción"
            required
            hint="Incluye uso recomendado, compatibilidad o condiciones de cotización"
          >
            <textarea
              name="description"
              rows={5}
              placeholder="Describe el producto para clientes, ferreteros y operadores."
              required
            />
          </FormField>
        </section>

        {/* ============================================
           SECCIÓN 5: MULTIMEDIA Y DOCUMENTOS
           ============================================ */}
        <section className="formSection">
          <div className="formSectionHeader">
            <h2>Multimedia y documentación</h2>
            <span>Recursos técnicos y visuales</span>
          </div>

          <div className="formGrid">
            <FormField label="Imágenes del producto" hint="Una URL por línea. La primera es la imagen principal">
              <textarea
                name="imageUrls"
                rows={4}
                placeholder="https://cdn.wulkan.com/producto/frontal.jpg&#10;https://cdn.wulkan.com/producto/lateral.jpg"
              />
            </FormField>
            <FormField label="Garantía comercial" hint="Ej: 6 meses por defecto de fábrica">
              <input name="warranty" placeholder="6 meses por defecto de fábrica" />
            </FormField>
            <FormField label="Ficha técnica (URL)" hint="Documento PDF o página web">
              <input name="technicalSheetUrl" placeholder="https://..." />
            </FormField>
            <FormField label="Manual de usuario (URL)" hint="Documento de instrucciones">
              <input name="manualUrl" placeholder="https://..." />
            </FormField>
          </div>
        </section>

        {/* ============================================
           SECCIÓN 6: VALIDACIONES ESPECIALES
           ============================================ */}
        <section className="formSection">
          <div className="formSectionHeader">
            <h2>Validaciones especiales</h2>
            <span>Reglas operativas para este producto</span>
          </div>

          <div className="checkGrid">
            <label className="checkboxLabel">
              <input type="checkbox" name="requiresQuote" /> Requiere cotización antes de compra
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" name="requiresInstallation" /> Requiere instalación profesional
            </label>
            <label className="checkboxLabel">
              <input type="checkbox" name="requiresTechnicalValidation" /> Requiere validación técnica de Wulkan
            </label>
          </div>
        </section>

        {/* ============================================
           ACCIONES
           ============================================ */}
        <div className="formActions">
          <a href="/productos" className="btnSecondary">
            Cancelar
          </a>
          <button type="submit" className="btnPrimary">
            Guardar producto
          </button>
        </div>
      </form>
    </AdminShell>
  );
}
