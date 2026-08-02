import type { LucideIcon } from "lucide-react";
import {
  Zap, ClipboardList, Inbox, Wrench, LayoutDashboard, ScrollText,
  History, Stethoscope, FileText, Brain, Server, ArrowRightLeft,
  Database, Settings, DollarSign, Compass, Dna, Ambulance,
  CalendarDays, // Plan 283 — los 18 anteriores estaban TODOS tomados: no habia ninguno libre
  Send,         // Plan 293 — tablero de trabajo
} from "lucide-react";

// OJO: importar el icono NO alcanza. Hay que agregarlo TAMBIEN a este mapa; son
// dos ediciones y olvidar la segunda deja el tab sin icono, sin romper tsc.
export const ICON_BY_NAME: Record<string, LucideIcon> = {
  Zap, ClipboardList, Inbox, Wrench, LayoutDashboard, ScrollText,
  History, Stethoscope, FileText, Brain, Server, ArrowRightLeft,
  Database, Settings, DollarSign, Compass, Dna, Ambulance,
  CalendarDays, // Plan 283
  Send,         // Plan 293
};
