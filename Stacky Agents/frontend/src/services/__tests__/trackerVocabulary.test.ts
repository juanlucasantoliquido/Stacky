import { describe, it, expect } from 'vitest';
import {
  pickExternalId,
  pickItemType,
  pickState,
  pickUrl,
} from '../trackerVocabulary';

describe('trackerVocabulary — Plan 218 F5', () => {
  it('pickExternalId prefiere external_id, cae a ado_id, null si no hay ninguno', () => {
    expect(pickExternalId({ external_id: 9, ado_id: 5 })).toBe(9);
    expect(pickExternalId({ ado_id: 5 })).toBe(5);
    expect(pickExternalId({})).toBeNull();
  });

  it('pickState prefiere tracker_state, cae a ado_state, null si no hay ninguno', () => {
    expect(pickState({ tracker_state: 'Doing', ado_state: 'Active' })).toBe('Doing');
    expect(pickState({ ado_state: 'Active' })).toBe('Active');
    expect(pickState({})).toBeNull();
  });

  it('pickUrl prefiere item_url, cae a ado_url, null si no hay ninguno', () => {
    expect(pickUrl({ item_url: 'https://gl/1', ado_url: 'https://ado/1' })).toBe('https://gl/1');
    expect(pickUrl({ ado_url: 'https://ado/1' })).toBe('https://ado/1');
    expect(pickUrl({})).toBeNull();
  });

  it('pickItemType prefiere item_type, cae a work_item_type, null si no hay ninguno', () => {
    expect(pickItemType({ item_type: 'issue', work_item_type: 'Task' })).toBe('issue');
    expect(pickItemType({ work_item_type: 'Task' })).toBe('Task');
    expect(pickItemType({})).toBeNull();
  });

  it('tolera null/undefined sin explotar', () => {
    expect(pickExternalId(null)).toBeNull();
    expect(pickState(undefined)).toBeNull();
    expect(pickUrl(null)).toBeNull();
    expect(pickItemType(undefined)).toBeNull();
  });
});
