import { useEffect, useRef } from "react";

type Props = { quoteId: string; onStatusChange: (status: string) => void };
type PayPalButtons = { render: (element: HTMLElement) => Promise<void>; close?: () => void };
type PayPalSdk = { Buttons: (options: {
  createOrder: () => Promise<string>;
  onApprove: (data: { orderID: string }) => Promise<void>;
  onCancel: () => void;
  onError: () => void;
}) => PayPalButtons };
declare global { interface Window { paypal?: PayPalSdk } }

async function post(path: string, body: object) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "Checkout unavailable");
  return result;
}

export default function CheckoutButton({ quoteId, onStatusChange }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onStatusChange);
  callback.current = onStatusChange;

  useEffect(() => {
    if (!quoteId || !container.current) return;
    let active = true;
    let buttons: PayPalButtons | undefined;
    const element = container.current;
    const clientId = import.meta.env.VITE_PAYPAL_CLIENT_ID as string | undefined;
    if (!clientId) { callback.current("checkout_unavailable"); return; }
    async function render() {
      if (!window.paypal) {
        const script = document.createElement("script");
        script.src = "https://www.paypal.com/sdk/js?" + new URLSearchParams({ "client-id": clientId!, currency: "USD", intent: "authorize" });
        await new Promise<void>((resolve, reject) => { script.onload = () => resolve(); script.onerror = () => reject(); document.head.appendChild(script); });
      }
      if (!active || !window.paypal) return;
      buttons = window.paypal.Buttons({
        createOrder: async () => (await post("/api/payments/orders", { quote_id: quoteId })).id,
        onApprove: async ({ orderID }) => {
          callback.current("pending");
          try { await post(`/api/payments/orders/${encodeURIComponent(orderID)}/authorize`, {}); callback.current("authorized"); }
          catch { callback.current("pending"); }
        },
        onCancel: () => callback.current("cancelled"),
        onError: () => callback.current("error"),
      });
      await buttons.render(element);
    }
    render().catch(() => { if (active) callback.current("error"); });
    return () => { active = false; buttons?.close?.(); };
  }, [quoteId]);

  return quoteId ? <div ref={container} /> : <button disabled>Checkout unavailable</button>;
}
