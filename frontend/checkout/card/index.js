// Card-field providers.
//
// A provider shows the *processor's own* card fields inside the checkout page and turns what the customer typed into
// a single-use token. The card number is never read by our code and never sent to our server — only the token is.
//
// A provider module default-exports:
//   {
//     async mount(container, { publicKey, formUrl }) ->{ tokenize(): Promise<string>, destroy(): void }
//   }
// `tokenize()` throws an Error with a customer-friendly message when the card details are incomplete or invalid.
//
// To support a processor, add a file here that wraps its hosted-fields SDK (Stripe Elements, Authorize.net Accept.js,
// NMI Collect.js, ...) and register it below. Which one is used is chosen in Admin → Settings → Card payments.

const PROVIDERS = {
  embed: () => import('/static/checkout/card/embed.js'), // generic: the client hosts the card form, we show it in an iframe
  mock: () => import('/static/checkout/card/mock.js'), // test provider: fake fields, no real card ever charged
};

/** Returns the provider module for `name`, or null if this build doesn't include it. */
export async function loadProvider(name) {
  const load = PROVIDERS[name];
  if (!load) return null;
  return (await load()).default;
}
