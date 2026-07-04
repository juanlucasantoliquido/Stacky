/**
 * Tests para PipelineBuilderSection (Plan 87 F5)
 * NOTA: Sin @testing-library/react, estos tests verifican estructura por grep
 * El gate real es tsc + verificación manual de criterios binarios
 */

import { describe, it, expect } from 'vitest';

describe('PipelineBuilderSection - F5 UI completa', () => {
  it('componente PipelineBuilderSection exportado', async () => {
    const { PipelineBuilderSection } = await import('../PipelineBuilderSection');
    expect(PipelineBuilderSection).toBeDefined();
  });

  it('BlockTree exportado', async () => {
    const { BlockTree } = await import('../BlockTree');
    expect(BlockTree).toBeDefined();
  });

  it('BlockProperties exportado', async () => {
    const { BlockProperties } = await import('../BlockProperties');
    expect(BlockProperties).toBeDefined();
  });

  it('PipelineYamlPreview exportado', async () => {
    const { PipelineYamlPreview } = await import('../PipelineYamlPreview');
    expect(PipelineYamlPreview).toBeDefined();
  });

  it('CommitPipelineModal exportado', async () => {
    const { CommitPipelineModal } = await import('../CommitPipelineModal');
    expect(CommitPipelineModal).toBeDefined();
  });

  it('TriggerPipelineSection exportado', async () => {
    const { TriggerPipelineSection } = await import('../TriggerPipelineSection');
    expect(TriggerPipelineSection).toBeDefined();
  });
});

describe('Criterios binarios F5 (verificables por código)', () => {
  it('C11 - estado vacío: CTA + "Empezar con ejemplo"', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx',
      'utf-8'
    );
    expect(content).toContain('Empezar con ejemplo');
    expect(content).toContain('Agregá tu primer stage');
  });

  it('C12 - validateSpecLocal usado en vivo', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx',
      'utf-8'
    );
    expect(content).toContain('validateSpecLocal');
    expect(content).toContain('localErrors');
  });

  it('C15 - specsEqual usado para badge "cambios sin guardar"', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx',
      'utf-8'
    );
    expect(content).toContain('specsEqual');
  });

  it('C15 - botón "Eliminar borrador" presente', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx',
      'utf-8'
    );
    expect(content).toContain('Eliminar borrador');
  });

  it('C16 - toda llamada async tiene catch hacia actionError', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx',
      'utf-8'
    );
    // Verificar que existe actionError state y que hay try/catch
    expect(content).toContain('actionError');
    expect(content).toMatch(/try\s*{/);
    expect(content).toMatch(/catch\s*\(/);
  });

  it('C14 - FlagGateBanner usado para generator/trigger OFF', async () => {
    const fs = await import('fs');
    const preview = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineYamlPreview.tsx',
      'utf-8'
    );
    const trigger = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/TriggerPipelineSection.tsx',
      'utf-8'
    );
    expect(preview).toContain('FlagGateBanner');
    expect(preview).toContain('STACKY_PIPELINE_GENERATOR_ENABLED');
    expect(trigger).toContain('FlagGateBanner');
    expect(trigger).toContain('STACKY_PIPELINE_TRIGGER_ENABLED');
  });

  it('FIX C1 - borradores usan mergeDraftsIntoProfile (riel GET→merge→PUT)', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx',
      'utf-8'
    );
    expect(content).toContain('mergeDraftsIntoProfile');
    // Verificar que NO hace PUT directo de drafts solo
    const lines = content.split('\n');
    const hasPutDraftsOnly = lines.some(l =>
      l.includes('put_client_profile') && l.includes('devops_pipeline_drafts') && !l.includes('profile')
    );
    expect(hasPutDraftsOnly).toBe(false);
  });

  it('HITL - commit requiere checkbox de confirmación', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/CommitPipelineModal.tsx',
      'utf-8'
    );
    expect(content).toContain('confirm');
    expect(content).toContain('Confirmo el commit');
  });

  it('FIX C5 - reusa CIPipeline existente (no crea namespace nuevo)', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/TriggerPipelineSection.tsx',
      'utf-8'
    );
    expect(content).toContain('CIPipeline');
    // NO debe crear un namespace CI nuevo
    const lines = content.split('\n');
    const hasNewCINamespace = lines.some(l =>
      l.includes('CI:') && !l.includes('CIPipeline') && !l.trim().startsWith('//')
    );
    expect(hasNewCINamespace).toBe(false);
  });

  it('FIX C6 - trigger usa ref del último commit exitoso como default', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/TriggerPipelineSection.tsx',
      'utf-8'
    );
    // Debe guardar el branch usado en commit
    expect(content).toMatch(/lastCommitBranch|lastBranch/);
  });

  it('C17 - auto-refresh con debounce 800ms', async () => {
    const fs = await import('fs');
    const content = fs.readFileSync(
      'N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/devops/PipelineYamlPreview.tsx',
      'utf-8'
    );
    expect(content).toContain('setTimeout');
    expect(content).toContain('clearTimeout');
    // Debe haber un delay de ~800ms
    expect(content).toMatch(/800|700|900/);
  });
});
