// State shared between views.
export const state = {
  tab: 'pending',
  rangeDays: 30, // used by the Revenue and Visits tabs
  stores: [], // every connected store: { id, name, active, logo_url, ... }
  store: null, // store filter for orders / revenue / visits; null = all stores
  settingsStore: null, // which store the Settings page edits (independent of the filter); null = filter's store or the first
};
