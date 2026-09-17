import type { Metadata, Viewport } from 'next';
import { Inter, Manrope } from 'next/font/google';
import './console.css';

// The Mini App's typeface for reading, Manrope for headings and figures. next/font serves both from this site.
const display = Manrope({ subsets: ['latin'], weight: ['600', '700', '800'], variable: '--font-display', display: 'swap' });
const text = Inter({ subsets: ['latin'], variable: '--font-text', display: 'swap' });

export const metadata: Metadata = {
  title: 'SubsMarket Console',
  description: 'Operator console for SubsMarket.',
  robots: { index: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#f4f5f2',
};

export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return <div className={`console-root ${display.variable} ${text.variable}`}>{children}</div>;
}
