import './base.css';

// Two products share this build: the operator console (/panel/) and the Mini App (/app/). Each brings its own
// layout and stylesheet, so neither can restyle the other; only the reset below is common.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
