/* ─── Gallery avatar metadata ──────────────────────────────────── */

export interface GalleryAvatar {
  id: string;
  label: string;
  category: "dev" | "analyst" | "qa" | "pm" | "ops" | "design" | "special";
  file: string; // path under /avatars/
}

export const GALLERY_AVATARS: GalleryAvatar[] = [
  { id: "dev-1",       label: "Dev Hoodie",         category: "dev",     file: "/avatars/dev-1.svg" },
  { id: "dev-2",       label: "Dev Glasses",        category: "dev",     file: "/avatars/dev-2.svg" },
  { id: "dev-3",       label: "Dev Cap",            category: "dev",     file: "/avatars/dev-3.svg" },
  { id: "mobile-1",   label: "Mobile Dev",          category: "dev",     file: "/avatars/mobile-1.svg" },
  { id: "analyst-1",  label: "Analyst (Funcional)", category: "analyst", file: "/avatars/analyst-1.svg" },
  { id: "analyst-2",  label: "Analyst (Técnico)",   category: "analyst", file: "/avatars/analyst-2.svg" },
  { id: "business-1", label: "Business Analyst",    category: "analyst", file: "/avatars/business-1.svg" },
  { id: "qa-1",       label: "QA Engineer",         category: "qa",      file: "/avatars/qa-1.svg" },
  { id: "pm-1",       label: "Project Manager",     category: "pm",      file: "/avatars/pm-1.svg" },
  { id: "tl-1",       label: "Tech Lead",           category: "pm",      file: "/avatars/tl-1.svg" },
  { id: "scrum-1",    label: "Scrum Master",        category: "pm",      file: "/avatars/scrum-1.svg" },
  { id: "dba-1",      label: "DBA",                 category: "ops",     file: "/avatars/dba-1.svg" },
  { id: "devops-1",   label: "DevOps",              category: "ops",     file: "/avatars/devops-1.svg" },
  { id: "data-1",     label: "Data Engineer",       category: "ops",     file: "/avatars/data-1.svg" },
  { id: "sec-1",      label: "Security Eng.",       category: "ops",     file: "/avatars/sec-1.svg" },
  { id: "architect-1",label: "Arquitecto",          category: "design",  file: "/avatars/architect-1.svg" },
  { id: "ux-1",       label: "UX Designer",         category: "design",  file: "/avatars/ux-1.svg" },
  { id: "robot-1",    label: "AI Agent",            category: "special", file: "/avatars/robot-1.svg" },
  { id: "ninja-1",    label: "Ninja",               category: "special", file: "/avatars/ninja-1.svg" },
  { id: "wizard-1",   label: "Wizard",              category: "special", file: "/avatars/wizard-1.svg" },
  { id: "dev-4",       label: "Dev Mujer",           category: "dev",     file: "/avatars/dev-4.svg" },
  { id: "dev-5",       label: "Dev Gorra Roja",      category: "dev",     file: "/avatars/dev-5.svg" },
  { id: "frontend-1",  label: "Frontend (JS)",        category: "dev",     file: "/avatars/frontend-1.svg" },
  { id: "backend-1",   label: "Backend (Python)",     category: "dev",     file: "/avatars/backend-1.svg" },
  { id: "fullstack-1", label: "Full Stack",           category: "dev",     file: "/avatars/fullstack-1.svg" },
  { id: "cloud-1",     label: "Cloud / DevOps",       category: "ops",     file: "/avatars/cloud-1.svg" },
  { id: "ml-1",        label: "ML Engineer",          category: "ops",     file: "/avatars/ml-1.svg" },
  { id: "qa-2",        label: "QA Engineer v2",       category: "qa",      file: "/avatars/qa-2.svg" },
  { id: "pm-2",        label: "PM v2",                category: "pm",      file: "/avatars/pm-2.svg" },
  { id: "tl-2",        label: "Tech Lead v2",         category: "pm",      file: "/avatars/tl-2.svg" },
  { id: "support-1",   label: "Soporte Técnico",      category: "ops",     file: "/avatars/support-1.svg" },
  { id: "ba-2",        label: "Business Analyst v2",  category: "analyst", file: "/avatars/ba-2.svg" },
  { id: "hacker-1",    label: "Hacker",               category: "special", file: "/avatars/hacker-1.svg" },
  { id: "coffee-1",    label: "Dev con Café",         category: "special", file: "/avatars/coffee-1.svg" },
];

/** Resolve an avatar value (gallery ID or base64) to a renderable src */
export function resolveAvatarSrc(value: string | null): string | null {
  if (!value) return null;
  if (value.startsWith("data:")) return value; // base64 custom
  const entry = GALLERY_AVATARS.find((a) => a.id === value);
  return entry ? entry.file : null;
}
