(() => {
  'use strict';

  const PAGE_SIZE = 18;
  const STORAGE_KEY = 'secureshelf.saved.v1';
  const REPOSITORY_URL = 'https://github.com/HumayunShariarHimu/HackingTools';
  const typeLabels = { tool: 'Tool', reference: 'Reference', service: 'Online service' };
  const state = {
    records: [],
    query: '',
    category: 'all',
    type: 'all',
    status: 'all',
    tag: '',
    savedOnly: false,
    sort: 'source',
    visible: PAGE_SIZE,
    saved: new Set(),
    activeRecord: null,
    dialogOpener: null,
    toastTimer: null,
  };

  const byId = (id) => document.getElementById(id);
  const ui = {
    grid: byId('resource-grid'),
    search: byId('search-input'),
    type: byId('type-filter'),
    status: byId('status-filter'),
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

  function normalizeRecord(record) {
    if (!record || typeof record.id !== 'string' || !record.id || typeof record.name !== 'string' || !record.name.trim()) return null;
    if (typeof record.category !== 'string' || !record.category.trim()) return null;
    const type = Object.hasOwn(typeLabels, record.type) ? record.type : 'tool';
    const tags = Array.isArray(record.tags)
      ? record.tags.filter((tag) => typeof tag === 'string' && tag.trim()).slice(0, 40)
      : [];
    return {
      id: record.id,
      name: record.name.trim(),
      category: record.category.trim(),
      tags,
      type,
      description: typeof record.description === 'string' ? record.description : 'Review the archived source for more information.',
      sourceUrl: safeExternalUrl(record.sourceUrl),
      archiveUrl: safeExternalUrl(record.archiveUrl),
      platform: typeof record.platform === 'string' ? record.platform : '',
      status: record.status === 'archived' ? 'archived' : 'active',
      statusReason: typeof record.statusReason === 'string' ? record.statusReason : '',
    };
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
      showToast('Favorites could not be saved in this browser.');
    }
    ui.savedCount.textContent = String(state.saved.size);
  }

  function showToast(message) {
    ui.toast.textContent = message;
    ui.toast.classList.add('is-visible');
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => ui.toast.classList.remove('is-visible'), 2400);
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
    allButton.append(node('span', '', 'All resources'));
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
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'en'))
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
    if (state.status !== 'all' && record.status !== state.status) return false;
    if (state.tag && !record.tags.includes(state.tag)) return false;
    if (state.savedOnly && !state.saved.has(record.id)) return false;
    if (!state.query) return true;
    const sourceHost = record.sourceUrl ? new URL(record.sourceUrl).hostname : '';
    const haystack = [record.name, record.category, record.description, typeLabels[record.type], sourceHost, ...record.tags]
      .join(' ')
      .toLocaleLowerCase('en');
    return haystack.includes(state.query.toLocaleLowerCase('en'));
  }

  function filteredRecords() {
    const results = state.records.filter(matches);
    if (state.sort === 'name') {
      results.sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }));
    }
    return results;
  }

  function updateActiveFilters() {
    ui.activeFilters.replaceChildren();
    const filters = [];
    if (state.category !== 'all') filters.push(['Category', state.category, 'category']);
    if (state.type !== 'all') filters.push(['Type', typeLabels[state.type], 'type']);
    if (state.status !== 'all') filters.push(['Status', state.status === 'archived' ? 'Archived' : 'Active', 'status']);
    if (state.tag) filters.push(['Tag', state.tag, 'tag']);
    if (state.savedOnly) filters.push(['View', 'Saved only', 'saved']);
    if (state.query) filters.push(['Search', `“${state.query}”`, 'query']);

    for (const [label, value, key] of filters) {
      const chip = node('span', 'active-chip');
      chip.append(node('span', '', `${label}: ${value}`));
      const remove = node('button', '', '×');
      remove.type = 'button';
      remove.setAttribute('aria-label', `Remove ${label.toLocaleLowerCase('en')} filter`);
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
    if (record.status === 'archived') {
      const archivedBadge = node('span', 'status-badge', 'Archived');
      archivedBadge.dataset.status = 'archived';
      top.append(archivedBadge);
    }
    const type = node('span', 'type-badge', typeLabels[record.type]);
    type.dataset.type = record.type;
    top.append(type);

    const title = node('button', 'card-title-button', record.name);
    title.type = 'button';
    title.dataset.action = 'details';
    title.dataset.id = record.id;
    title.setAttribute('aria-label', `${record.name} — open resource details`);

    const description = node('p', 'card-description', record.description);
    const tags = node('div', 'card-tags');
    for (const tag of record.tags.slice(0, 4)) {
      const tagButton = node('button', 'resource-tag', tag);
      tagButton.type = 'button';
      tagButton.dataset.action = 'tag';
      tagButton.dataset.tag = tag;
      tagButton.setAttribute('aria-label', `Filter by ${tag} tag`);
      tags.append(tagButton);
    }

    const footer = node('div', 'card-footer');
    const sourceHost = record.sourceUrl ? new URL(record.sourceUrl).hostname : '';
    footer.append(node('span', `source-status${sourceHost ? ' has-source' : ''}`, sourceHost ? `HTTPS source · ${sourceHost}` : 'No HTTPS source link listed'));
    const actions = node('div', 'card-actions');
    const detailButton = node('button', 'card-detail', 'Details ↗');
    detailButton.type = 'button';
    detailButton.dataset.action = 'details';
    detailButton.dataset.id = record.id;
    const saveButton = node('button', 'card-save', state.saved.has(record.id) ? '★' : '☆');
    saveButton.type = 'button';
    saveButton.dataset.action = 'save';
    saveButton.dataset.id = record.id;
    saveButton.setAttribute('aria-pressed', String(state.saved.has(record.id)));
    saveButton.setAttribute('aria-label', state.saved.has(record.id) ? `Remove ${record.name} from saved resources` : `Save ${record.name}`);
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
    ui.resultCount.replaceChildren();
    const strong = node('strong', '', String(results.length));
    ui.resultCount.append(strong, document.createTextNode(` of ${state.records.length} catalog entries`));
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
      showToast('Removed from saved resources.');
    } else {
      state.saved.add(id);
      showToast('Saved in this browser.');
    }
    persistSaved();
    render();
    if (state.activeRecord && state.activeRecord.id === id) updateDialogSave();
  }

  function updateDialogSave() {
    const record = state.activeRecord;
    if (!record) return;
    const isSaved = state.saved.has(record.id);
    byId('dialog-save').textContent = isSaved ? '★ Remove from saved' : '☆ Save this resource';
    byId('dialog-save').setAttribute('aria-pressed', String(isSaved));
  }

  function openDetails(id) {
    const record = state.records.find((item) => item.id === id);
    if (!record) return;
    state.activeRecord = record;
    state.dialogOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    byId('dialog-category').textContent = record.category;
    byId('dialog-title').textContent = record.name;
    byId('dialog-description').textContent = record.description;
    byId('dialog-type').textContent = typeLabels[record.type];
    byId('dialog-status').textContent = record.status === 'archived' ? 'Archived in the source project' : 'Published resource';
    byId('dialog-platform').textContent = record.platform || 'Not listed in the archived source';
    const sourceUrl = safeExternalUrl(record.sourceUrl);
    byId('dialog-source-status').textContent = sourceUrl ? new URL(sourceUrl).hostname : 'No HTTPS source URL is listed for this entry.';
    const archiveNote = byId('dialog-archive-note');
    archiveNote.hidden = record.status !== 'archived';
    archiveNote.textContent = record.status === 'archived'
      ? `Archived entry. The source project marks it as deprecated or unavailable: ${record.statusReason || 'No reason was recorded.'} This directory does not run it.`
      : '';
    const sourceLink = byId('dialog-source-link');
    sourceLink.hidden = !sourceUrl;
    sourceLink.href = sourceUrl || '#';
    const archiveLink = byId('dialog-archive-link');
    archiveLink.href = safeExternalUrl(record.archiveUrl) || REPOSITORY_URL;
    const copyButton = byId('dialog-copy');
    copyButton.hidden = !sourceUrl;
    copyButton.dataset.url = sourceUrl;
    const tags = byId('dialog-tags');
    tags.replaceChildren();
    for (const tag of record.tags) tags.append(node('span', 'resource-tag', tag));
    updateDialogSave();
    if (!ui.dialog.open) ui.dialog.showModal();
    ui.dialog.querySelector('[data-action="close-dialog"]').focus();
  }

  function clearFilters() {
    state.query = '';
    state.category = 'all';
    state.type = 'all';
    state.status = 'all';
    state.tag = '';
    state.savedOnly = false;
    state.sort = 'source';
    state.visible = PAGE_SIZE;
    ui.search.value = '';
    ui.type.value = 'all';
    ui.status.value = 'all';
    ui.sort.value = 'source';
    render();
  }

  function removeFilter(filter) {
    if (filter === 'category') state.category = 'all';
    if (filter === 'type') { state.type = 'all'; ui.type.value = 'all'; }
    if (filter === 'status') { state.status = 'all'; ui.status.value = 'all'; }
    if (filter === 'tag') state.tag = '';
    if (filter === 'saved') state.savedOnly = false;
    if (filter === 'query') { state.query = ''; ui.search.value = ''; }
    state.visible = PAGE_SIZE;
    render();
  }

  document.addEventListener('click', async (event) => {
    const target = event.target instanceof Element ? event.target.closest('[data-action]') : null;
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
  ui.status.addEventListener('change', () => {
    state.status = ui.status.value;
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
    const sourceUrl = safeExternalUrl(event.currentTarget.dataset.url);
    if (!sourceUrl) return;
    try {
      await navigator.clipboard.writeText(sourceUrl);
      showToast('Source URL copied.');
    } catch {
      showToast('Could not copy. Open the source link and copy its URL.');
    }
  });
  ui.dialog.addEventListener('click', (event) => {
    if (event.target === ui.dialog) ui.dialog.close();
  });
  ui.dialog.addEventListener('close', () => {
    const opener = state.dialogOpener;
    state.activeRecord = null;
    state.dialogOpener = null;
    if (opener && opener.isConnected) opener.focus();
  });

  window.addEventListener('storage', (event) => {
    if (event.key !== STORAGE_KEY) return;
    try {
      const next = JSON.parse(event.newValue || '[]');
      state.saved = new Set(Array.isArray(next) ? next.filter((id) => typeof id === 'string') : []);
    } catch {
      state.saved = new Set();
    }
    render();
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
      if (!response.ok) throw new Error(`Catalog HTTP ${response.status}`);
      const payload = await response.json();
      if (!payload || !Array.isArray(payload.records)) throw new Error('Invalid catalog format');
      const ids = new Set();
      state.records = payload.records.map(normalizeRecord).filter((record) => {
        if (!record || ids.has(record.id)) return false;
        ids.add(record.id);
        return true;
      });
      if (!state.records.length) throw new Error('No usable catalog entries');

      const sourceCount = state.records.filter((record) => record.sourceUrl).length;
      byId('stat-tools').textContent = String(state.records.length);
      byId('stat-sources').textContent = String(sourceCount);
      const archivedCount = state.records.filter((record) => record.status === 'archived').length;
      byId('source-count-note').textContent = `${archivedCount} archived entries are included and clearly labeled.`;
      byId('data-note').textContent = typeof payload.note === 'string' ? payload.note : `${payload.generatedFrom || 'Archived catalog'} · ${state.records.length} metadata-only records.`;
      render();
    } catch (error) {
      console.error('SecureShelf catalog failed to load:', error);
      ui.grid.setAttribute('aria-busy', 'false');
      ui.grid.hidden = true;
      ui.empty.hidden = false;
      byId('empty-state').querySelector('h3').textContent = 'The catalog could not be loaded';
      byId('empty-state').querySelector('p').textContent = 'Refresh the page or check that the catalog file is available.';
      byId('empty-clear').hidden = true;
      byId('result-count').textContent = 'Catalog unavailable';
      byId('data-note').textContent = 'No resource, script or command was executed.';
    }
  }

  start();
})();
