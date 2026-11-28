// Optional session-replay tagging on the checkout page: Microsoft Clarity, and optionally PostHog.
//
// Both are entirely config-driven (see app.schemas.settings: clarityProjectId / posthogProjectKey / posthogHost,
// shared across every store since this whole service is one domain). A blank project id/key means that tool is
// simply never loaded -- nothing is sent anywhere, no network request is even made. Neither of these ids is a
// secret: a Clarity project id and a PostHog *project* key are both meant to ship in client-side JS.
//
// Nothing in here may throw past its own call: a tracking snippet failing must never break the checkout page.

function loadClarity(projectId) {
  // Microsoft's standard loader snippet, parameterized (the project id is config, not a build-time constant).
  (function (c, l, a, r, i, t, y) {
    c[a] = c[a] || function () { (c[a].q = c[a].q || []).push(arguments); };
    t = l.createElement(r); t.async = 1; t.src = 'https://www.clarity.ms/tag/' + i;
    y = l.getElementsByTagName(r)[0]; y.parentNode.insertBefore(t, y);
  })(window, document, 'clarity', 'script', projectId);
}

function tagClarity(session) {
  window.clarity('set', 'store_id', String(session.store_id));
  window.clarity('set', 'checkout_session', session.id);
  window.clarity('set', 'utm_campaign', session.utm_campaign || '(none)');
  window.clarity('set', 'has_gclid', session.has_click_id ? 'yes' : 'no');
  // The same id Deep2K/junard uses, so a store-side recording and this checkout recording can be matched --
  // only when the store's checkout-redirect.js actually captured one (not every session has a Deep2K context).
  if (session.deep2k_anonymous_id) window.clarity('identify', session.deep2k_anonymous_id);
}

// PostHog's array.js bundle defines window.posthog itself once loaded; calls made before that would be lost, so
// (unlike Clarity's own queue-stub) init/identify/register are simply deferred to the script's onload instead of
// hand-replicating PostHog's official async stub, which is easy to get subtly wrong from memory.
function loadPostHog(projectKey, host, session) {
  var apiHost = host || 'https://us.i.posthog.com';
  var script = document.createElement('script');
  script.async = true;
  script.src = apiHost + '/static/array.js';
  script.onload = function () {
    if (!window.posthog || !window.posthog.init) return;
    window.posthog.init(projectKey, { api_host: apiHost });
    window.posthog.register({ utm_campaign: session.utm_campaign || '(none)', has_gclid: session.has_click_id });
    if (session.deep2k_anonymous_id) window.posthog.identify(session.deep2k_anonymous_id);
  };
  document.head.appendChild(script);
}

/** Call once, right after the session is first loaded. Safe to call even when neither tool is configured. */
export function initTracking(session) {
  try {
    var clarityId = session?.branding?.clarity_project_id;
    if (clarityId) {
      loadClarity(clarityId);
      tagClarity(session);
    }
    var posthogKey = session?.branding?.posthog_project_key;
    if (posthogKey) {
      loadPostHog(posthogKey, session.branding.posthog_host, session);
    }
  } catch {
    // A tracking snippet must never be able to break the checkout page.
  }
}
