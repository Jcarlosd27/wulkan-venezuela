import Link from "next/link";
import type { ReactNode } from "react";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav className="breadcrumb">
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`} className="breadcrumbItem">
          {item.href ? (
            <Link href={item.href}>{item.label}</Link>
          ) : (
            <span className="breadcrumbCurrent">{item.label}</span>
          )}
          {index < items.length - 1 && <span className="breadcrumbSep">/</span>}
        </div>
      ))}
    </nav>
  );
}
