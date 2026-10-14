import type { Metadata, Viewport } from 'next';
import { Inter, Manrope } from 'next/font/google';
import './console.css';
import './workspace.css';
import './records.css';

// The Mini App's typeface for reading, Manrope for headings and figures. next/font serves both from this site.
const display = Manrope({ subsets: ['latin'], weight: ['600', '700', '800'], variable: '--font-display', display: 'swap' });
const text = Inter({ subsets: ['latin'], variable: '--font-text', display: 'swap' });

export const metadata: Metadata = {
  title: 'Console',
  description: 'Operator console.',
  robots: { index: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#f7f8fa',
};

export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return <div className={`console-root ${display.variable} ${text.variable}`}>{children}</div>;
}
