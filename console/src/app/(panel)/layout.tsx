import type { Metadata, Viewport } from 'next';
import '@fontsource-variable/manrope';
import './console.css';
import './workspace.css';
import './records.css';
import './studio.css';
import './mobile-lists.css';

// Bundled with the console: no external font request at build time or runtime.

export const metadata: Metadata = {
  title: 'Console',
  description: 'Operator console.',
  robots: { index: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#f5f7fb',
  viewportFit: 'cover',
};

export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return <div className="console-root">{children}</div>;
}
