// Generic "embedded card form" provider.
//
// The client hosts the card form (built with whatever processor they use) and we show it in an iframe on our page.
// The card number is typed into THEIR page and goes straight to their processor; we only ever receive a token.
// Messages are plain postMessage — see docs/embedded-card-form.md for the contract the client's page implements:
//
//   form -> checkout   { source: 'checkout-card-form', type: 'ready' }
//   form -> checkout   { source: 'checkout-card-form', type: 'height', height: 240 }              (optional)
//   checkout -> form   { source: 'checkout', type: 'tokenize', id }
//   form -> checkout   { source: 'checkout-card-form', type: 'token', id, token }
//   form -> checkout   { source: 'checkout-card-form', type: 'error', id, message }

const FROM_FORM = 'checkout-card-form';
const FROM_US = 'checkout';
const READY_TIMEOUT_MS = 15000;
const TOKEN_TIMEOUT_MS = 60000;

export default {
  async mount(container, { formUrl }) {
    const origin = new URL(formUrl, location.href).origin;
    if (origin === location.origin) throw new Error('The card form must be hosted on a different origin');

    const frame = document.createElement('iframe');
    frame.title = 'Card details';
    frame.className = 'card-frame';
    frame.setAttribute('allow', 'payment');
    // Their page may run scripts and talk to their processor; it may not navigate our page or open our DOM.
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox');
    frame.src = formUrl;

    let pending = null; // { id, resolve, reject, timer }
    let settleReady;
    const ready = new Promise((resolve) => { settleReady = resolve; });

    const onMessage = (event) => {
      // Only our own iframe, and only from the origin we configured.
      if (event.source !== frame.contentWindow || event.origin !== origin) return;
      const msg = event.data;
      if (!msg || msg.source !== FROM_FORM) return;
      if (msg.type === 'ready') settleReady(true);
      else if (msg.type === 'height') {
        const h = Math.round(Number(msg.height));
        if (h >= 80 && h <= 900) frame.style.height = `${h}px`;
      } else if (pending && msg.id === pending.id && (msg.type === 'token' || msg.type === 'error')) {
        const { resolve, reject, timer } = pending;
        pending = null;
        clearTimeout(timer);
        if (msg.type === 'token' && typeof msg.token === 'string' && msg.token && msg.token.length <= 500) resolve(msg.token);
        else reject(new Error(typeof msg.message === 'string' && msg.message ? msg.message.slice(0, 200) : 'Please check your card details'));
      }
    };
    window.addEventListener('message', onMessage);
    container.appendChild(frame);

    const loaded = await Promise.race([ready, new Promise((r) => setTimeout(() => r(false), READY_TIMEOUT_MS))]);
    if (!loaded) {
      window.removeEventListener('message', onMessage);
      frame.remove();
      throw new Error('The card form did not load');
    }

    return {
      tokenize() {
        if (pending) return Promise.reject(new Error('Please wait…'));
        return new Promise((resolve, reject) => {
          const id = crypto.randomUUID();
          const timer = setTimeout(() => { pending = null; reject(new Error('The card form did not respond. Please try again.')); }, TOKEN_TIMEOUT_MS);
          pending = { id, resolve, reject, timer };
          frame.contentWindow.postMessage({ source: FROM_US, type: 'tokenize', id }, origin);
        });
      },
      destroy() {
        window.removeEventListener('message', onMessage);
        frame.remove();
      },
    };
  },
};
