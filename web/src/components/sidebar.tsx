"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Disc3,
  LayoutDashboard,
  ListMusic,
  Wand2,
  FolderSearch,
  Cloud,
  Settings,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/library", label: "Library", icon: ListMusic },
  { href: "/set-builder", label: "Set Builder", icon: Wand2 },
  { href: "/scan", label: "Scan Library", icon: FolderSearch },
  { href: "/soundcloud", label: "SoundCloud", icon: Cloud },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 w-64 bg-zinc-900 border-r border-zinc-800 flex flex-col">
      <div className="p-6 flex items-center gap-3">
        <Disc3 className="w-8 h-8 text-purple-400 animate-spin" style={{ animationDuration: "3s" }} />
        <div>
          <h1 className="text-lg font-bold text-white">DJ Set Planner</h1>
          <p className="text-xs text-zinc-500">Music Theory Engine</p>
        </div>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-purple-500/20 text-purple-300"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
              }`}
            >
              <Icon className="w-5 h-5" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-zinc-800">
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <Settings className="w-4 h-4" />
          <span>v0.1.0</span>
        </div>
      </div>
    </aside>
  );
}
