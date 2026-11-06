// Test card provider: renders ordinary inputs and returns a fake token (`tok_mock_<last4>`).
// The typed number is validated locally and then discarded: it is never sent anywhere, just like with a real provider.
// Used for development and automated tests. Use 4242 4242 4242 4242 to succeed and 4000 0000 0000 0002 to be declined.

const luhn = (digits) => {
  let sum = 0;
  [...digits].reverse().forEach((d, i) => {
    let n = Number(d);
    if (i % 2) { n *= 2; if (n > 9) n -= 9; }
    sum += n;
  });
  return sum % 10 === 0;
};

export default {
  async mount(container) {
    container.innerHTML = `
      <div class="mock-card">
        <p class="mock-note">Test mode — no real card is charged. Try <b>4242 4242 4242 4242</b> (approved) or <b>4000 0000 0000 0002</b> (declined).</p>
        <label>Card number<input data-card="number" inputmode="numeric" autocomplete="cc-number" placeholder="4242 4242 4242 4242" maxlength="23"></label>
        <div class="row">
          <label>Expiry<input data-card="expiry" inputmode="numeric" autocomplete="cc-exp" placeholder="MM / YY" maxlength="7"></label>
          <label>CVC<input data-card="cvc" inputmode="numeric" autocomplete="cc-csc" placeholder="123" maxlength="4"></label>
        </div>
      </div>`;
    const field = (name) => container.querySelector(`[data-card=${name}]`);

    return {
      async tokenize() {
        const digits = field('number').value.replace(/\D/g, '');
        const expiry = field('expiry').value.replace(/\D/g, '');
        const cvc = field('cvc').value.replace(/\D/g, '');
        if (digits.length < 13 || digits.length > 19 || !luhn(digits)) throw new Error('Please enter a valid card number');
        const month = Number(expiry.slice(0, 2));
        const year = 2000 + Number(expiry.slice(2, 4));
        const now = new Date();
        if (expiry.length !== 4 || month < 1 || month > 12 || year < now.getFullYear() || (year === now.getFullYear() && month < now.getMonth() + 1)) {
          throw new Error('Please enter a valid expiry date');
        }
        if (cvc.length < 3) throw new Error('Please enter the security code');
        return `tok_mock_${digits.slice(-4)}`;
      },
      destroy() { container.innerHTML = ''; },
    };
  },
};
