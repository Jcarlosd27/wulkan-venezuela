import type { EntityStatus, ProductType } from "@wulkan/domain";

export const productTypeOptions: Array<{ value: ProductType; label: string }> = [
  { value: "machine", label: "Maquinaria" },
  { value: "spare_part", label: "Repuesto" },
  { value: "accessory", label: "Accesorio" },
  { value: "service", label: "Servicio" },
  { value: "project", label: "Proyecto tecnico" }
];

export const entityStatusOptions: Array<{ value: EntityStatus; label: string }> = [
  { value: "active", label: "Activo" },
  { value: "pending", label: "Pendiente" },
  { value: "inactive", label: "Inactivo" },
  { value: "suspended", label: "Suspendido" },
  { value: "archived", label: "Archivado" }
];

