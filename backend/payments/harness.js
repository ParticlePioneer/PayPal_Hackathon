(async () => {
  const status = document.getElementById('status');
  async function post(url, data) {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Checkout unavailable');
    return result;
  }
  try {
    const session = await post('/api/test-checkout/session', {});
    const saved = await fetch('/api/payments/quotes/' + encodeURIComponent(session.quote_id));
    if (!saved.ok) throw new Error('Could not recover payment status');
    const state = await saved.json();
    const capture = state.operations.find((operation) => operation.operation_type === 'capture');
    const authorization = state.operations.find((operation) => operation.operation_type === 'authorize');
    const uncertain = state.operations.find((operation) => operation.status === 'pending' || operation.status === 'unknown');
    if (capture && capture.status === 'succeeded') {
      status.textContent = 'Captured. Capture ID: ' + capture.paypal_capture_id;
      return;
    }
    if (uncertain) {
      status.textContent = 'Payment outcome pending. Do not start another checkout.';
      return;
    }
    if (authorization && authorization.status === 'succeeded') {
      status.textContent = 'Authorized. Authorization ID: ' + authorization.paypal_authorization_id;
      return;
    }
    const script = document.createElement('script');
    const params = new URLSearchParams({ 'client-id': session.client_id, currency: 'USD', intent: 'authorize' });
    script.src = 'https://www.paypal.com/sdk/js?' + params.toString();
    await new Promise((resolve, reject) => { script.onload = resolve; script.onerror = reject; document.head.append(script); });
    status.textContent = 'Ready for Sandbox buyer approval.';
    await window.paypal.Buttons({
      createOrder: async () => (await post('/api/payments/orders', { quote_id: session.quote_id })).id,
      onApprove: async (data) => {
        status.textContent = 'Authorizing...';
        try {
          const result = await post('/api/payments/orders/' + encodeURIComponent(data.orderID) + '/authorize', {});
          status.textContent = 'Authorized. Authorization ID: ' + result.authorization_id;
        } catch (error) { status.textContent = error.message; }
      },
      onCancel: () => { status.textContent = 'Buyer cancelled. No authorization was requested.'; },
      onError: () => { status.textContent = 'Checkout could not continue. Check status before retrying.'; }
    }).render('#paypal-button');
  } catch (error) { status.textContent = 'Checkout setup failed. ' + (error.message || ''); }
})();
