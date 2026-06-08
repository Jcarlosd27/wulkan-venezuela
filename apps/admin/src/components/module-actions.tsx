import Link from "next/link";

interface ModuleActionsProps {
  actions: Array<{
    label: string;
    href: string;
  }>;
}

export function ModuleActions({ actions }: ModuleActionsProps) {
  return (
    <div className="moduleActions">
      {actions.map((action) => (
        <Link href={action.href} key={action.href}>
          {action.label}
        </Link>
      ))}
    </div>
  );
}

