"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useState } from "react";
import { getAdminSession } from "../lib/auth";
import { getVisibleNavItems } from "../lib/permissions";

interface AdminShellProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  children: ReactNode;
}

export function AdminShell({ title, description, actionLabel, onAction, children }: AdminShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const session = getAdminSession();
  const navItems = getVisibleNavItems(session);

  return (
    <main className="shell">
      <button
        className="sidebarToggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label="Abrir/cerrar navegación"
      >
        ☰
      </button>

      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="brand">
          <img className="brandLogo" src="/brand/wulkan-logo.svg" alt="Wulkan" />
          <small>Admin Venezuela</small>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <Link
              href={item.href}
              key={item.href}
              onClick={() => setSidebarOpen(false)}
              className="navLink"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="sessionBox">
          <small>Sesión {session.authMode}</small>
          <strong>{session.user.name}</strong>
          <span>{session.user.role}</span>
          <span className={session.claimsReady ? "claimsReady" : "claimsPending"}>
            {session.claimsReady ? "✓ Claims listos" : "⏳ Claims pendientes"}
          </span>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          {actionLabel && (
            <button type="button" className="btnPrimary" onClick={onAction}>
              {actionLabel}
            </button>
          )}
        </header>
        {children}
      </section>
    </main>
  );
}
