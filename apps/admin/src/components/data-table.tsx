import type { ReactNode } from "react";

interface DataTableProps {
  columns: string[];
  children: ReactNode;
}

export function DataTable({ columns, children }: DataTableProps) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

