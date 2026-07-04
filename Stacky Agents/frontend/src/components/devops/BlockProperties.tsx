/**
 * BlockProperties (Plan 87 F5)
 * Panel de propiedades del bloque seleccionado
 */
import React from 'react';
import type { PipelineSpecDraft } from '../../devops/specBuilder';
import { updateStage, updateJob, updateStep } from '../../devops/specBuilder';

export interface BlockPropertiesProps {
  spec: PipelineSpecDraft;
  setSpec: (spec: PipelineSpecDraft) => void;
  selected: { si?: number; ji?: number; sti?: number } | null;
}

const parseCsv = (str: string): string[] => {
  return str.split(',').map(s => s.trim()).filter(s => s);
};

const parseKeyValues = (str: string): Record<string, string> => {
  const result: Record<string, string> = {};
  str.split('\n').forEach(line => {
    const [key, ...valueParts] = line.split('=');
    if (key && key.trim()) {
      result[key.trim()] = valueParts.join('=').trim();
    }
  });
  return result;
};

const formatKeyValues = (obj: Record<string, string>): string => {
  return Object.entries(obj).map(([k, v]) => `${k}=${v}`).join('\n');
};

export const BlockProperties: React.FC<BlockPropertiesProps> = ({ spec, setSpec, selected }) => {
  if (!selected) {
    // Propiedades del pipeline
    return (
      <div style={{ padding: '16px', backgroundColor: '#f8f9fa', borderRadius: '4px' }}>
        <h3 style={{ marginTop: 0 }}>Propiedades del Pipeline</h3>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Variables (una por línea: key=value)</label>
          <textarea
            value={formatKeyValues(spec.variables)}
            onChange={(e) => setSpec({ ...spec, variables: parseKeyValues(e.target.value) })}
            placeholder="KEY=value"
            style={{ width: '100%', minHeight: '80px', fontFamily: 'monospace', fontSize: '12px', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Trigger branches (CSV)</label>
          <input
            type="text"
            value={spec.trigger_branches.join(',')}
            onChange={(e) => setSpec({ ...spec, trigger_branches: parseCsv(e.target.value) })}
            placeholder="main,develop"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <details>
          <summary style={{ cursor: 'pointer', marginBottom: '8px' }}>Avanzado (YAML crudo)</summary>
          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'block', marginBottom: '4px' }}>Target</label>
            <select
              value={spec.raw_yaml_target ?? ''}
              onChange={(e) => setSpec({ ...spec, raw_yaml_target: e.target.value as 'ado' | 'gitlab' | null })}
              style={{ width: '100%', padding: '8px' }}
            >
              <option value="">(ninguno)</option>
              <option value="ado">Azure DevOps</option>
              <option value="gitlab">GitLab CI</option>
            </select>
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '4px' }}>YAML crudo</label>
            <textarea
              value={spec.raw_yaml ?? ''}
              onChange={(e) => setSpec({ ...spec, raw_yaml: e.target.value })}
              placeholder="Escape hatch: YAML raw de fallback..."
              style={{ width: '100%', minHeight: '100px', fontFamily: 'monospace', fontSize: '12px', padding: '8px' }}
            />
          </div>
        </details>
      </div>
    );
  }

  if (selected.sti !== undefined && selected.ji !== undefined && selected.si !== undefined) {
    // Step seleccionado (índices en locales: el narrowing de `selected.*` no
    // se propaga dentro de los closures onChange más abajo)
    const si = selected.si;
    const ji = selected.ji;
    const sti = selected.sti;
    const step = spec.stages[si].jobs[ji].steps[sti];
    return (
      <div style={{ padding: '16px', backgroundColor: '#fff3cd', borderRadius: '4px' }}>
        <h3 style={{ marginTop: 0 }}>Propiedades del Step</h3>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Nombre</label>
          <input
            type="text"
            value={step.name}
            onChange={(e) => setSpec(updateStep(spec, si, ji, sti, { name: e.target.value }))}
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Script</label>
          <textarea
            value={step.script}
            onChange={(e) => setSpec(updateStep(spec, si, ji, sti, { script: e.target.value }))}
            placeholder="echo 'hola mundo'"
            style={{ width: '100%', minHeight: '120px', fontFamily: 'monospace', fontSize: '12px', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Working directory</label>
          <input
            type="text"
            value={step.working_directory ?? ''}
            onChange={(e) => setSpec(updateStep(spec, si, ji, sti, { working_directory: e.target.value || null }))}
            placeholder="/path/to/dir"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Condition</label>
          <input
            type="text"
            value={step.condition ?? ''}
            onChange={(e) => setSpec(updateStep(spec, si, ji, sti, { condition: e.target.value || null }))}
            placeholder="success()"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Environment variables (una por línea: key=value)</label>
          <textarea
            value={formatKeyValues(step.env)}
            onChange={(e) => setSpec(updateStep(spec, si, ji, sti, { env: parseKeyValues(e.target.value) }))}
            placeholder="KEY=value"
            style={{ width: '100%', minHeight: '80px', fontFamily: 'monospace', fontSize: '12px', padding: '8px' }}
          />
        </div>
      </div>
    );
  }

  if (selected.ji !== undefined && selected.si !== undefined) {
    // Job seleccionado
    const si = selected.si;
    const ji = selected.ji;
    const job = spec.stages[si].jobs[ji];
    return (
      <div style={{ padding: '16px', backgroundColor: '#d1ecf1', borderRadius: '4px' }}>
        <h3 style={{ marginTop: 0 }}>Propiedades del Job</h3>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Nombre</label>
          <input
            type="text"
            value={job.name}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { name: e.target.value }))}
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Image</label>
          <input
            type="text"
            value={job.image ?? ''}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { image: e.target.value || null }))}
            placeholder="node:18"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Pool VM Image</label>
          <input
            type="text"
            value={job.pool_vm_image ?? ''}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { pool_vm_image: e.target.value || null }))}
            placeholder="ubuntu-20.04"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Runner Tags (CSV)</label>
          <input
            type="text"
            value={job.runner_tags.join(',')}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { runner_tags: parseCsv(e.target.value) }))}
            placeholder="docker,linux"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Variables (una por línea: key=value)</label>
          <textarea
            value={formatKeyValues(job.variables)}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { variables: parseKeyValues(e.target.value) }))}
            placeholder="KEY=value"
            style={{ width: '100%', minHeight: '60px', fontFamily: 'monospace', fontSize: '12px', padding: '8px' }}
          />
        </div>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Artifacts (CSV)</label>
          <input
            type="text"
            value={job.artifacts.join(',')}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { artifacts: parseCsv(e.target.value) }))}
            placeholder="dist/*.zip"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Services (CSV)</label>
          <input
            type="text"
            value={job.services.join(',')}
            onChange={(e) => setSpec(updateJob(spec, si, ji, { services: parseCsv(e.target.value) }))}
            placeholder="docker:dind,postgres:14"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
      </div>
    );
  }

  if (selected.si !== undefined) {
    // Stage seleccionado
    const si = selected.si;
    const stage = spec.stages[si];
    return (
      <div style={{ padding: '16px', backgroundColor: '#e7f3ff', borderRadius: '4px' }}>
        <h3 style={{ marginTop: 0 }}>Propiedades del Stage</h3>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Nombre</label>
          <input
            type="text"
            value={stage.name}
            onChange={(e) => setSpec(updateStage(spec, si, { name: e.target.value }))}
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Condition</label>
          <input
            type="text"
            value={stage.condition ?? ''}
            onChange={(e) => setSpec(updateStage(spec, si, { condition: e.target.value || null }))}
            placeholder="success('build')"
            style={{ width: '100%', padding: '8px' }}
          />
        </div>
      </div>
    );
  }

  return null;
};
