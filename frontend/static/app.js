// State
let currentManga = null;
let selectedChapterIds = new Set();
let activeTaskId = null;
let activeEventSource = null;
let lastClickedCheckboxIdx = null;
let searchDebounceTimer = null;

// DOM Elements
const urlInput = document.getElementById("urlInput");
const scanBtn = document.getElementById("scanBtn");
const scanBtnText = document.getElementById("scanBtnText");
const scanLoading = document.getElementById("scanLoading");
const errorAlert = document.getElementById("errorAlert");
const errorMessage = document.getElementById("errorMessage");
const errorTitle = document.getElementById("errorTitle");
const searchDropdown = document.getElementById("searchDropdown");

const mangaView = document.getElementById("mangaView");
const mangaCover = document.getElementById("mangaCover");
const mangaBackdrop = document.getElementById("mangaBackdrop");
const mangaTitle = document.getElementById("mangaTitle");
const mangaAuthor = document.getElementById("mangaAuthor");
const mangaSynopsis = document.getElementById("mangaSynopsis");
const mangaStatusBadge = document.getElementById("mangaStatusBadge");
const mangaSourceBadge = document.getElementById("mangaSourceBadge");
const mangaLanguageBadge = document.getElementById("mangaLanguageBadge");
const mangaTotalChapters = document.getElementById("mangaTotalChapters");
const mangaGenres = document.getElementById("mangaGenres");
const languageSelect = document.getElementById("languageSelect");

const selectFromChapter = document.getElementById("selectFromChapter");
const selectToChapter = document.getElementById("selectToChapter");
const rangeFromBadge = document.getElementById("rangeFromBadge");
const rangeToBadge = document.getElementById("rangeToBadge");
const chapterFilterInput = document.getElementById("chapterFilterInput");
const chapterListContainer = document.getElementById("chapterListContainer");
const selectedCountBadge = document.getElementById("selectedCountBadge");

const stickyActionBar = document.getElementById("stickyActionBar");
const stickySelectedCount = document.getElementById("stickySelectedCount");
const stickyFormatBadge = document.getElementById("stickyFormatBadge");
const stickyRangeText = document.getElementById("stickyRangeText");

const progressModal = document.getElementById("progressModal");
const progressModalTitle = document.getElementById("progressModalTitle");
const progressModalMsg = document.getElementById("progressModalMsg");
const progressBarFill = document.getElementById("progressBarFill");
const progressPageDetail = document.getElementById("progressPageDetail");
const progressPercentDetail = document.getElementById("progressPercentDetail");
const progressCurrentChapter = document.getElementById("progressCurrentChapter");
const progressIcon = document.getElementById("progressIcon");
const cancelTaskBtn = document.getElementById("cancelTaskBtn");
const downloadCompletedBtn = document.getElementById("downloadCompletedBtn");
const completedSizeText = document.getElementById("completedSizeText");

const historyDrawer = document.getElementById("historyDrawer");
const historyListContainer = document.getElementById("historyListContainer");
const historyBadge = document.getElementById("historyBadge");

function safeCreateIcons() {
  if (typeof lucide !== "undefined" && lucide && typeof lucide.createIcons === "function") {
    try {
      lucide.createIcons();
    } catch (e) {}
  }
}

// Event Listeners
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    searchDropdown.classList.add("hidden");
    handleScanOrSearch();
  }
});

urlInput.addEventListener("input", (e) => {
  const val = e.target.value.trim();
  clearTimeout(searchDebounceTimer);

  if (val.length >= 2 && !val.startsWith("http://") && !val.startsWith("https://")) {
    searchDebounceTimer = setTimeout(() => {
      fetchSearchSuggestions(val);
    }, 350);
  } else {
    searchDropdown.classList.add("hidden");
  }
});

document.addEventListener("click", (e) => {
  if (!searchDropdown.contains(e.target) && e.target !== urlInput) {
    searchDropdown.classList.add("hidden");
  }
});

// Clipboard Helper
async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      urlInput.value = text;
      handleScanOrSearch();
    }
  } catch (err) {
    console.error("Clipboard paste error:", err);
  }
}

function quickSelectManga(title) {
  urlInput.value = title;
  handleScanOrSearch();
}

function resetToHome() {
  mangaView.classList.add("hidden");
  stickyActionBar.classList.add("hidden");
  hideError();
  urlInput.value = "";
  currentManga = null;
  selectedChapterIds.clear();
}

// Search Suggestions API
async function fetchSearchSuggestions(query) {
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=6`);
    if (!res.ok) return;
    const results = await res.json();

    if (results.length === 0) {
      searchDropdown.innerHTML = `<div class="p-4 text-xs text-slate-400 text-center">No manga found matching "${query}"</div>`;
      searchDropdown.classList.remove("hidden");
      return;
    }

    searchDropdown.innerHTML = results.map(item => `
      <div 
        class="p-3 hover:bg-dark-card/90 cursor-pointer flex items-center gap-3 transition-colors"
        onclick="selectSearchResult('${item.id}', '${escapeHtml(item.title)}')"
      >
        <img 
          src="${item.cover_url || '/static/placeholder.png'}" 
          alt="${escapeHtml(item.title)}" 
          class="w-10 h-14 object-cover rounded-lg bg-dark-bg shrink-0 border border-dark-border"
          onerror="this.src='https://placehold.co/80x120/161a29/818cf8?text=Manga'"
        />
        <div class="flex-1 min-w-0">
          <p class="text-sm font-bold text-white truncate">${escapeHtml(item.title)}</p>
          <p class="text-xs text-slate-400 truncate">${escapeHtml(item.author || 'Unknown Author')}</p>
          <div class="flex items-center gap-2 mt-1">
            <span class="text-[10px] px-1.5 py-0.2 rounded bg-brand-500/20 text-brand-300 font-semibold uppercase">${item.source_name}</span>
            <span class="text-[10px] text-slate-500">${item.status || ''}</span>
          </div>
        </div>
      </div>
    `).join("");

    searchDropdown.classList.remove("hidden");
  } catch (err) {
    console.error("Search suggestion error:", err);
  }
}

function selectSearchResult(id, title) {
  urlInput.value = `https://mangadex.org/title/${id}`;
  searchDropdown.classList.add("hidden");
  handleScanOrSearch();
}

// Scan or Search Manga
async function handleScanOrSearch(selectedLanguage = "en") {
  const query = urlInput.value.trim();
  if (!query) return;

  hideError();
  searchDropdown.classList.add("hidden");
  scanLoading.classList.remove("hidden");
  mangaView.classList.add("hidden");
  stickyActionBar.classList.add("hidden");
  scanBtn.disabled = true;
  scanBtnText.textContent = "Scanning...";

  try {
    let scanPayload = { url: query, language: selectedLanguage };

    // If query is plain text title and not a URL/UUID, search first and pick the first match
    if (!query.startsWith("http://") && !query.startsWith("https://") && !query.match(/^[0-9a-f-]{36}$/)) {
      const searchRes = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=1`);
      if (searchRes.ok) {
        const list = await searchRes.json();
        if (list && list.length > 0) {
          scanPayload.url = `https://mangadex.org/title/${list[0].id}`;
        }
      }
    }

    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scanPayload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Could not scan manga. Please verify URL.");
    }

    const data = await res.json();
    displayMangaDetails(data);
  } catch (err) {
    showError("Scan Failed", err.message);
  } finally {
    scanLoading.classList.add("hidden");
    scanBtn.disabled = false;
    scanBtnText.textContent = "Scan";
  }
}

function displayMangaDetails(manga) {
  currentManga = manga;
  selectedChapterIds.clear();

  // Populate Details
  mangaTitle.textContent = manga.title || "Unknown Title";
  mangaAuthor.querySelector("span").textContent = manga.author ? `By ${manga.author}` : "Author Unknown";
  mangaSynopsis.textContent = manga.synopsis || "No description provided.";
  
  if (manga.cover_url) {
    mangaCover.src = manga.cover_url;
    mangaBackdrop.style.backgroundImage = `url('${manga.cover_url}')`;
  } else {
    mangaCover.src = "https://placehold.co/400x600/161a29/818cf8?text=No+Cover";
    mangaBackdrop.style.backgroundImage = "none";
  }

  mangaStatusBadge.textContent = manga.status || "Ongoing";
  mangaSourceBadge.textContent = manga.source_name || "Manga";
  mangaLanguageBadge.textContent = (manga.available_languages && manga.available_languages[0]) ? manga.available_languages[0].toUpperCase() : "EN";
  mangaTotalChapters.textContent = `${manga.chapters.length} Chapters`;

  // Populate Genres
  mangaGenres.innerHTML = (manga.genres || []).map(g => `
    <span class="px-2.5 py-0.5 rounded-full text-xs font-medium bg-dark-card border border-dark-border text-slate-300">
      ${escapeHtml(g)}
    </span>
  `).join("");

  // Populate Language Selector
  if (manga.available_languages && manga.available_languages.length > 1) {
    languageSelect.innerHTML = manga.available_languages.map(l => `
      <option value="${l}">${l.toUpperCase()}</option>
    `).join("");
    languageSelect.parentElement.classList.remove("hidden");
  } else {
    languageSelect.parentElement.classList.add("hidden");
  }

  // Populate Translation Group Options
  const groupSelect = document.getElementById("scanGroupSelect");
  if (groupSelect && manga.chapters) {
    const groups = Array.from(new Set(manga.chapters.map(c => c.scanlation_group).filter(Boolean)));
    let opts = `<option value="dedupe">✨ Recommended Group (1 version per chapter)</option>`;
    opts += `<option value="all">Show All Versions & Groups (${manga.chapters.length} Total)</option>`;
    groups.forEach(g => {
      opts += `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`;
    });
    groupSelect.innerHTML = opts;
    groupSelect.value = "dedupe";
    isDeduplicateEnabled = true;
    selectedGroupFilter = "dedupe";
    updateDedupeBtnUI();
  }

  // Setup Chapter Dropdowns
  populateChapterDropdowns(manga);

  // Default: Select first 5 chapters or all if <= 5
  if (manga.chapters.length <= 5) {
    selectPreset("all");
  } else {
    selectPreset("first5");
  }

  renderChapterList();
  renderBatchRangePills();
  mangaView.classList.remove("hidden");
  safeCreateIcons();

  // Scroll smoothly to manga view
  mangaView.scrollIntoView({ behavior: "smooth", block: "start" });
}

let isDeduplicateEnabled = true;
let selectedGroupFilter = "dedupe";

function getActiveChapters() {
  if (!currentManga || !currentManga.chapters) return [];

  const rawChapters = currentManga.chapters;

  if (selectedGroupFilter !== "all" && selectedGroupFilter !== "dedupe") {
    return rawChapters.filter(c => c.scanlation_group === selectedGroupFilter);
  }

  if (isDeduplicateEnabled || selectedGroupFilter === "dedupe") {
    const seenNumbers = new Map();
    rawChapters.forEach(ch => {
      const numKey = ch.chapter_number > 0 ? ch.chapter_number : ch.chapter_display;
      if (!seenNumbers.has(numKey)) {
        seenNumbers.set(numKey, ch);
      }
    });
    return Array.from(seenNumbers.values());
  }

  return rawChapters;
}

function handleGroupFilterChange() {
  const select = document.getElementById("scanGroupSelect");
  if (!select) return;

  selectedGroupFilter = select.value;
  if (selectedGroupFilter === "dedupe") {
    isDeduplicateEnabled = true;
  } else if (selectedGroupFilter === "all") {
    isDeduplicateEnabled = false;
  }
  updateDedupeBtnUI();
  selectPreset("all");
  renderBatchRangePills();
}

function toggleDeduplication() {
  isDeduplicateEnabled = !isDeduplicateEnabled;
  const select = document.getElementById("scanGroupSelect");
  if (select) {
    select.value = isDeduplicateEnabled ? "dedupe" : "all";
    selectedGroupFilter = select.value;
  }
  updateDedupeBtnUI();
  selectPreset("all");
  renderBatchRangePills();
}

function updateDedupeBtnUI() {
  const btn = document.getElementById("dedupeToggleBtn");
  const text = document.getElementById("dedupeToggleText");
  if (!btn || !text) return;

  if (isDeduplicateEnabled) {
    btn.className = "px-3 py-1.5 rounded-xl bg-brand-500/20 text-brand-300 border border-brand-500/40 font-bold flex items-center gap-1.5 transition-all shadow-sm active:scale-95";
    text.textContent = "Deduplicate (1 per Ch.)";
  } else {
    btn.className = "px-3 py-1.5 rounded-xl bg-dark-surface text-slate-400 border border-dark-border font-medium flex items-center gap-1.5 transition-all shadow-sm active:scale-95";
    text.textContent = "Show All Versions";
  }
  safeCreateIcons();
}

function populateChapterDropdowns(manga) {
  const activeChs = getActiveChapters();
  if (!activeChs || activeChs.length === 0) {
    selectFromChapter.innerHTML = `<option value="">No chapters available</option>`;
    selectToChapter.innerHTML = `<option value="">No chapters available</option>`;
    return;
  }

  const optionsHtml = activeChs.map((ch, idx) => {
    const titlePart = ch.title && ch.title !== ch.chapter_display ? ` - ${escapeHtml(ch.title)}` : "";
    const groupPart = ch.scanlation_group ? ` (${escapeHtml(ch.scanlation_group)})` : "";
    return `<option value="${ch.id}" data-idx="${idx}">${escapeHtml(ch.chapter_display)}${titlePart}${groupPart}</option>`;
  }).join("");

  selectFromChapter.innerHTML = optionsHtml;
  selectToChapter.innerHTML = optionsHtml;
}

function renderChapterList() {
  if (!currentManga || !currentManga.chapters) return;

  const activeChs = getActiveChapters();
  const filterText = (chapterFilterInput.value || "").toLowerCase().trim();

  const filtered = activeChs.filter(ch => {
    if (!filterText) return true;
    return (
      ch.chapter_display.toLowerCase().includes(filterText) ||
      (ch.title && ch.title.toLowerCase().includes(filterText)) ||
      (ch.scanlation_group && ch.scanlation_group.toLowerCase().includes(filterText))
    );
  });

  mangaTotalChapters.textContent = `${activeChs.length} Chapters${activeChs.length < currentManga.chapters.length ? ' (Deduplicated)' : ''}`;

  if (filtered.length === 0) {
    chapterListContainer.innerHTML = `
      <div class="p-8 text-center text-xs text-slate-400">
        No chapters match "${filterText}"
      </div>
    `;
    return;
  }

  chapterListContainer.innerHTML = filtered.map((ch, idx) => {
    const isChecked = selectedChapterIds.has(ch.id);
    const dateStr = ch.publish_date ? ch.publish_date : "";
    const groupStr = ch.scanlation_group ? ch.scanlation_group : "";

    return `
      <div 
        class="px-6 py-3.5 flex items-center justify-between gap-4 hover:bg-dark-surface/60 transition-colors cursor-pointer group ${isChecked ? 'bg-brand-500/5' : ''}"
        onclick="handleChapterRowClick(event, '${ch.id}', ${idx})"
      >
        <div class="flex items-center gap-3.5 min-w-0">
          <input 
            type="checkbox" 
            id="chk_${ch.id}" 
            ${isChecked ? 'checked' : ''} 
            class="w-4 h-4 rounded border-dark-border cursor-pointer"
            onclick="event.stopPropagation(); handleCheckboxToggle('${ch.id}', ${idx}, event)"
          />
          <div class="flex items-center gap-2 min-w-0">
            <span class="px-2 py-0.5 rounded-lg text-xs font-bold bg-dark-surface border border-dark-border text-brand-300 font-mono shrink-0">
              ${escapeHtml(ch.chapter_display)}
            </span>
            <span class="text-sm font-medium text-slate-200 truncate group-hover:text-white transition-colors">
              ${escapeHtml(ch.title || '')}
            </span>
          </div>
        </div>

        <div class="flex items-center gap-4 text-xs text-slate-400 shrink-0">
          ${groupStr ? `<span class="hidden sm:inline-block px-2 py-0.5 rounded bg-dark-surface border border-dark-border text-[11px] text-slate-400">${escapeHtml(groupStr)}</span>` : ''}
          ${dateStr ? `<span class="hidden md:inline font-mono text-[11px] text-slate-500">${dateStr}</span>` : ''}
          ${ch.url ? `<a href="${ch.url}" target="_blank" onclick="event.stopPropagation()" class="p-1 text-slate-500 hover:text-brand-400 transition-colors" title="Open Chapter Link"><i data-lucide="external-link" class="w-3.5 h-3.5"></i></a>` : ''}
        </div>
      </div>
    `;
  }).join("");

  updateSelectionState();
  safeCreateIcons();
}

function handleChapterRowClick(event, chId, idx) {
  const isChecked = selectedChapterIds.has(chId);
  if (isChecked) {
    selectedChapterIds.delete(chId);
  } else {
    selectedChapterIds.add(chId);
  }
  lastClickedCheckboxIdx = idx;
  renderChapterList();
}

function handleCheckboxToggle(chId, idx, event) {
  const activeChs = getActiveChapters();
  if (event.shiftKey && lastClickedCheckboxIdx !== null && activeChs) {
    const start = Math.min(lastClickedCheckboxIdx, idx);
    const end = Math.max(lastClickedCheckboxIdx, idx);
    const shouldCheck = event.target.checked;

    for (let i = start; i <= end; i++) {
      const targetCh = activeChs[i];
      if (targetCh) {
        if (shouldCheck) selectedChapterIds.add(targetCh.id);
        else selectedChapterIds.delete(targetCh.id);
      }
    }
  } else {
    if (event.target.checked) {
      selectedChapterIds.add(chId);
    } else {
      selectedChapterIds.delete(chId);
    }
  }

  lastClickedCheckboxIdx = idx;
  renderChapterList();
}

function updateSelectionState() {
  const count = selectedChapterIds.size;
  selectedCountBadge.textContent = `${count} selected`;
  stickySelectedCount.textContent = count;

  const exportFormat = document.querySelector('input[name="exportFormat"]:checked')?.value.toUpperCase() || "PDF";
  stickyFormatBadge.textContent = exportFormat;

  if (count > 0 && currentManga) {
    stickyActionBar.classList.remove("hidden");
    
    const activeChs = getActiveChapters();
    const selectedChs = activeChs.filter(c => selectedChapterIds.has(c.id));
    if (selectedChs.length > 0) {
      const firstCh = selectedChs[0];
      const lastCh = selectedChs[selectedChs.length - 1];
      
      const firstDisp = firstCh.chapter_display;
      const lastDisp = lastCh.chapter_display;
      stickyRangeText.textContent = selectedChs.length === 1 ? firstDisp : `${firstDisp} → ${lastDisp}`;

      if (selectFromChapter && selectFromChapter.value !== firstCh.id) {
        selectFromChapter.value = firstCh.id;
      }
      if (selectToChapter && selectToChapter.value !== lastCh.id) {
        selectToChapter.value = lastCh.id;
      }
      if (rangeFromBadge) rangeFromBadge.textContent = firstDisp;
      if (rangeToBadge) rangeToBadge.textContent = lastDisp;
    }
  } else {
    stickyActionBar.classList.add("hidden");
    if (rangeFromBadge) rangeFromBadge.textContent = "";
    if (rangeToBadge) rangeToBadge.textContent = "";
  }
}

// Chapter Dropdown Range Selection
function handleDropdownRangeChange() {
  if (!currentManga || !currentManga.chapters || currentManga.chapters.length === 0) return;

  const activeChs = getActiveChapters();
  const fromId = selectFromChapter.value;
  const toId = selectToChapter.value;

  if (!fromId || !toId) return;

  const fromIdx = activeChs.findIndex(c => c.id === fromId);
  const toIdx = activeChs.findIndex(c => c.id === toId);

  if (fromIdx === -1 || toIdx === -1) return;

  const start = Math.min(fromIdx, toIdx);
  const end = Math.max(fromIdx, toIdx);

  selectedChapterIds.clear();
  for (let i = start; i <= end; i++) {
    selectedChapterIds.add(activeChs[i].id);
  }

  renderChapterList();
}

function renderBatchRangePills() {
  const container = document.getElementById("dynamicBatchRanges");
  const activeChs = getActiveChapters();
  if (!container || !activeChs || activeChs.length <= 10) {
    if (container) container.innerHTML = "";
    return;
  }

  const total = activeChs.length;
  const step = 20;

  let pillsHtml = `<span class="text-slate-500 font-semibold mr-1">Quick Batches:</span>`;
  for (let i = 0; i < total; i += step) {
    const endIdx = Math.min(total - 1, i + step - 1);
    const startCh = activeChs[i].chapter_display;
    const endCh = activeChs[endIdx].chapter_display;
    pillsHtml += `
      <button 
        type="button"
        onclick="setExplicitRange(${i}, ${endIdx})"
        class="px-2.5 py-1 rounded-lg bg-dark-card hover:bg-dark-border text-slate-300 hover:text-white border border-dark-border text-[11px] font-mono transition-colors"
      >
        ${startCh}-${endCh}
      </button>
    `;
  }

  container.innerHTML = pillsHtml;
}

function setExplicitRange(startIdx, endIdx) {
  if (!currentManga || !currentManga.chapters) return;
  const activeChs = getActiveChapters();

  selectedChapterIds.clear();
  for (let i = startIdx; i <= endIdx; i++) {
    if (activeChs[i]) selectedChapterIds.add(activeChs[i].id);
  }

  if (activeChs[startIdx] && selectFromChapter) selectFromChapter.value = activeChs[startIdx].id;
  if (activeChs[endIdx] && selectToChapter) selectToChapter.value = activeChs[endIdx].id;

  renderChapterList();
}

// Quick Presets
function selectPreset(type) {
  if (!currentManga || !currentManga.chapters) return;
  const activeChs = getActiveChapters();

  selectedChapterIds.clear();

  if (type === "all") {
    activeChs.forEach(c => selectedChapterIds.add(c.id));
  } else if (type === "first5") {
    activeChs.slice(0, 5).forEach(c => selectedChapterIds.add(c.id));
  } else if (type === "first10") {
    activeChs.slice(0, 10).forEach(c => selectedChapterIds.add(c.id));
  } else if (type === "latest10") {
    activeChs.slice(-10).forEach(c => selectedChapterIds.add(c.id));
  } else if (type === "none") {
    selectedChapterIds.clear();
  }

  populateChapterDropdowns(currentManga);

  if (selectedChapterIds.size > 0) {
    const selected = activeChs.filter(c => selectedChapterIds.has(c.id));
    if (selected.length > 0) {
      if (selectFromChapter) selectFromChapter.value = selected[0].id;
      if (selectToChapter) selectToChapter.value = selected[selected.length - 1].id;
    }
  }

  renderChapterList();
}

function toggleSelectAllVisible() {
  if (!currentManga) return;
  const filterText = (chapterFilterInput.value || "").toLowerCase().trim();
  const visible = currentManga.chapters.filter(ch => {
    if (!filterText) return true;
    return ch.chapter_display.toLowerCase().includes(filterText) || (ch.title && ch.title.toLowerCase().includes(filterText));
  });

  const allVisibleSelected = visible.every(c => selectedChapterIds.has(c.id));
  visible.forEach(c => {
    if (allVisibleSelected) selectedChapterIds.delete(c.id);
    else selectedChapterIds.add(c.id);
  });

  renderChapterList();
}

function filterChapterList() {
  renderChapterList();
}

function updateFormatUI() {
  updateSelectionState();
}

function changeLanguage() {
  const lang = languageSelect.value;
  handleScanOrSearch(lang);
}

function toggleSynopsis() {
  const isExpanded = mangaSynopsis.classList.contains("line-clamp-none");
  const btn = document.getElementById("toggleSynopsisBtn");
  if (isExpanded) {
    mangaSynopsis.classList.remove("line-clamp-none");
    mangaSynopsis.classList.add("line-clamp-3");
    btn.innerHTML = `<span>Read More</span><i data-lucide="chevron-down" class="w-3.5 h-3.5"></i>`;
  } else {
    mangaSynopsis.classList.remove("line-clamp-3");
    mangaSynopsis.classList.add("line-clamp-none");
    btn.innerHTML = `<span>Show Less</span><i data-lucide="chevron-up" class="w-3.5 h-3.5"></i>`;
  }
  safeCreateIcons();
}

// Download Execution & Real-time Progress Tracking
async function triggerDownload() {
  if (!currentManga || selectedChapterIds.size === 0) return;

  const rawBundleMode = document.getElementById("bundleMode").value;
  let bundleMode = rawBundleMode;
  let extraOptions = {};

  if (rawBundleMode === "volumes_25") {
    bundleMode = "volumes";
    extraOptions = { volume_size: 25 };
  } else if (rawBundleMode === "volumes_50") {
    bundleMode = "volumes";
    extraOptions = { volume_size: 50 };
  }

  const dataSaver = document.getElementById("dataSaver").value === "true";

  const payload = {
    manga: currentManga,
    selected_chapter_ids: Array.from(selectedChapterIds),
    format: exportFormat,
    bundle_mode: bundleMode,
    extra_options: extraOptions,
    data_saver: dataSaver
  };

  // Reset Progress Modal
  progressModalTitle.textContent = "Starting Download...";
  progressModalMsg.textContent = "Connecting to chapter image servers...";
  progressBarFill.style.width = "0%";
  progressPageDetail.textContent = `0 / ${selectedChapterIds.size} chapters`;
  progressPercentDetail.textContent = "0%";
  progressCurrentChapter.textContent = "Initializing...";
  progressIcon.setAttribute("data-lucide", "loader-2");
  progressIcon.classList.add("animate-spin");
  cancelTaskBtn.classList.remove("hidden");
  downloadCompletedBtn.classList.add("hidden");
  const kindleBtn = document.getElementById("kindleDirectBtn");
  if (kindleBtn) kindleBtn.classList.add("hidden");
  const doneBtn = document.getElementById("doneProgressBtn");
  if (doneBtn) doneBtn.classList.add("hidden");

  progressModal.classList.remove("hidden");
  safeCreateIcons();

  try {
    const res = await fetch("/api/download/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to start download.");
    }

    const { task_id } = await res.json();
    activeTaskId = task_id;
    listenToProgressSSE(task_id);
  } catch (err) {
    progressModalTitle.textContent = "Download Error";
    progressModalMsg.textContent = err.message;
    progressIcon.setAttribute("data-lucide", "alert-triangle");
    progressIcon.classList.remove("animate-spin");
    cancelTaskBtn.textContent = "Close";
    safeCreateIcons();
  }
}

function listenToProgressSSE(taskId) {
  if (activeEventSource) {
    activeEventSource.close();
  }

  activeEventSource = new EventSource(`/api/tasks/${taskId}/progress`);

  activeEventSource.onmessage = (event) => {
    try {
      const task = JSON.parse(event.data);
      updateProgressModal(task);
    } catch (e) {
      console.error("SSE parse error:", e);
    }
  };

  activeEventSource.onerror = () => {
    // Reconnect or close
  };
}

function updateProgressModal(task) {
  if (task.message) {
    progressModalMsg.textContent = task.message;
  }

  // Calculate percentage dynamically from task fields
  let pct = Number(task.progress_percent);
  if (isNaN(pct) || pct <= 0) {
    if (task.total_pages_overall > 0 && task.total_pages_downloaded > 0) {
      pct = (task.total_pages_downloaded / task.total_pages_overall) * 85.0;
    } else {
      pct = 0;
    }
  }
  pct = Math.min(100, Math.max(0, pct));

  progressBarFill.style.width = `${pct}%`;
  progressPercentDetail.textContent = `${Math.round(pct)}%`;

  if (task.total_pages_overall > 0) {
    progressPageDetail.textContent = `${task.total_pages_downloaded} / ${task.total_pages_overall} pages`;
  } else if (task.total_chapters > 0) {
    progressPageDetail.textContent = `${task.current_chapter_idx} / ${task.total_chapters} chapters`;
  }

  if (task.current_chapter) {
    progressCurrentChapter.textContent = task.current_chapter;
  }

  if (task.status === "downloading" || (task.total_pages_overall > 0 && pct < 85)) {
    progressModalTitle.textContent = `Downloading Pages (${Math.round(pct)}%)...`;
  } else if (task.status === "packaging" || pct >= 85) {
    progressModalTitle.textContent = "Compiling Book...";
  }

  if (task.status === "completed") {
    if (activeEventSource) activeEventSource.close();

    progressModalTitle.textContent = "Download Ready!";
    progressModalMsg.textContent = `Formatted as ${task.format.toUpperCase()} (${task.file_size_formatted})`;
    progressIcon.setAttribute("data-lucide", "check-circle-2");
    progressIcon.classList.remove("animate-spin");
    progressIcon.classList.add("text-emerald-400");
    
    // Track active completed task for Kindle modal
    activeCompletedTask = task;

    cancelTaskBtn.classList.add("hidden");
    downloadCompletedBtn.href = `/api/files/${task.file_id}`;
    downloadCompletedBtn.setAttribute("download", task.filename || "manga");
    completedSizeText.textContent = task.file_size_formatted || "Ready";
    downloadCompletedBtn.classList.remove("hidden");

    // Show Kindle & Done buttons
    const kindleBtn = document.getElementById("kindleDirectBtn");
    if (kindleBtn) kindleBtn.classList.remove("hidden");

    const doneBtn = document.getElementById("doneProgressBtn");
    if (doneBtn) doneBtn.classList.remove("hidden");

    safeCreateIcons();

    // Trigger Confetti Celebration!
    confetti({
      particleCount: 80,
      spread: 70,
      origin: { y: 0.6 }
    });

    // Auto-trigger browser download
    const link = document.createElement("a");
    link.href = `/api/files/${task.file_id}`;
    link.download = task.filename || "manga";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Refresh history
    loadDownloadsHistory();

  } else if (task.status === "error" || task.status === "cancelled") {
    if (activeEventSource) activeEventSource.close();

    progressModalTitle.textContent = task.status === "cancelled" ? "Download Cancelled" : "Download Failed";
    progressModalMsg.textContent = task.error_message || task.message || "An unexpected error occurred.";
    progressIcon.setAttribute("data-lucide", "alert-octagon");
    progressIcon.classList.remove("animate-spin");
    progressIcon.classList.add("text-rose-400");
    cancelTaskBtn.textContent = "Close";
    cancelTaskBtn.classList.remove("hidden");
    downloadCompletedBtn.classList.add("hidden");
    
    const kindleBtn = document.getElementById("kindleDirectBtn");
    if (kindleBtn) kindleBtn.classList.add("hidden");

    const doneBtn = document.getElementById("doneProgressBtn");
    if (doneBtn) doneBtn.classList.add("hidden");

    safeCreateIcons();
  }
}

function closeProgressModal() {
  if (activeEventSource) {
    activeEventSource.close();
  }
  progressModal.classList.add("hidden");
}

// Kindle Integration
let activeCompletedTask = null;
// Universal File Converter & Splitter Tabs
let currentConverterTab = 'convert';
let converterSelectedFiles = [];
let converterSelectedFileId = null;

function switchConverterTab(tab) {
  currentConverterTab = tab;
  const tabBtnConvert = document.getElementById("tabBtnConvert");
  const tabBtnSplit = document.getElementById("tabBtnSplit");
  const convertSection = document.getElementById("convertTabSection");
  const splitSection = document.getElementById("splitTabSection");
  const actionBtn = document.getElementById("startConvertBtn");
  const actionText = document.getElementById("modalActionBtnText");
  const statusBox = document.getElementById("converterStatusBox");
  if (statusBox) statusBox.classList.add("hidden");

  if (tab === 'split') {
    if (tabBtnConvert) tabBtnConvert.className = "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white transition-all";
    if (tabBtnSplit) tabBtnSplit.className = "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-indigo-600 text-white shadow transition-all";
    if (convertSection) convertSection.classList.add("hidden");
    if (splitSection) splitSection.classList.remove("hidden");
    if (actionBtn) actionBtn.className = "w-full py-3.5 px-6 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-extrabold text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-indigo-500/20 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed";
    if (actionText) actionText.textContent = "⚡ Auto-Split Manga (~200MB Volumes)";
  } else {
    if (tabBtnConvert) tabBtnConvert.className = "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-purple-600 text-white shadow transition-all";
    if (tabBtnSplit) tabBtnSplit.className = "flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white transition-all";
    if (convertSection) convertSection.classList.remove("hidden");
    if (splitSection) splitSection.classList.add("hidden");
    if (actionBtn) actionBtn.className = "w-full py-3.5 px-6 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-extrabold text-xs flex items-center justify-center gap-2 transition-all shadow-lg shadow-purple-500/20 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed";
    if (actionText) actionText.textContent = "Convert File Now";
  }
  safeCreateIcons();
}

function openConverterModal(tabOrFileId = 'convert', filename = null) {
  const modal = document.getElementById("converterModal");
  const statusBox = document.getElementById("converterStatusBox");
  if (statusBox) statusBox.classList.add("hidden");

  let initialTab = 'convert';
  if (tabOrFileId === 'split' || tabOrFileId === 'convert') {
    initialTab = tabOrFileId;
    converterSelectedFiles = [];
    converterSelectedFileId = null;
    document.getElementById("converterFileName").textContent = "Click or Drag & Drop Manga Files Here";
    document.getElementById("converterFileSubtext").textContent = "Select any AZW3, MOBI, EPUB, PDF, CBZ, or ZIP files";
  } else if (tabOrFileId && filename) {
    converterSelectedFileId = tabOrFileId;
    converterSelectedFiles = [];
    document.getElementById("converterFileName").textContent = `Selected: ${filename}`;
    document.getElementById("converterFileSubtext").textContent = "From your downloads history. Ready to process!";
  }

  switchConverterTab(initialTab);
  updateConverterFormatUI();

  if (modal) {
    modal.classList.remove("hidden");
    safeCreateIcons();
  }
}

function closeConverterModal() {
  const modal = document.getElementById("converterModal");
  if (modal) modal.classList.add("hidden");
}

function handleConverterFileSelected(event) {
  const files = Array.from(event.target.files || []);
  if (!files || files.length === 0) return;

  converterSelectedFiles = files;
  converterSelectedFileId = null;

  if (files.length === 1) {
    const f = files[0];
    const sizeFormatted = (f.size / (1024 * 1024)).toFixed(1) + " MB";
    document.getElementById("converterFileName").textContent = `📄 ${f.name}`;
    document.getElementById("converterFileSubtext").textContent = `Size: ${sizeFormatted} • Click to change`;
  } else {
    const totalBytes = files.reduce((acc, f) => acc + f.size, 0);
    const totalMB = (totalBytes / (1024 * 1024)).toFixed(1) + " MB";
    document.getElementById("converterFileName").textContent = `📚 ${files.length} Manga Files Selected`;
    document.getElementById("converterFileSubtext").textContent = `Total: ${totalMB} • Ready to process!`;
  }
  
  const statusBox = document.getElementById("converterStatusBox");
  if (statusBox) statusBox.classList.add("hidden");
}

function updateConverterFormatUI() {
  const targetFmt = document.querySelector('input[name="convTargetFormat"]:checked')?.value.toUpperCase() || "AZW3";
  const label = document.getElementById("targetFormatLabel");
  if (label) label.textContent = `Output: ${targetFmt}`;
}

async function executeModalAction() {
  if (currentConverterTab === 'split') {
    await executeFileSplitting();
  } else {
    await executeFileConversion();
  }
}

async function executeFileSplitting() {
  const btn = document.getElementById("startConvertBtn");
  const statusBox = document.getElementById("converterStatusBox");
  
  // Auto-detect format from the source file extension (No manual format picking needed!)
  let detectedFormat = "epub";
  if (converterSelectedFiles.length > 0) {
    const ext = converterSelectedFiles[0].name.split('.').pop().toLowerCase();
    if (["pdf", "epub", "azw3", "mobi", "cbz"].includes(ext)) {
      detectedFormat = ext;
    }
  } else if (converterSelectedFileId) {
    const fn = document.getElementById("converterFileName").textContent;
    const ext = fn.split('.').pop().toLowerCase();
    if (["pdf", "epub", "azw3", "mobi", "cbz"].includes(ext)) {
      detectedFormat = ext;
    }
  }
  const targetFormat = detectedFormat;
  const splitMode = "auto_size";
  const splitValue = 200; // Auto-detect and split ~200 MB per volume

  if (converterSelectedFiles.length === 0 && !converterSelectedFileId) {
    statusBox.className = "p-3.5 rounded-2xl text-xs bg-rose-950/40 border border-rose-500/40 text-rose-200";
    statusBox.innerHTML = "<p class='font-bold'>Please select or drop a manga file to split first!</p>";
    statusBox.classList.remove("hidden");
    return;
  }

  btn.disabled = true;
  safeCreateIcons();

  statusBox.className = "p-3.5 rounded-2xl text-xs bg-indigo-950/40 border border-indigo-500/40 text-indigo-200";
  statusBox.classList.remove("hidden");
  statusBox.innerHTML = `
    <div class="flex items-center gap-2">
      <i data-lucide="loader-2" class="w-4 h-4 animate-spin text-indigo-400"></i>
      <span class="font-bold">⚡ Auto-analyzing & splitting into ~200MB volumes (${targetFormat.toUpperCase()})...</span>
    </div>
  `;
  safeCreateIcons();

  try {
    let sourceFileId = converterSelectedFileId;

    if (!sourceFileId && converterSelectedFiles.length > 0) {
      const file = converterSelectedFiles[0];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("target_format", targetFormat);

      const upRes = await fetch("/api/convert/upload", {
        method: "POST",
        body: formData
      });
      const upData = await upRes.json();
      if (!upRes.ok) throw new Error(upData.detail || "File upload failed.");
      sourceFileId = upData.file_id;
    }

    const res = await fetch("/api/convert/split", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: sourceFileId,
        target_format: targetFormat,
        split_mode: splitMode,
        split_value: splitValue
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Splitting failed.");
    }

    const items = data.items || [];
    let html = `
      <div class="space-y-3">
        <div class="flex items-center gap-2 text-emerald-300 font-bold text-sm">
          <i data-lucide="check-circle" class="w-4 h-4 text-emerald-400"></i>
          <span>Successfully split into ${items.length} volumes!</span>
        </div>
        <div class="max-h-48 overflow-y-auto space-y-1.5 pr-1">
    `;

    items.forEach((item) => {
      html += `
        <div class="flex items-center justify-between p-2 rounded-xl bg-dark-surface border border-dark-border text-xs">
          <div class="min-w-0 flex-1 mr-2">
            <p class="font-semibold text-white truncate">${escapeHtml(item.filename)}</p>
            <p class="text-[10px] text-slate-400 font-mono">${item.file_size}</p>
          </div>
          <a 
            href="${item.download_url}" 
            download="${escapeHtml(item.filename)}"
            class="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs flex items-center gap-1 shadow-sm shrink-0"
          >
            <i data-lucide="download" class="w-3 h-3"></i>
            <span>Save</span>
          </a>
        </div>
      `;
    });

    html += `</div></div>`;
    statusBox.className = "p-3.5 rounded-2xl text-xs bg-dark-surface/90 border border-emerald-500/40 text-slate-200";
    statusBox.innerHTML = html;
    safeCreateIcons();

    if (typeof loadDownloadsHistory === "function") {
      loadDownloadsHistory();
    }

  } catch (err) {
    statusBox.className = "p-3.5 rounded-2xl text-xs bg-rose-950/40 border border-rose-500/40 text-rose-200";
    statusBox.innerHTML = `<p class="font-bold">❌ Error: ${escapeHtml(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    safeCreateIcons();
  }
}

async function executeFileConversion() {
  const btn = document.getElementById("startConvertBtn");
  const statusBox = document.getElementById("converterStatusBox");
  const targetFormat = document.querySelector('input[name="convTargetFormat"]:checked')?.value || "azw3";
  const splitSelect = document.getElementById("convSplitSelect")?.value || "none";

  let splitMode = null;
  let splitValue = 0;
  if (splitSelect.startsWith("parts_")) {
    splitMode = "parts";
    splitValue = parseInt(splitSelect.replace("parts_", ""), 10);
  } else if (splitSelect.startsWith("pages_")) {
    splitMode = "pages";
    splitValue = parseInt(splitSelect.replace("pages_", ""), 10);
  }

  if (converterSelectedFiles.length === 0 && !converterSelectedFileId) {
    statusBox.className = "p-3.5 rounded-2xl text-xs bg-rose-950/40 border border-rose-500/40 text-rose-200";
    statusBox.innerHTML = "<p class='font-bold'>Please select or drop at least one file to convert first!</p>";
    statusBox.classList.remove("hidden");
    return;
  }

  btn.disabled = true;
  safeCreateIcons();

  statusBox.className = "p-3.5 rounded-2xl text-xs bg-purple-950/40 border border-purple-500/40 text-purple-200";
  statusBox.classList.remove("hidden");

  try {
    const convertedItems = [];

    if (converterSelectedFiles.length > 0) {
      const totalFiles = converterSelectedFiles.length;

      for (let i = 0; i < totalFiles; i++) {
        const file = converterSelectedFiles[i];
        const currentNum = i + 1;
        const progressPct = Math.round(((i) / totalFiles) * 100);

        btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>${splitMode ? "Splitting" : "Converting"} (${currentNum}/${totalFiles})...</span>`;
        statusBox.innerHTML = `
          <div class="space-y-2">
            <div class="flex justify-between items-center text-xs font-bold text-purple-300">
              <span class="truncate">${splitMode ? "Splitting" : "Converting"} (${currentNum}/${totalFiles}): ${escapeHtml(file.name)}...</span>
              <span class="font-mono">${progressPct}%</span>
            </div>
            <div class="w-full bg-dark-surface rounded-full h-2 overflow-hidden border border-purple-500/30">
              <div class="bg-gradient-to-r from-purple-500 to-brand-accent h-full transition-all duration-300 rounded-full" style="width: ${progressPct}%"></div>
            </div>
          </div>
        `;
        safeCreateIcons();

        const formData = new FormData();
        formData.append("file", file);
        formData.append("target_format", targetFormat);

        const res = await fetch("/api/convert/upload", {
          method: "POST",
          body: formData
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || `Conversion failed for ${file.name}.`);
        }

        if (splitMode) {
          // Now split this converted file into the requested volume parts
          const splitRes = await fetch("/api/convert/split", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              file_id: data.file_id,
              target_format: targetFormat,
              split_mode: splitMode,
              split_value: splitValue
            })
          });
          const splitData = await splitRes.json();
          if (splitRes.ok && splitData.items) {
            convertedItems.push(...splitData.items);
          } else {
            convertedItems.push(data);
          }
        } else {
          convertedItems.push(data);
        }
      }

    } else if (converterSelectedFileId) {
      btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>${splitMode ? "Splitting" : "Converting"}...</span>`;
      statusBox.innerHTML = `
        <div class="flex items-center gap-2">
          <i data-lucide="loader-2" class="w-4 h-4 animate-spin text-purple-400"></i>
          <span class="font-bold">${splitMode ? "Splitting into volumes" : "Converting file"} to ${targetFormat.toUpperCase()}...</span>
        </div>
      `;
      safeCreateIcons();

      if (splitMode) {
        const res = await fetch("/api/convert/split", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            file_id: converterSelectedFileId,
            target_format: targetFormat,
            split_mode: splitMode,
            split_value: splitValue
          })
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Splitting failed.");
        }
        if (data.items) {
          convertedItems.push(...data.items);
        }
      } else {
        const res = await fetch("/api/convert/existing", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            file_id: converterSelectedFileId,
            target_format: targetFormat
          })
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Conversion failed.");
        }
        convertedItems.push(data);
      }
    }

    // Done Converting!
    if (convertedItems.length > 1) {
      let zipBundle = null;
      try {
        const fileIds = convertedItems.map(c => c.file_id);
        const zipRes = await fetch("/api/convert/bundle-zip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            file_ids: fileIds,
            zip_name: `Batch_Converted_${targetFormat.toUpperCase()}s_${Date.now()}.zip`
          })
        });
        if (zipRes.ok) {
          zipBundle = await zipRes.json();
        }
      } catch (e) {
        console.error("ZIP bundle error:", e);
      }

      let html = `
        <div class="space-y-3">
          <div class="flex items-center gap-2 text-emerald-300 font-bold text-sm">
            <i data-lucide="check-circle" class="w-5 h-5 text-emerald-400"></i>
            <span>Successfully Converted All ${convertedItems.length} Files to ${targetFormat.toUpperCase()}!</span>
          </div>
      `;

      if (zipBundle) {
        html += `
          <a 
            href="${zipBundle.download_url}" 
            download="${escapeHtml(zipBundle.filename)}"
            class="w-full py-3 px-4 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-extrabold text-xs flex items-center justify-center gap-2 transition-all shadow-md active:scale-95"
          >
            <i data-lucide="archive" class="w-4 h-4"></i>
            <span>📦 Download All ${convertedItems.length} Files as ZIP (${zipBundle.file_size})</span>
          </a>
        `;
      }

      html += `<div class="max-h-48 overflow-y-auto space-y-1.5 pr-1">`;
      for (const item of convertedItems) {
        html += `
          <div class="p-2 rounded-xl bg-dark-surface border border-dark-border flex items-center justify-between gap-2 text-xs">
            <span class="truncate font-semibold text-white">${escapeHtml(item.filename)}</span>
            <a 
              href="${item.download_url}" 
              download="${escapeHtml(item.filename)}" 
              class="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 font-bold hover:bg-emerald-500/30 text-[11px] shrink-0"
            >
              ⬇️ Save (${item.file_size})
            </a>
          </div>
        `;
      }
      html += `</div></div>`;

      statusBox.className = "p-4 rounded-2xl text-xs space-y-3 bg-emerald-950/40 border border-emerald-500/40 text-emerald-200";
      statusBox.innerHTML = html;

    } else if (convertedItems.length === 1) {
      const data = convertedItems[0];
      statusBox.className = "p-4 rounded-2xl text-xs space-y-3 bg-emerald-950/40 border border-emerald-500/40 text-emerald-200";
      statusBox.innerHTML = `
        <div class="flex items-center gap-2 text-emerald-300 font-bold text-sm">
          <i data-lucide="check-circle" class="w-5 h-5 text-emerald-400"></i>
          <span>Converted Successfully!</span>
        </div>
        <p class="text-xs text-slate-300">File: <strong>${escapeHtml(data.filename)}</strong> (${data.file_size})</p>
        <a 
          href="${data.download_url}" 
          download="${escapeHtml(data.filename)}"
          class="w-full py-2.5 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold text-xs flex items-center justify-center gap-2 transition-all shadow-md active:scale-95"
        >
          <i data-lucide="download" class="w-4 h-4"></i>
          <span>Download ${escapeHtml(data.format)} File (${data.file_size})</span>
        </a>
      `;
    }

    loadDownloadsHistory();
    safeCreateIcons();

    if (typeof confetti === "function") {
      confetti({ particleCount: 60, spread: 70, origin: { y: 0.6 } });
    }

  } catch (err) {
    statusBox.className = "p-3.5 rounded-2xl text-xs space-y-1 bg-rose-950/40 border border-rose-500/40 text-rose-200";
    statusBox.innerHTML = `
      <p class="font-bold text-rose-300">Conversion Error</p>
      <p class="text-[11px]">${escapeHtml(err.message)}</p>
    `;
    statusBox.classList.remove("hidden");
    safeCreateIcons();
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play" class="w-4 h-4"></i><span>Convert File Now</span>`;
    safeCreateIcons();
  }
}

let currentKindleFileId = null;
let currentKindleFilename = "";

function openKindleModalFromProgress() {
  if (activeCompletedTask) {
    openOpenMTPModal();
  }
}

async function splitFileForKindle() {
  const btn = document.getElementById("splitKindleBtn");
  const statusBox = document.getElementById("kindleStatusBox");

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Starting Kindle Splitting...</span>`;
  safeCreateIcons();

  statusBox.className = "p-3.5 rounded-xl text-xs space-y-2 bg-amber-950/40 border border-amber-500/40 text-amber-200";
  statusBox.innerHTML = `
    <div class="space-y-2">
      <div class="flex items-center justify-between font-semibold text-amber-300">
        <span id="splitStatusText">Initializing splitting engine...</span>
        <span id="splitPercentText" class="font-mono">0%</span>
      </div>
      <div class="w-full bg-dark-surface rounded-full h-2.5 overflow-hidden border border-amber-500/30">
        <div id="splitBarFill" class="bg-gradient-to-r from-amber-500 to-amber-300 h-full w-0 transition-all duration-200 rounded-full"></div>
      </div>
      <div class="flex items-center justify-between text-[11px] text-amber-300/80 font-mono">
        <span id="splitPagesText">0 / 0 pages</span>
        <span id="splitPhaseText">Preparing...</span>
      </div>
    </div>
  `;
  statusBox.classList.remove("hidden");

  try {
    const res = await fetch("/api/kindle/split/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: currentKindleFileId })
    });

    const { task_id } = await res.json();
    if (!res.ok) throw new Error("Failed to start volume splitting.");

    const evtSource = new EventSource(`/api/tasks/${task_id}/progress`);

    evtSource.onmessage = (event) => {
      try {
        const task = JSON.parse(event.data);
        const pct = Math.min(100, Math.max(0, task.progress_percent || 0));

        const barFill = document.getElementById("splitBarFill");
        const pctText = document.getElementById("splitPercentText");
        const statusText = document.getElementById("splitStatusText");
        const pagesText = document.getElementById("splitPagesText");
        const phaseText = document.getElementById("splitPhaseText");

        if (barFill) barFill.style.width = `${pct}%`;
        if (pctText) pctText.textContent = `${Math.round(pct)}%`;
        if (statusText && task.message) statusText.textContent = task.message;
        if (pagesText && task.total_pages_overall > 0) {
          pagesText.textContent = `${task.total_pages_downloaded} / ${task.total_pages_overall} pages`;
        }
        if (phaseText && task.current_chapter) {
          phaseText.textContent = task.current_chapter;
        }

        if (task.status === "completed") {
          evtSource.close();
          btn.disabled = false;
          btn.innerHTML = `<i data-lucide="scissors" class="w-4 h-4 text-amber-400"></i><span>⚡ Auto-Split & Compress into Kindle Volumes (<45MB)</span>`;

          const volumes = task.extra?.volumes || [];
          let volHtml = `<p class="font-bold text-amber-300 flex items-center gap-1.5"><i data-lucide="check-circle" class="w-4 h-4 text-emerald-400"></i> Split Complete! ${volumes.length} Kindle Volumes Created (<45MB each)</p>`;
          volHtml += `<div class="space-y-1.5 pt-1 max-h-48 overflow-y-auto pr-1">`;
          volumes.forEach(vol => {
            volHtml += `
              <div class="flex items-center justify-between p-2 rounded-lg bg-dark-surface border border-dark-border gap-2">
                <span class="font-bold text-white text-[11px] truncate">${escapeHtml(vol.filename)} (${vol.file_size})</span>
                <a href="${vol.download_url}" download class="px-2.5 py-1 rounded bg-amber-500 hover:bg-amber-400 text-black font-extrabold text-[10px] shrink-0">
                  Download Part ${vol.part_number}
                </a>
              </div>
            `;
          });
          volHtml += `</div>`;

          statusBox.innerHTML = volHtml;
          loadDownloadsHistory();
          safeCreateIcons();

        } else if (task.status === "error") {
          evtSource.close();
          btn.disabled = false;
          btn.innerHTML = `<i data-lucide="scissors" class="w-4 h-4 text-amber-400"></i><span>⚡ Auto-Split & Compress into Kindle Volumes (<45MB)</span>`;
          statusBox.className = "p-3.5 rounded-xl text-xs space-y-1 bg-rose-950/40 border border-rose-500/40 text-rose-200";
          statusBox.innerHTML = `<p class="font-bold text-rose-300">Split Error</p><p class="text-[11px]">${escapeHtml(task.error_message || task.message)}</p>`;
        }
      } catch (e) {
        console.error("Split SSE error:", e);
      }
    };

  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="scissors" class="w-4 h-4 text-amber-400"></i><span>⚡ Auto-Split & Compress into Kindle Volumes (<45MB)</span>`;
    statusBox.className = "p-3.5 rounded-xl text-xs space-y-1 bg-rose-950/40 border border-rose-500/40 text-rose-200";
    statusBox.innerHTML = `<p class="font-bold text-rose-300">Split Error</p><p class="text-[11px]">${escapeHtml(err.message)}</p>`;
    statusBox.classList.remove("hidden");
  }
}

async function cancelActiveTask() {
  if (activeTaskId) {
    try {
      await fetch(`/api/tasks/${activeTaskId}/cancel`, { method: "POST" });
    } catch (e) {
      console.error("Cancel task error:", e);
    }
  }
  if (activeEventSource) {
    activeEventSource.close();
  }
  progressModal.classList.add("hidden");
}

// History Management
async function loadDownloadsHistory() {
  try {
    const res = await fetch("/api/history");
    if (!res.ok) return;
    const history = await res.json();

    if (history.length > 0) {
      historyBadge.textContent = history.length;
      historyBadge.classList.remove("hidden");
    } else {
      historyBadge.classList.add("hidden");
    }

    if (history.length === 0) {
      historyListContainer.innerHTML = `
        <div class="py-12 text-center text-slate-500 space-y-2">
          <i data-lucide="archive" class="w-8 h-8 mx-auto stroke-1 text-slate-600"></i>
          <p class="text-xs">No downloads in this session yet.</p>
        </div>
      `;
    } else {
      historyListContainer.innerHTML = history.map(item => `
        <div class="p-4 rounded-2xl bg-dark-surface border border-dark-border space-y-2 hover:border-brand-500/40 transition-colors">
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="text-sm font-bold text-white leading-snug">${escapeHtml(item.manga_title)}</p>
              <p class="text-xs text-slate-400 font-mono">${escapeHtml(item.chapter_range)}</p>
            </div>
            <span class="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase bg-brand-500/20 text-brand-300 border border-brand-500/30">
              ${item.format}
            </span>
          </div>

          <div class="flex items-center justify-between pt-1 border-t border-dark-border/50 text-xs">
            <span class="text-slate-500 font-mono">${item.file_size}</span>
            <div class="flex items-center gap-3">
              <button 
                onclick="openConverterModal('${item.file_id}', '${escapeHtml(item.filename)}')" 
                class="flex items-center gap-1 text-purple-400 hover:text-purple-300 font-semibold transition-colors"
                title="Convert Format"
              >
                <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
                <span>Convert</span>
              </button>
              <button 
                onclick="openOpenMTPModal()" 
                class="flex items-center gap-1 text-amber-400 hover:text-amber-300 font-semibold transition-colors"
                title="Transfer to Kindle via OpenMTP"
              >
                <i data-lucide="usb" class="w-3.5 h-3.5"></i>
                <span>OpenMTP</span>
              </button>
              <a 
                href="${item.download_url}" 
                download="${escapeHtml(item.filename)}"
                class="flex items-center gap-1 text-brand-400 hover:text-brand-300 font-semibold transition-colors"
              >
                <i data-lucide="download" class="w-3.5 h-3.5"></i>
                <span>Save</span>
              </a>
            </div>
          </div>
        </div>
      `).join("");
    }

    safeCreateIcons();
  } catch (e) {
    console.error("History load error:", e);
  }
}

function toggleHistoryDrawer() {
  const isHidden = historyDrawer.classList.contains("translate-x-full");
  if (isHidden) {
    loadDownloadsHistory();
    historyDrawer.classList.remove("translate-x-full");
  } else {
    historyDrawer.classList.add("translate-x-full");
  }
}

async function clearHistory() {
  try {
    await fetch("/api/history/clear", { method: "POST" });
    loadDownloadsHistory();
  } catch (e) {
    console.error("Clear history error:", e);
  }
}

// Helpers
function showError(title, msg) {
  errorTitle.textContent = title;
  errorMessage.textContent = msg;
  errorAlert.classList.remove("hidden");
  errorAlert.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideError() {
  errorAlert.classList.add("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Standalone Kindle File Upload & Drag & Drop
function triggerKindleUploadPicker() {
  const input = document.getElementById("standaloneFileInput");
  if (input) input.click();
}

function handleStandaloneFileUpload(event) {
  const file = event.target.files[0];
  if (file) {
    uploadFileToKindle(file);
  }
}

async function uploadFileToKindle(file) {
  progressModalTitle.textContent = "Uploading File to MangaDrop...";
  progressModalMsg.textContent = `Uploading ${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)...`;
  progressBarFill.style.width = "50%";
  progressPercentDetail.textContent = "50%";
  progressPageDetail.textContent = file.name;
  progressCurrentChapter.textContent = "Uploading...";
  progressIcon.setAttribute("data-lucide", "upload-cloud");
  progressIcon.classList.add("animate-spin");
  cancelTaskBtn.classList.remove("hidden");
  downloadCompletedBtn.classList.add("hidden");
  const kindleBtn = document.getElementById("kindleDirectBtn");
  if (kindleBtn) kindleBtn.classList.add("hidden");

  progressModal.classList.remove("hidden");
  safeCreateIcons();

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/kindle/upload", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const cType = res.headers.get("content-type");
      if (cType && cType.includes("application/json")) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to upload file.");
      } else {
        const text = await res.text();
        throw new Error(`Upload failed (${res.status}): ` + (text.slice(0, 100) || "Server error"));
      }
    }

    const data = await res.json();

    closeProgressModal();
    loadDownloadsHistory();
    openKindleModal(data.file_id, data.filename);

  } catch (err) {
    progressModalTitle.textContent = "Upload Error";
    progressModalMsg.textContent = err.message;
    progressIcon.setAttribute("data-lucide", "alert-octagon");
    progressIcon.classList.remove("animate-spin");
    progressIcon.classList.add("text-rose-400");
    cancelTaskBtn.textContent = "Close";
    cancelTaskBtn.classList.remove("hidden");
    safeCreateIcons();
  }
}

// Drag & Drop setup on Dropzone
document.addEventListener("DOMContentLoaded", () => {
  const dropzone = document.getElementById("kindleUploadDropzone");
  if (dropzone) {
    ["dragenter", "dragover"].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add("border-amber-400", "bg-amber-500/10");
      }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove("border-amber-400", "bg-amber-500/10");
      }, false);
    });

    dropzone.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        uploadFileToKindle(files[0]);
      }
    });
  }

  const convDropzone = document.getElementById("converterDropZone");
  if (convDropzone) {
    ["dragenter", "dragover"].forEach(eventName => {
      convDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        convDropzone.classList.add("border-purple-400", "bg-purple-500/10");
      }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
      convDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        convDropzone.classList.remove("border-purple-400", "bg-purple-500/10");
      }, false);
    });

    convDropzone.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        handleConverterFileSelected({ target: { files: files } });
      }
    });
  }
});

// OpenMTP Kindle Transfer Modal
function openOpenMTPModal() {
  const modal = document.getElementById("openMtpModal");
  if (modal) {
    modal.classList.remove("hidden");
    safeCreateIcons();
  }
}

function closeOpenMTPModal() {
  const modal = document.getElementById("openMtpModal");
  if (modal) modal.classList.add("hidden");
}

function copyDownloadsPath() {
  const path = "~/Desktop/manga/downloads";
  if (navigator.clipboard) {
    navigator.clipboard.writeText(path).then(() => {
      const btn = document.getElementById("copyPathBtn");
      if (btn) {
        const orig = btn.textContent;
        btn.textContent = "Copied! ✓";
        btn.classList.add("bg-amber-300", "text-black");
        setTimeout(() => {
          btn.textContent = orig;
          btn.classList.remove("bg-amber-300", "text-black");
        }, 2000);
      }
    });
  }
}

// Global Shortcuts
// Note: Modals now close ONLY when clicking the explicit Cross (X) or Close button

// Auto-Update & Live Reload Detection
let currentAppBuildId = null;

async function initAutoUpdateCheck() {
  try {
    const res = await fetch("/api/version", { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      currentAppBuildId = data.build_id;
    }
  } catch (e) {}

  setInterval(async () => {
    try {
      const res = await fetch("/api/version", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();

      if (currentAppBuildId && data.build_id && data.build_id !== currentAppBuildId) {
        // Safe check: Only auto-reload if no download task is actively running
        if (!activeTaskId && progressModal.classList.contains("hidden")) {
          console.log("⚡ New MangaDrop update detected! Auto-refreshing...");
          window.location.reload();
        }
      } else if (!currentAppBuildId) {
        currentAppBuildId = data.build_id;
      }
    } catch (e) {}
  }, 5000);
}

// Initial Load
loadDownloadsHistory();
initAutoUpdateCheck();
