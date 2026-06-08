import { AdminShell } from "../../components/admin-shell";
import { FormField } from "../../components/form-field";
import { adminRepository } from "../../lib/repositories";
import { updateSettingsAction } from "./actions";

interface SettingsPageProps {
  searchParams?: Promise<{ status?: string }>;
}

export default async function SettingsPage({ searchParams }: SettingsPageProps) {
  const params = (await searchParams) ?? {};
  const settings = await adminRepository.getAppSettings();

  return (
    <AdminShell
      title="Settings operativos"
      description="Parametros de Venezuela, tasa USD/VES y soporte inicial."
      actionLabel="Guardar cambios"
    >
      {params.status === "invalid" ? (
        <section className="panel compactPanel">
          <p className="bodyCopy">La tasa USD/VES debe ser mayor a cero.</p>
        </section>
      ) : null}
      <form className="formPanel" action={updateSettingsAction}>
        <section className="formGrid">
          <FormField label="Pais operativo">
            <input value={settings.country} readOnly />
          </FormField>
          <FormField label="Moneda principal">
            <input value={settings.primaryCurrency} readOnly />
          </FormField>
          <FormField label="Moneda secundaria">
            <input value={settings.secondaryCurrency} readOnly />
          </FormField>
          <FormField label="Tasa USD/VES">
            <input name="exchangeRate" defaultValue={settings.exchangeRate.rate} inputMode="decimal" />
          </FormField>
          <FormField label="Origen de tasa">
            <input value={settings.exchangeRate.source} readOnly />
          </FormField>
          <FormField label="WhatsApp soporte">
            <input name="whatsappSupportNumber" defaultValue={settings.whatsappSupportNumber} />
          </FormField>
        </section>
        <section className="checkGrid">
          <label>
            <input type="checkbox" name="maintenanceMode" defaultChecked={settings.maintenanceMode} /> Modo mantenimiento
          </label>
        </section>
        <div className="formActions">
          <button type="submit">Guardar settings</button>
        </div>
      </form>
    </AdminShell>
  );
}
