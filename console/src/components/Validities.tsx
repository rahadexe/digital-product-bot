'use client';

import { useCallback, useEffect, useState } from 'react';
import { Clock, Plus, Trash2, Edit3 } from 'lucide-react';
import { api, type Category, type Product } from '@/lib/api';
import { EmptyRow, FlagRow, Modal, errorText, useConfirm, type Say } from './ui';

interface EditDraft {
  mode: 'new' | 'edit';
  originalLabel?: string;
  label: string;
  updateProducts: boolean;
}

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
  const [draft, setDraft] = useState<EditDraft | null>(null);
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
      if (sets && sets.validity_presets) {
        loadedPresets = sets.validity_presets
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
      } else {
        loadedPresets = ['3 Days', '7 Days', '14 Days', '30 Days', '90 Days', '1 Year'];
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
        `Cannot delete "${label}": used by ${usingProducts.length} product(s). Please change or clear the duration on those products first.`,
        'bad'
      );
      return;
    }

    if (!(await confirm(`Delete "${label}"?`, 'Remove this validity duration?', 'Delete'))) {
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

  async function handleModalSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const trimmed = draft.label.trim();
    if (!trimmed) return;

    setBusy(true);
    try {
      if (draft.mode === 'new') {
        if (presets.some((p) => p.toLowerCase() === trimmed.toLowerCase())) {
          say(`"${trimmed}" already exists.`, 'bad');
          setBusy(false);
          return;
        }
        const updated = [...presets, trimmed];
        await savePresets(updated);
        say(`Created "${trimmed}".`);
      } else if (draft.mode === 'edit' && draft.originalLabel) {
        const oldLabel = draft.originalLabel;
        const updated = presets.map((p) =>
          p.toLowerCase() === oldLabel.toLowerCase() ? trimmed : p
        );
        await savePresets(updated);

        if (draft.updateProducts) {
          const matchingProds = (products ?? []).filter(
            (p) => p.duration_label && p.duration_label.trim().toLowerCase() === oldLabel.toLowerCase()
          );
          for (const prod of matchingProds) {
            await api.updateProduct(prod.id, { duration_label: trimmed });
          }
        }
        say(`Updated "${trimmed}".`);
      }

      setDraft(null);
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

  return (
    <>
      {confirmDialog}

      {/* Main Table Section */}
      <section className="panel">
        <header>
          <div className="filters">
            <input
              type="search"
              placeholder="Search validities..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              <option value="all">All Categories</option>
              {(categories ?? []).map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn"
            onClick={() =>
              setDraft({
                mode: 'new',
                label: '',
                updateProducts: false,
              })
            }
          >
            <Plus size={16} style={{ marginRight: 4 }} /> New Validity
          </button>
        </header>

        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Duration</th>
                <th>Linked Products</th>
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
                    <td>
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
                        <button
                          type="button"
                          className="mini"
                          onClick={() =>
                            setDraft({
                              mode: 'edit',
                              originalLabel: val,
                              label: val,
                              updateProducts: true,
                            })
                          }
                        >
                          <Edit3 size={13} style={{ marginRight: 3 }} /> Edit
                        </button>
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

      {/* Create / Edit Modal */}
      {draft ? (
        <Modal
          title={draft.mode === 'new' ? 'New Validity' : `Edit "${draft.originalLabel}"`}
          onClose={() => setDraft(null)}
          onSubmit={handleModalSubmit}
          footer={
            <>
              <button
                type="button"
                className="btn ghost"
                onClick={() => setDraft(null)}
              >
                Cancel
              </button>
              <button type="submit" className="btn" disabled={busy}>
                {draft.mode === 'new' ? 'Create' : 'Save'}
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
              value={draft.label}
              autoFocus
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            />
          </label>

          {draft.mode === 'edit' && (
            <div style={{ marginTop: '10px' }}>
              <FlagRow
                label="Update linked products"
                on={draft.updateProducts}
                onChange={(on) => setDraft({ ...draft, updateProducts: on })}
              />
            </div>
          )}
        </Modal>
      ) : null}
    </>
  );
}
