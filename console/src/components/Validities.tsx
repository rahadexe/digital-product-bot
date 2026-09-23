'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Clock, Plus, Trash2 } from 'lucide-react';
import { api, type Category, type Product } from '@/lib/api';
import { EmptyRow, Modal, errorText, useConfirm, type Say } from './ui';
import { CustomSelect, type SelectOption } from './CustomSelect';

function parseDurationToDays(label: string): number {
  const m = label.match(/(\d+)/);
  let num = m ? parseInt(m[1], 10) : 999999;
  const lower = label.toLowerCase();
  if (lower.includes('month') || lower.includes('mash')) num *= 30;
  else if (lower.includes('year') || lower.includes('bochor')) num *= 365;
  return num;
}

export function Validities({ say }: { say: Say }) {
  const [presets, setPresets] = useState<string[]>([]);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [categories, setCategories] = useState<Category[] | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, confirmDialog] = useConfirm();

  const loadData = useCallback(async () => {
    try {
      const [sets, prods, cats] = await Promise.all([
        api.settings(),
        api.products(),
        api.categories(),
      ]);

      let loadedPresets: string[] = [];
      if (sets && typeof sets.validity_presets === 'string') {
        loadedPresets = sets.validity_presets
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
      }
      setPresets(loadedPresets);
      setProducts(prods);
      setCategories(cats);
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }, [say]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function savePresets(newPresets: string[]) {
    await api.updateSettings({ validity_presets: newPresets.join(', ') });
    setPresets(newPresets);
  }

  async function handleDelete(label: string) {
    const usingProducts = (products ?? []).filter(
      (p) => p.duration_label && p.duration_label.trim().toLowerCase() === label.toLowerCase()
    );

    if (usingProducts.length > 0) {
      say(
        `Cannot delete "${label}": used by ${usingProducts.length} product(s). Remove duration from those products first.`,
        'bad'
      );
      return;
    }

    if (!(await confirm(`Delete "${label}"?`, 'Remove this validity duration from presets?', 'Delete'))) {
      return;
    }

    const updated = presets.filter((p) => p.toLowerCase() !== label.toLowerCase());
    try {
      await savePresets(updated);
      say(`Deleted "${label}".`);
      await loadData();
    } catch (cause) {
      say(errorText(cause), 'bad');
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = newLabel.trim();
    if (!trimmed) return;

    if (presets.some((p) => p.toLowerCase() === trimmed.toLowerCase())) {
      say(`"${trimmed}" already exists.`, 'bad');
      return;
    }

    setBusy(true);
    try {
      const updated = [...presets, trimmed];
      await savePresets(updated);
      say(`Created "${trimmed}".`);
      setIsCreating(false);
      setNewLabel('');
      await loadData();
    } catch (cause) {
      say(errorText(cause), 'bad');
    } finally {
      setBusy(false);
    }
  }

  // Merge presets with any duration label in active products so nothing is hidden
  const allDurations = Array.from(
    new Set([
      ...presets,
      ...(products ?? [])
        .map((p) => p.duration_label?.trim())
        .filter((d): d is string => Boolean(d)),
    ])
  );

  const sortedDurations = [...allDurations].sort(
    (a, b) => parseDurationToDays(a) - parseDurationToDays(b)
  );

  const filteredDurations = sortedDurations.filter((val) => {
    if (search && !val.toLowerCase().includes(search.toLowerCase())) return false;
    if (selectedCategory !== 'all') {
      const catId = Number(selectedCategory);
      const hasProductInCat = (products ?? []).some(
        (p) =>
          p.duration_label &&
          p.duration_label.trim().toLowerCase() === val.toLowerCase() &&
          p.category_id === catId
      );
      if (!hasProductInCat) return false;
    }
    return true;
  });

  const categoryOptions: SelectOption[] = useMemo(() => {
    const list: SelectOption[] = [{ value: 'all', label: 'All Categories' }];
    for (const c of categories ?? []) {
      const count = (products ?? []).filter(
        (p) => p.category_id === c.id && p.duration_label && p.duration_label.trim()
      ).length;
      list.push({
        value: String(c.id),
        label: c.name,
        badge: count > 0 ? count : undefined,
      });
    }
    return list;
  }, [categories, products]);

  return (
    <>
      {confirmDialog}

      {/* Main Table Section */}
      <section className="panel">
        <header>
          <div className="filters">
            <input
              type="search"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <CustomSelect
              value={selectedCategory}
              onChange={setSelectedCategory}
              options={categoryOptions}
              width={260}
            />
          </div>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setNewLabel('');
              setIsCreating(true);
            }}
          >
            <Plus size={16} style={{ marginRight: 4 }} /> New Validity
          </button>
        </header>

        <div className="scroll" style={{ minHeight: '220px' }}>
          <table className="validities-table">
            <thead>
              <tr>
                <th>Duration</th>
                <th style={{ textAlign: 'center' }}>Linked Products</th>
                <th className="right" aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {filteredDurations.map((val) => {
                const matchingProducts = (products ?? []).filter(
                  (p) => p.duration_label && p.duration_label.trim().toLowerCase() === val.toLowerCase()
                );
                const isUsed = matchingProducts.length > 0;

                return (
                  <tr key={val}>
                    <td className="name">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Clock size={16} color="var(--accent)" />
                        <strong>{val}</strong>
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {matchingProducts.length > 0 ? (
                        <span
                          className="pill good"
                          style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 600 }}
                        >
                          {matchingProducts.length} product{matchingProducts.length > 1 ? 's' : ''}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>0</span>
                      )}
                    </td>
                    <td>
                      <div className="row-actions">
                        {isUsed ? (
                          <button
                            type="button"
                            className="mini danger"
                            disabled
                            title={`Cannot delete: used by ${matchingProducts.length} product(s).`}
                            style={{ opacity: 0.4, cursor: 'not-allowed' }}
                          >
                            <Trash2 size={13} style={{ marginRight: 3 }} /> Delete
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="mini danger"
                            onClick={() => handleDelete(val)}
                          >
                            <Trash2 size={13} style={{ marginRight: 3 }} /> Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}

              {filteredDurations.length === 0 ? (
                <EmptyRow columns={4}>
                  {search ? 'Nothing matches.' : 'No validities found.'}
                </EmptyRow>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Simple Create Modal */}
      {isCreating ? (
        <Modal
          title="New Validity"
          onClose={() => setIsCreating(false)}
          onSubmit={handleCreate}
          footer={
            <>
              <button
                type="button"
                className="btn ghost"
                onClick={() => setIsCreating(false)}
              >
                Cancel
              </button>
              <button type="submit" className="btn" disabled={busy}>
                Create
              </button>
            </>
          }
        >
          <label className="field">
            <span>Duration Label</span>
            <input
              type="text"
              required
              placeholder="e.g. 7 Days, 1 Month"
              value={newLabel}
              autoFocus
              onChange={(e) => setNewLabel(e.target.value)}
            />
          </label>
        </Modal>
      ) : null}
    </>
  );
}
