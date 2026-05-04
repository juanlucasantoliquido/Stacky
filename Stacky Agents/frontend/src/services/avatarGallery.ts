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
];

/** Resolve an avatar value (gallery ID or base64) to a renderable src */
export function resolveAvatarSrc(value: string | null): string | null {
  if (!value) return null;
  if (value.startsWith("data:")) return value; // base64 custom
  const entry = GALLERY_AVATARS.find((a) => a.id === value);
  return entry ? entry.file : null;
}
