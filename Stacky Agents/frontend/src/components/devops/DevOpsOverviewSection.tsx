/** Plan 239 F3 — Sección Resumen del cockpit DevOps. SOLO LECTURA:
 *  ningún botón de esta pantalla ejecuta nada; los de las alertas NAVEGAN.
 *
 *  CERO estilos inline y cero hex: toda la presentación sale de DevOpsCockpit.module.css,
 *  que a su vez solo usa tokens del plan 138 (⇒ hereda densidad del 150 y tema claro del 141).
 */
import { useQuery } from '@tanstack/react-query';
import { Card, StatusChip, SectionHeader, Skeleton, Button, Select } from '../ui';
import CopyAsButton from '../CopyAsButton'; // Plan 194 F3
import { DevOps } from '../../api/endpoints';
import { useLocalStorageState } from '../../hooks/useLocalStorageState';
import type { DevOpsSectionContext } from '../../pages/DevOpsPage';
import {
  buildKpiRows,
  statusLabel,
  blocksNote,
  sparkPoints,
  sparkAltText,
  fmtWhen,
  buildOverviewClipboardText,
} from './overviewModel';
import styles from '../../pages/DevOpsCockpit.module.css';

export function DevOpsOverviewSection({ ctx }: { ctx: DevOpsSectionContext }) {
  // Filtros persistidos (sobreviven a la sesión, sin backend ni config: hook de la casa).
  const [appId, setAppId] = useLocalStorageState<string | null>('stacky.devops.overview.appId', null);
  const [project, setProject] = useLocalStorageState<string | null>('stacky.devops.overview.project', null);
  const [windowDays, setWindowDays] = useLocalStorageState<number>('stacky.devops.overview.windowDays', 14);

  const q = useQuery({
    // Los filtros van en la queryKey: react-query cachea por alcance y no mezcla resultados.
    queryKey: ['devops-overview', appId, project, windowDays],
    queryFn: () => DevOps.overview({ appId, project, windowDays }),
    // `api.get` LANZA en cualquier non-2xx (incluido el 404 de un deploy viejo sin
    // el endpoint): con retry:false la rama isError muestra el estado vacío y la
    // pantalla nunca queda en blanco.
    retry: false,
    // F6: la sección solo sondea cuando es la visible; 60 s (dato de minutos, no de segundos).
    refetchInterval: ctx.visible === false ? false : 60_000,
  });

  if (q.isLoading) {
    return (
      <div className={styles.kpiGrid}>
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <Card key={i} padding="sm"><Skeleton lines={2} /></Card>
        ))}
      </div>
    );
  }

  if (q.isError || !q.data) {
    return (
      <p className={styles.empty}>
        No se pudo leer el resumen. Probá con el botón Actualizar; si persiste, revisá que la
        flag STACKY_DEVOPS_COCKPIT_ENABLED esté encendida (Configuración → Arnés, categoría DevOps).
      </p>
    );
  }

  const p = q.data;
  const st = statusLabel(p.status);
  const nowMs = Date.parse(p.generated_at); // reloj del SERVIDOR (no del navegador)
  const kpis = buildKpiRows(p, nowMs);
  const note = blocksNote(p);

  return (
    <section>
      <SectionHeader
        title={<span className={styles.titleRow}>Resumen <StatusChip tone={st.tone}>{st.text}</StatusChip></span>}
        subtitle={`Datos al ${fmtWhen(p.generated_at, Date.now())}. Solo lectura.`}
        actions={
          <>
            {/* Filtros: 3 Select de la primitiva del plan 162. `value` sale del ECO
                del backend (p.filters), no del estado local: si el backend descartó
                un filtro inválido, el selector muestra la verdad, no la intención. */}
            <Select
              aria-label="Aplicación"
              value={p.filters.app_id ?? ''}
              onChange={(e) => setAppId(e.target.value || null)}
            >
              <option value="">Todas las aplicaciones</option>
              {p.options.apps.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
            <Select
              aria-label="Proyecto de CI"
              value={p.filters.project ?? ''}
              onChange={(e) => setProject(e.target.value || null)}
            >
              <option value="">Todos los proyectos</option>
              {p.options.projects.map((pr) => <option key={pr} value={pr}>{pr}</option>)}
            </Select>
            <Select
              aria-label="Ventana de la tendencia"
              value={String(p.filters.window_days)}
              onChange={(e) => setWindowDays(Number(e.target.value))}
            >
              <option value="7">7 días</option>
              <option value="14">14 días</option>
              <option value="30">30 días</option>
            </Select>
            {/* Plan 239 F3.5 — copiar el resumen como texto llano. `build` es perezoso:
                copia lo que está en pantalla en ese momento, con el alcance aplicado.
                Si STACKY_COPY_EXPORT_ENABLED está OFF, CopyAsButton se auto-oculta. */}
            <CopyAsButton options={[{ label: 'Texto', build: () => buildOverviewClipboardText(p, nowMs) }]} />
            <Button variant="secondary" size="sm" onClick={() => q.refetch()}>Actualizar</Button>
          </>
        }
      />

      {/* KPIs */}
      <div className={styles.kpiGrid}>
        {kpis.map((k) => (
          <Card key={k.key} padding="sm">
            <div className={styles.kpiLabel}>{k.label}</div>
            <div className={styles.kpiValue}>{k.value}</div>
            {k.hint && <div className={styles.kpiHint}>{k.hint}</div>}
          </Card>
        ))}
      </div>

      {/* Alertas: cada una NAVEGA, ninguna EJECUTA */}
      {p.alerts.length > 0 && (
        <div className={styles.alerts}>
          {p.alerts.map((a) => (
            <div key={a.id} className={styles.alertRow}>
              <StatusChip tone={a.tone}>
                {a.tone === 'danger' ? 'Crítico' : a.tone === 'warning' ? 'Atención' : 'Info'}
              </StatusChip>
              <div className={styles.alertBody}>
                <div className={styles.alertTitle}>{a.title}</div>
                <div className={styles.alertDetail}>{a.detail}</div>
              </div>
              {ctx.setActiveSection && (
                <Button variant="secondary" size="sm" onClick={() => ctx.setActiveSection!(a.section)}>
                  Ir a la sección
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tendencia: SVG puro, sin dependencias nuevas. El título usa la ventana APLICADA. */}
      <SectionHeader title={`Tendencia (${p.filters.window_days} días)`} />
      <svg className={styles.spark} viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
        <polyline className={styles.sparkLine} points={sparkPoints(p.series.deploys_by_day)} />
        <polyline className={styles.sparkFail} points={sparkPoints(p.series.ci_failures_by_day)} />
      </svg>
      <p className={styles.kpiHint}>
        {sparkAltText('Despliegues', p.series.deploys_by_day, p.series.days)}{' · '}
        {sparkAltText('Fallos de CI', p.series.ci_failures_by_day, p.series.days)}
      </p>

      {/* Actividad reciente unificada */}
      <SectionHeader title="Actividad reciente" />
      {p.recent.length === 0
        ? <p className={styles.empty}>Todavía no hay despliegues ni corridas de CI registradas.</p>
        : (
          <div className={styles.timeline}>
            {p.recent.map((e, i) => (
              <div key={`${e.at}-${i}`} className={styles.eventRow}>
                <span className={styles.eventWhen}>{fmtWhen(e.at, nowMs)}</span>
                <span>{e.title}</span>
                <StatusChip tone={e.tone}>{e.status}</StatusChip>
              </div>
            ))}
          </div>
        )}

      {note && <p className={styles.blocksNote}>Fuentes sin datos: {note}</p>}
    </section>
  );
}

export default DevOpsOverviewSection;
