'use client';

import { useEffect, useState } from 'react';
import { api } from './api';

// The store's currency symbol comes from Settings, so the console shows money the way customers see it.
let symbolRequest: Promise<string> | null = null;

function loadCurrencySymbol(): Promise<string> {
  if (!symbolRequest) {
    symbolRequest = api
      .settings()
      .then((settings) => settings.currency_symbol || '৳')
      .catch(() => {
        symbolRequest = null;
        return '৳';
      });
  }
  return symbolRequest;
}

/** Call after saving settings so screens pick up a changed symbol. */
export function resetCurrencySymbol() {
  symbolRequest = null;
}

export function useMoney() {
  const [symbol, setSymbol] = useState('৳');
  useEffect(() => {
    let active = true;
    loadCurrencySymbol().then((value) => {
      if (active) setSymbol(value);
    });
    return () => {
      active = false;
    };
  }, []);
  return (value: number) => `${symbol}${Number(value || 0).toFixed(2)}`;
}
