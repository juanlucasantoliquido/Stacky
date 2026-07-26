import { useEffect, useState } from "react";

import { rawGet, rawPost } from "../../api/client";
import { DbCompare, HarnessFlags } from "../../api/endpoints";
import Select from "../ui/Select";
import { Button, Checkbox, Dialog } from "../ui";
import {
  deployStatusByEnv,
  executableEnvs,
  idempotencyWarning,
  ledgerRow,
  type EnvOption,
  type LedgerEntry,
  type ScriptRef,
} from "./sqlExecPanelLogic";
import panel from "./GatesPanel.module.css";
import styles from "./dbcompare.module.css";

interface ExecResponse {
  ok: boolean;
  dry_run: boolean;
  statement_count: number;
  rows_affected: number | null;
  error: string | null;
  statements?: string[];
  partial_effects_possible?: boolean;
  ledger_write_failed?: boolean;
}

/**
 * Plan 200 R3/R4 — Ejecutar un script contra un ambiente, y ver dónde ya corrió.
 *
 * Es la única pantalla del producto que dispara una ESCRITURA en una base del
 * operador, así que:
 *  - nunca manda SQL crudo: manda una REFERENCIA y el backend re-lee el archivo;
 *  - siempre exige confirmar en un diálogo, con el nombre y el sha a la vista;
 *  - ofrece el dry-run primero;
 *  - con la capacidad apagada el panel sigue mostrando la TRAZA (read-only) y
 *    solo se deshabilita el botón. Ocultar la traza escondería justamente la
 *    información que sirve para auditar lo que ya pasó.
 */
export default function SqlExecPanel({
  scripts,
  ticketRef,
  incidentId,
}: {
  scripts: ScriptRef[];
  ticketRef?: string | null;
  incidentId?: string | null;
}) {
  const [envs, setEnvs] = useState<EnvOption[]>([]);
  const [alias, setAlias] = useState("");
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [chainOk, setChainOk] = useState(true);
  const [execEnabled, setExecEnabled] = useState(false);
  const [elegido, setElegido] = useState<ScriptRef | null>(null);
  const [bloqueUnico, setBloqueUnico] = useState(false);
  const [resultado, setResultado] = useState<ExecResponse | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [corriendo, setCorriendo] = useState(false);

  useEffect(() => {
    DbCompare.listEnvironments()
      .then((r) => {
        const posibles = executableEnvs((r.environments ?? []) as unknown as EnvOption[]);
        setEnvs(posibles);
        setAlias((previo) => previo || posibles[0]?.alias || "");
      })
      .catch(() => setAviso("No se pudieron cargar los ambientes"));

    // La capacidad se lee del panel de flags que ya existe; no se inventa un
    // endpoint de estado.
    HarnessFlags.list()
      .then((r) => {
        const flag = (r.flags ?? []).find((f) => f.key === "STACKY_SQL_EXEC_ENABLED");
        setExecEnabled(Boolean(flag?.value));
      })
      .catch(() => setExecEnabled(false));
  }, []);

  const recargarTraza = () => {
    const qs = ticketRef ? `?ticket_ref=${encodeURIComponent(ticketRef)}` : "";
    rawGet<{ ok: boolean; entries: LedgerEntry[]; chain_ok: boolean }>(
      `/api/db-compare/sql-exec-ledger${qs}`,
    ).then((r) => {
      if (!r.ok || !r.data) return; // 404 = traza apagada: el panel sigue sirviendo
      setEntries(r.data.entries ?? []);
      setChainOk(r.data.chain_ok !== false);
    });
  };

  useEffect(recargarTraza, [ticketRef]);

  async function ejecutar(dryRun: boolean, force = false) {
    if (!elegido || !alias) return;
    setCorriendo(true);
    setAviso(null);
    // Ejecución POR REFERENCIA: el SQL nunca viaja desde acá.
    const r = await rawPost<ExecResponse>(
      `/api/db-compare/environments/${encodeURIComponent(alias)}/execute-script`,
      {
        confirm: true,
        script_ref: elegido,
        fingerprint: elegido.sha256,
        dry_run: dryRun,
        split_statements: !bloqueUnico,
        ticket_ref: ticketRef ?? null,
        incident_id: incidentId ?? null,
        force,
      },
    );
    setCorriendo(false);

    if (r.ok && r.data) {
      setResultado(r.data);
      if (r.data.ledger_write_failed) {
        // El efecto ocurrió pero no quedó registrado: si esto no se dice, el
        // operador re-ejecuta a ciegas creyendo que no pasó nada.
        setAviso("Ejecutado pero NO registrado en la bitácora: verificá antes de re-ejecutar.");
      }
      recargarTraza();
      return;
    }

    const kind = (r.errorBody as { kind?: string } | null)?.kind;
    if (kind === "script_stale" || kind === "fingerprint_mismatch") {
      setAviso("El script cambió desde que se mostró. Refrescá el preview y volvé a intentar.");
    } else if (kind === "already_executed") {
      setAviso("Este script ya se ejecutó en este ambiente. Usá «Forzar» si querés repetirlo.");
    } else if (r.status === 403) {
      setAviso("Este ambiente no tiene habilitada la ejecución (opt-in por ambiente).");
    } else if (r.status === 404) {
      setAviso("La ejecución SQL está deshabilitada.");
    } else {
      setAviso("No se pudo ejecutar el script.");
    }
  }

  if (!scripts?.length) return null;

  const estados = deployStatusByEnv(entries, envs.map((e) => e.alias), elegido?.sha256 ?? "");
  const yaCorrio = elegido ? idempotencyWarning(entries, alias, elegido.sha256) : "";

  return (
    <section className={panel.panel}>
      <h3>Despliegue SQL por ambiente</h3>

      {!chainOk && (
        <div className={styles.errorBanner}>
          La bitácora fue alterada: los registros de abajo no son confiables.
        </div>
      )}
      {aviso && <div className={styles.errorBanner}>{aviso}</div>}

      <label>
        Ambiente
        <Select value={alias} onChange={(e) => setAlias(e.target.value)}>
          {envs.length === 0 && <option value="">Ningún ambiente habilitado para ejecutar</option>}
          {envs.map((e) => (
            <option key={e.alias} value={e.alias}>
              {e.alias} ({e.engine})
            </option>
          ))}
        </Select>
      </label>

      <ul className={panel.list}>
        {scripts.map((s) => (
          <li key={s.sha256} className={panel.item}>
            <strong>{s.name}</strong>
            <span className={styles.recency}>{s.sha256.slice(0, 8)}</span>
            {/* Dónde ya corrió, SIN ejecutar nada. */}
            {envs.map((e) => (
              <span key={e.alias} className={styles.chip}>
                {e.alias}: {deployStatusByEnv(entries, [e.alias], s.sha256)[e.alias]}
              </span>
            ))}
            <Button
              size="sm"
              disabled={!execEnabled || !alias}
              title={
                execEnabled
                  ? undefined
                  : "Habilitá ejecución SQL en Configuración > Flags"
              }
              onClick={() => {
                setElegido(s);
                setResultado(null);
                setAviso(null);
              }}
            >
              Ejecutar en ambiente…
            </Button>
          </li>
        ))}
      </ul>

      {entries.length > 0 && (
        <details>
          <summary>Traza de ejecuciones ({entries.length})</summary>
          <ul className={panel.list}>
            {entries.map((e) => (
              <li key={`${e.script_sha256}-${e.executed_at}`} className={panel.detail}>
                {ledgerRow(e)}
                {e.error ? ` — ${e.error}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}

      <Dialog
        open={Boolean(elegido)}
        onClose={() => setElegido(null)}
        title="Ejecutar script contra un ambiente"
      >
        {elegido && (
          <div>
            <p>
              <strong>{elegido.name}</strong> · {elegido.sha256.slice(0, 12)}
            </p>
            <p>
              Ambiente: <strong>{alias}</strong> · estado actual:{" "}
              {estados[alias] ?? "no-registrado"}
            </p>
            {yaCorrio && <div className={styles.errorBanner}>{yaCorrio}</div>}

            <Checkbox
              label="Ejecutar como bloque único (PL/SQL)"
              checked={bloqueUnico}
              onChange={(e) => setBloqueUnico(e.target.checked)}
            />

            {resultado && (
              <div className={panel.detail}>
                {resultado.dry_run
                  ? `Dry-run: ${resultado.statement_count} sentencia(s).`
                  : resultado.ok
                    ? `Ejecutado: ${resultado.rows_affected ?? 0} fila(s) afectada(s).`
                    : `Falló: ${resultado.error}`}
                {resultado.partial_effects_possible && (
                  <div className={styles.errorBanner}>
                    Contiene DDL: sin rollback atómico en Oracle/MySQL.
                  </div>
                )}
              </div>
            )}

            <footer>
              <Button size="sm" onClick={() => void ejecutar(true)} disabled={corriendo}>
                Dry-run
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={() => void ejecutar(false)}
                disabled={corriendo || !execEnabled}
              >
                Ejecutar de verdad
              </Button>
              {yaCorrio && (
                <Button size="sm" onClick={() => void ejecutar(false, true)} disabled={corriendo}>
                  Forzar
                </Button>
              )}
              <Button size="sm" onClick={() => setElegido(null)}>
                Cerrar
              </Button>
            </footer>
          </div>
        )}
      </Dialog>
    </section>
  );
}
