// Replaces Next's default 404 page, which carries inline style attributes the policy forbids.
export default function NotFound() {
  return (
    <main id="main">
      <h1>Page not found</h1>
      <p className="muted">There is nothing at this address. <a href="/">Back to the start</a>.</p>
    </main>
  );
}
