(() => {
  'use strict';

  const PAGE_SIZE = 18;
  const STORAGE_KEY = 'secureshelf.saved.v1';
  const typeLabels = { tool: 'টুল', reference: 'রেফারেন্স', service: 'অনলাইন সেবা' };
  const state = {
    records: [],
    query: '',
    category: 'all',
    type: 'all',
    tag: '',
    savedOnly: false,
    sort: 'source',
    visible: PAGE_SIZE,
    saved: new Set(),
    activeRecord: null,
    toastTimer: null,
  };

  const byId = (id) => document.getElementById(id);
  const ui = {
    grid: byId('resource-grid'),
    search: byId('search-input'),
    type: byId('type-filter'),
    sort: byId('sort-filter'),
    categoryList: byId('category-list'),
    tagList: byId('tag-filter-list'),
    resultCount: byId('result-count'),
    empty: byId('empty-state'),
    loadMore: byId('load-more'),
    activeFilters: byId('active-filters'),
    savedToggle: byId('saved-toggle'),
    savedCount: byId('saved-count'),
    dialog: byId('resource-dialog'),
    toast: byId('toast'),
  };

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function safeExternalUrl(value) {
    if (typeof value !== 'string' || !value.trim()) return '';
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) return '';
      return url.href;
    } catch {
      return '';
    }
  }

  function loadSaved() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      if (Array.isArray(parsed)) state.saved = new Set(parsed.filter((id) => typeof id === 'string'));
    } catch {
      state.saved = new Set();
    }
  }

  function persistSaved() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.saved]));
    } catch {
      showToast('এই browser-এ সংরক্ষণ করা যায়নি।');
    }
    ui.savedCount.textContent = String(state.saved.size);
  }

  function showToast(message) {
    ui.toast.textContent = message;
    ui.toast.classList.add('is-visible');
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => ui.toast.classList.remove('is-visible'), 2200);
  }

  function categoryCounts() {
    const counts = new Map();
    for (const record of state.records) counts.set(record.category, (counts.get(record.category) || 0) + 1);
    return counts;
  }

  function renderCategories() {
    const counts = categoryCounts();
    ui.categoryList.replaceChildren();
    const allButton = node('button', 'category-button');
    allButton.type = 'button';
    allButton.dataset.action = 'category';
    allButton.dataset.category = 'all';
    allButton.setAttribute('aria-pressed', String(state.category === 'all'));
    allButton.append(node('span', '', 'সব রিসোর্স'));
    allButton.append(node('span', 'category-total', String(state.records.length)));
    ui.categoryList.append(allButton);

    for (const [category, count] of counts) {
      const button = node('button', 'category-button');
      button.type = 'button';
      button.dataset.action = 'category';
      button.dataset.category = category;
      button.setAttribute('aria-pressed', String(state.category === category));
      button.append(node('span', '', category));
      button.append(node('span', 'category-total', String(count)));
      ui.categoryList.append(button);
    }
    byId('category-count').textContent = String(counts.size);
    byId('stat-categories').textContent = String(counts.size).padStart(2, '0');
  }

  function renderPopularTags() {
    const counts = new Map();
    for (const record of state.records) {
      for (const tag of record.tags) counts.set(tag, (counts.get(tag) || 0) + 1);
    }
    const popular = [...counts.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 14);
    ui.tagList.replaceChildren();
    for (const [tag] of popular) {
      const button = node('button', 'tag-filter-button', tag);
      button.type = 'button';
      button.dataset.action = 'tag';
      button.dataset.tag = tag;
      button.setAttribute('aria-pressed', String(state.tag === tag));
      ui.tagList.append(button);
    }
  }

  function matches(record) {
    if (state.category !== 'all' && record.category !== state.category) return false;
    if (state.type !== 'all' && record.type !== state.type) return false;
    if (state.tag && !record.tags.includes(state.tag)) return false;
    if (state.savedOnly && !state.saved.has(record.id)) return false;
    if (!state.query) return true;
    const haystack = [record.name, record.category, record.description, ...record.tags].join(' ').toLocaleLowerCase();
    return haystack.includes(state.query.toLocaleLowerCase());
  }

  function filteredRecords() {
    const results = state.records.filter(matches);
    if (state.sort === 'name') {
      results.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
    }
    return results;
  }

  function updateActiveFilters() {
    ui.activeFilters.replaceChildren();
    const filters = [];
    if (state.category !== 'all') filters.push(['বিভাগ', state.category, 'category']);
    if (state.type !== 'all') filters.push(['ধরন', typeLabels[state.type], 'type']);
    if (state.tag) filters.push(['ট্যাগ', state.tag, 'tag']);
    if (state.savedOnly) filters.push(['দেখুন', 'শুধু সংরক্ষিত', 'saved']);
    if (state.query) filters.push(['খোঁজ', `“${state.query}”`, 'query']);
    for (const [label, value, key] of filters) {
      const chip = node('span', 'active-chip');
      chip.append(node('span', '', `${label}: ${value}`));
      const remove = node('button', '', '×');
      remove.type = 'button';
      remove.setAttribute('aria-label', `${label} ফিল্টার সরান`);
      remove.dataset.action = 'remove-filter';
      remove.dataset.filter = key;
      chip.append(remove);
      ui.activeFilters.append(chip);
    }
  }

  function createCard(record) {
    const card = node('article', 'resource-card');
    const top = node('div', 'card-top');
    top.append(node('span', 'card-category', record.category));
    const badge = node('span', 'type-badge', typeLabels[record.type] || 'রিসোর্স');
    badge.dataset.type = record.type;
    top.append(badge);

    const title = node('button', 'card-title-button', record.name);
    title.type = 'button';
    title.dataset.action = 'details';
    title.dataset.id = record.id;
    title.setAttribute('aria-label', `${record.name} — বিস্তারিত দেখুন`);

    const description = node('p', 'card-description', record.description);
    const tags = node('div', 'card-tags');
    for (const tag of record.tags.slice(0, 4)) {
      const tagButton = node('button', 'resource-tag', tag);
      tagButton.type = 'button';
      tagButton.dataset.action = 'tag';
      tagButton.dataset.tag = tag;
      tagButton.setAttribute('aria-label', `${tag} ট্যাগ দিয়ে filter করুন`);
      tags.append(tagButton);
    }

    const footer = node('div', 'card-footer');
    const officialUrl = safeExternalUrl(record.sourceUrl);
    footer.append(node('span', `source-status${officialUrl ? ' has-source' : ''}`, officialUrl ? new URL(officialUrl).hostname : 'উৎসের link দেওয়া নেই'));
    const actions = node('div', 'card-actions');
    const detailButton = node('button', 'card-detail', 'বিস্তারিত ↗');
    detailButton.type = 'button';
    detailButton.dataset.action = 'details';
    detailButton.dataset.id = record.id;
    const saveButton = node('button', 'card-save', state.saved.has(record.id) ? '★' : '☆');
    saveButton.type = 'button';
    saveButton.dataset.action = 'save';
    saveButton.dataset.id = record.id;
    saveButton.setAttribute('aria-pressed', String(state.saved.has(record.id)));
    saveButton.setAttribute('aria-label', state.saved.has(record.id) ? `${record.name} সংরক্ষণ থেকে সরান` : `${record.name} সংরক্ষণ করুন`);
    actions.append(detailButton, saveButton);
    footer.append(actions);
    card.append(top, title, description, tags, footer);
    return card;
  }

  function render() {
    const results = filteredRecords();
    const visible = results.slice(0, state.visible);
    ui.grid.replaceChildren(...visible.map(createCard));
    ui.grid.setAttribute('aria-busy', 'false');
    ui.empty.hidden = results.length !== 0;
    ui.grid.hidden = results.length === 0;
    ui.loadMore.hidden = results.length <= visible.length;
    ui.resultCount.innerHTML = '';
    const strong = node('strong', '', String(results.length));
    ui.resultCount.append(strong, document.createTextNode(` / ${state.records.length} রিসোর্স`));
    updateActiveFilters();
    renderCategories();
    renderPopularTags();
    ui.savedToggle.setAttribute('aria-pressed', String(state.savedOnly));
    ui.savedCount.textContent = String(state.saved.size);
  }

  function toggleSaved(id) {
    if (!id) return;
    if (state.saved.has(id)) {
      state.saved.delete(id);
      showToast('সংরক্ষিত তালিকা থেকে সরানো হয়েছে।');
    } else {
      state.saved.add(id);
      showToast('এই browser-এ সংরক্ষণ করা হয়েছে।');
    }
    persistSaved();
    render();
    if (state.activeRecord && state.activeRecord.id === id) updateDialogSave();
  }

  function updateDialogSave() {
    const record = state.activeRecord;
    if (!record) return;
    const isSaved = state.saved.has(record.id);
    byId('dialog-save').textContent = isSaved ? '★ সংরক্ষিত থেকে সরান' : '☆ এই রিসোর্স সংরক্ষণ করুন';
    byId('dialog-save').setAttribute('aria-pressed', String(isSaved));
  }

  function openDetails(id) {
    const record = state.records.find((item) => item.id === id);
    if (!record) return;
    state.activeRecord = record;
    byId('dialog-category').textContent = record.category;
    byId('dialog-title').textContent = record.name;
    byId('dialog-description').textContent = record.description;
    byId('dialog-type').textContent = typeLabels[record.type] || 'রিসোর্স';
    byId('dialog-platform').textContent = record.platform || 'উৎসে উল্লেখ নেই';
    const officialUrl = safeExternalUrl(record.sourceUrl);
    byId('dialog-source-status').textContent = officialUrl ? new URL(officialUrl).hostname : 'এই entry-তে official project link দেওয়া নেই';
    const sourceLink = byId('dialog-source-link');
    sourceLink.hidden = !officialUrl;
    sourceLink.href = officialUrl || '#';
    const archiveLink = byId('dialog-archive-link');
    archiveLink.href = safeExternalUrl(record.archiveUrl) || 'https://github.com/HumayunShariarHimu/HackingTools';
    const copyButton = byId('dialog-copy');
    copyButton.hidden = !officialUrl;
    copyButton.dataset.url = officialUrl;
    const tags = byId('dialog-tags');
    tags.replaceChildren();
    for (const tag of record.tags) tags.append(node('span', 'resource-tag', tag));
    updateDialogSave();
    if (!ui.dialog.open) ui.dialog.showModal();
    byId('dialog-close')?.focus();
    ui.dialog.querySelector('[data-action="close-dialog"]').focus();
  }

  function clearFilters() {
    state.query = '';
    state.category = 'all';
    state.type = 'all';
    state.tag = '';
    state.savedOnly = false;
    state.sort = 'source';
    state.visible = PAGE_SIZE;
    ui.search.value = '';
    ui.type.value = 'all';
    ui.sort.value = 'source';
    render();
  }

  function removeFilter(filter) {
    if (filter === 'category') state.category = 'all';
    if (filter === 'type') { state.type = 'all'; ui.type.value = 'all'; }
    if (filter === 'tag') state.tag = '';
    if (filter === 'saved') state.savedOnly = false;
    if (filter === 'query') { state.query = ''; ui.search.value = ''; }
    state.visible = PAGE_SIZE;
    render();
  }

  document.addEventListener('click', async (event) => {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    const { action } = target.dataset;
    if (action === 'category') {
      state.category = target.dataset.category || 'all';
      state.visible = PAGE_SIZE;
      render();
    } else if (action === 'tag') {
      const tag = target.dataset.tag || '';
      state.tag = state.tag === tag ? '' : tag;
      state.visible = PAGE_SIZE;
      render();
    } else if (action === 'details') {
      openDetails(target.dataset.id);
    } else if (action === 'save') {
      toggleSaved(target.dataset.id);
    } else if (action === 'close-dialog') {
      ui.dialog.close();
    } else if (action === 'remove-filter') {
      removeFilter(target.dataset.filter);
    } else if (action === 'copy-source') {
      // Reserved for a future explicit copy control; no page action invokes commands.
    } else if (action === 'noop') {
      event.preventDefault();
    }
  });

  ui.search.addEventListener('input', () => {
    state.query = ui.search.value.trim();
    state.visible = PAGE_SIZE;
    render();
  });
  ui.type.addEventListener('change', () => {
    state.type = ui.type.value;
    state.visible = PAGE_SIZE;
    render();
  });
  ui.sort.addEventListener('change', () => {
    state.sort = ui.sort.value;
    state.visible = PAGE_SIZE;
    render();
  });
  ui.savedToggle.addEventListener('click', () => {
    state.savedOnly = !state.savedOnly;
    state.visible = PAGE_SIZE;
    render();
  });
  byId('clear-filters').addEventListener('click', clearFilters);
  byId('empty-clear').addEventListener('click', clearFilters);
  ui.loadMore.addEventListener('click', () => {
    state.visible += PAGE_SIZE;
    render();
  });
  byId('dialog-save').addEventListener('click', () => {
    if (state.activeRecord) toggleSaved(state.activeRecord.id);
  });
  byId('dialog-copy').addEventListener('click', async (event) => {
    const url = safeExternalUrl(event.currentTarget.dataset.url);
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      showToast('Source URL কপি করা হয়েছে।');
    } catch {
      showToast('কপি করা যায়নি—source link খুলে URL কপি করুন।');
    }
  });
  ui.dialog.addEventListener('click', (event) => {
    if (event.target === ui.dialog) ui.dialog.close();
  });

  document.addEventListener('keydown', (event) => {
    const target = event.target;
    const editing = target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
    if (event.key === '/' && !editing && !ui.dialog.open) {
      event.preventDefault();
      ui.search.focus();
    } else if (event.key === 'Escape' && ui.dialog.open) {
      ui.dialog.close();
    }
  });

  async function start() {
    loadSaved();
    try {
      const response = await fetch('data/catalog.json', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`catalog HTTP ${response.status}`);
      const payload = await response.json();
      if (!payload || !Array.isArray(payload.records)) throw new Error('invalid catalog format');
      state.records = payload.records.filter((record) => record && typeof record.id === 'string' && typeof record.name === 'string');
      byId('stat-tools').textContent = String(state.records.length);
      const claimed = Number(payload.sourceClaimedCount || 0);
      byId('data-note').textContent = claimed && claimed !== state.records.length
        ? `দ্রষ্টব্য: archived README-তে ${claimed}টি active tool-এর দাবি আছে; প্রকাশিত docs/TOOLS.md-এ ${state.records.length}টি তালিকাভুক্ত entry পাওয়া গেছে। অনুপস্থিত entry বা source link অনুমান করে যোগ করা হয়নি।`
        : `উৎস: ${payload.generatedFrom || 'archived catalog'} · ${state.records.length}টি metadata record।`;
      render();
    } catch (error) {
      console.error('SecureShelf catalog failed to load:', error);
      ui.grid.setAttribute('aria-busy', 'false');
      ui.grid.hidden = true;
      ui.empty.hidden = false;
      byId('result-count').textContent = 'ক্যাটালগ লোড করা যায়নি। পেজ refresh করুন অথবা catalog file পরীক্ষা করুন।';
      byId('data-note').textContent = 'কোনো tool চালানো হয়নি।';
    }
  }

  start();
})();
