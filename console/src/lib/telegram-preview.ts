/** Escape text before restoring the small HTML subset supported by the preview. */
export function escapeTelegramHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function renderSafeTelegramHtml(raw: string): string {
  if (!raw.trim()) return '<span style="color: var(--muted); font-style: italic;">Message preview...</span>';
  return escapeTelegramHtml(raw)
    .replace(/&lt;(b|strong|i|em|code|pre)&gt;([\s\S]*?)&lt;\/\1&gt;/gi, '<$1>$2</$1>')
    .replace(/&lt;a href=&quot;([\s\S]*?)&quot;&gt;([\s\S]*?)&lt;\/a&gt;/gi, (_match, href: string, label: string) => {
      // No javascript/data URLs, relative destinations or attributes from the source.
      // href is still escaped, including quotes, when placed in the HTML attribute.
      if (!/^(https?:\/\/|tg:\/\/)/i.test(href)) return label;
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    })
    .replace(/\n/g, '<br/>')
    // Preserve Telegram's encoded text/query strings without treating them as markup.
    .replace(/&amp;(amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);/gi, '&$1;');
}
