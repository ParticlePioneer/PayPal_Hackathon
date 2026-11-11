// Member B owns the PayPal callbacks and final integration of this component.
type CheckoutButtonProps = {
  quoteId: string;
  onStatusChange: (status: string) => void;
};

export default function CheckoutButton(_props: CheckoutButtonProps) {
  return <button disabled>Checkout unavailable</button>;
}
