// State shared between views.
export const state = {
  tab: 'pending',
  rangeDays: 30, // used by the Revenue and Visits tabs
  stores: [], // every connected store: { id, name, active, logo_url, ... }
  store: null, // selected store id; null = all stores
};
