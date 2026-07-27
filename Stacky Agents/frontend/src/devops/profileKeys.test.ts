/**
 * profileKeys.test.ts — Plan 98 F5.
 * Unit puro sobre el helper de escritura por clave. Sin red, sin render.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
  },
}));

import { api } from '../api/client';
import { saveProfileKey } from './profileKeys';

const mocked = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  mocked.get.mockReset();
  mocked.put.mockReset();
  mocked.patch.mockReset();
  mocked.patch.mockResolvedValue({ ok: true });
  mocked.put.mockResolvedValue({ ok: true });
});

describe('Plan 98 F5 — saveProfileKey', () => {
  it('con flag ON hace UN PATCH a la URL exacta con body {value} y nada más', async () => {
    const drafts = [{ name: 'd1', spec: {}, updated_at: 'x' }];
    await saveProfileKey('p1', 'devops_pipeline_drafts', drafts, true);

    expect(mocked.patch).toHaveBeenCalledTimes(1);
    expect(mocked.patch).toHaveBeenCalledWith(
      '/api/projects/p1/client-profile/keys/devops_pipeline_drafts',
      { value: drafts },
    );
    expect(mocked.get).not.toHaveBeenCalled();
    expect(mocked.put).not.toHaveBeenCalled();
  });

  it('con flag OFF ejecuta GET → merge → PUT preservando las otras keys', async () => {
    mocked.get.mockResolvedValue({
      profile: { otra_key: 'intacta', devops_publication_presets: ['viejo'] },
    });

    await saveProfileKey('p1', 'devops_publication_presets', ['nuevo'], false);

    expect(mocked.patch).not.toHaveBeenCalled();
    expect(mocked.get).toHaveBeenCalledWith('/api/projects/p1/client-profile');
    expect(mocked.put).toHaveBeenCalledWith('/api/projects/p1/client-profile', {
      profile: { otra_key: 'intacta', devops_publication_presets: ['nuevo'] },
    });
  });

  it('con flag OFF y profile ausente parte de {}', async () => {
    mocked.get.mockResolvedValue({});
    await saveProfileKey('p1', 'devops_environment_settings', { a: 1 }, false);
    expect(mocked.put).toHaveBeenCalledWith('/api/projects/p1/client-profile', {
      profile: { devops_environment_settings: { a: 1 } },
    });
  });

  it('propaga el error del PATCH (no lo traga)', async () => {
    mocked.patch.mockRejectedValue(new Error('400 Bad Request: key_not_patchable'));
    await expect(
      saveProfileKey('p1', 'devops_publication_settings', {}, true),
    ).rejects.toThrow('key_not_patchable');
  });

  it('encodea el nombre del proyecto en ambos rieles', async () => {
    await saveProfileKey('mi proyecto', 'devops_pipeline_drafts', [], true);
    expect(mocked.patch).toHaveBeenCalledWith(
      '/api/projects/mi%20proyecto/client-profile/keys/devops_pipeline_drafts',
      { value: [] },
    );

    mocked.get.mockResolvedValue({ profile: {} });
    await saveProfileKey('mi proyecto', 'devops_pipeline_drafts', [], false);
    expect(mocked.get).toHaveBeenCalledWith('/api/projects/mi%20proyecto/client-profile');
    expect(mocked.put).toHaveBeenCalledWith(
      '/api/projects/mi%20proyecto/client-profile',
      { profile: { devops_pipeline_drafts: [] } },
    );
  });
});
