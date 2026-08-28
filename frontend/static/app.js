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
  lucide.createIcons();

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
  lucide.createIcons();
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
  lucide.createIcons();
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
  lucide.createIcons();
}

// Download Execution & Real-time Progress Tracking
async function triggerDownload() {
  if (!currentManga || selectedChapterIds.size === 0) return;

  const exportFormat = document.querySelector('input[name="exportFormat"]:checked')?.value || "pdf";
  const bundleMode = document.getElementById("bundleMode").value;
  const dataSaver = document.getElementById("dataSaver").value === "true";

  const payload = {
    manga: currentManga,
    selected_chapter_ids: Array.from(selectedChapterIds),
    format: exportFormat,
    bundle_mode: bundleMode,
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
  lucide.createIcons();

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
    lucide.createIcons();
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

    lucide.createIcons();

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

    lucide.createIcons();
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
let currentKindleFileId = null;
let currentKindleFilename = "";

function openKindleModalFromProgress() {
  if (activeCompletedTask) {
    openKindleModal(activeCompletedTask.file_id, activeCompletedTask.filename);
  }
}

function openKindleModal(fileId, filename) {
  currentKindleFileId = fileId;
  currentKindleFilename = filename;
  document.getElementById("kindleModalFilename").textContent = filename;
  
  const savedEmail = localStorage.getItem("kindle_email") || "nit.ratha01_t9Ucaw@kindle.com";
  document.getElementById("kindleEmailInput").value = savedEmail;
  document.getElementById("btnKindleEmailLabel").textContent = savedEmail;

  document.getElementById("kindleStatusBox").classList.add("hidden");
  document.getElementById("kindleModal").classList.remove("hidden");
  lucide.createIcons();
}

function closeKindleModal() {
  document.getElementById("kindleModal").classList.add("hidden");
}

async function sendKindleEmailDirect() {
  const emailInput = document.getElementById("kindleEmailInput");
  const email = emailInput.value.trim() || "nit.ratha01_t9Ucaw@kindle.com";
  localStorage.setItem("kindle_email", email);

  const btn = document.getElementById("sendKindleDirectBtn");
  const statusBox = document.getElementById("kindleStatusBox");

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Sending to Kindle...</span>`;
  lucide.createIcons();

  try {
    const res = await fetch("/api/kindle/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_id: currentKindleFileId,
        kindle_email: email
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Failed to dispatch to Kindle.");
    }

    statusBox.className = "p-3.5 rounded-xl text-xs space-y-1 bg-emerald-950/40 border border-emerald-500/40 text-emerald-200";
    statusBox.innerHTML = `
      <p class="font-bold text-emerald-300 flex items-center gap-1.5"><i data-lucide="check-circle" class="w-4 h-4"></i> ${data.message || 'Ready for Kindle!'}</p>
      <p class="text-[11px] text-emerald-200/90">Sent to ${escapeHtml(email)}. Your Kindle device will automatically download and sync this manga when connected to Wi-Fi!</p>
    `;
    statusBox.classList.remove("hidden");
    lucide.createIcons();

  } catch (err) {
    statusBox.className = "p-3.5 rounded-xl text-xs space-y-1 bg-rose-950/40 border border-rose-500/40 text-rose-200";
    statusBox.innerHTML = `<p class="font-bold text-rose-300">Delivery Notice</p><p class="text-[11px]">${escapeHtml(err.message)}</p>`;
    statusBox.classList.remove("hidden");
    lucide.createIcons();
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="send" class="w-4 h-4"></i><span>Send Directly to <span id="btnKindleEmailLabel" class="font-mono">${escapeHtml(email)}</span></span>`;
    lucide.createIcons();
  }
}

async function splitFileForKindle() {
  const btn = document.getElementById("splitKindleBtn");
  const statusBox = document.getElementById("kindleStatusBox");

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Starting Kindle Splitting...</span>`;
  lucide.createIcons();

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
          lucide.createIcons();

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
                onclick="openKindleModal('${item.file_id}', '${escapeHtml(item.filename)}')" 
                class="flex items-center gap-1 text-amber-400 hover:text-amber-300 font-semibold transition-colors"
                title="Send to Kindle"
              >
                <i data-lucide="tablet" class="w-3.5 h-3.5"></i>
                <span>Kindle</span>
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

    lucide.createIcons();
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
  lucide.createIcons();

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
    lucide.createIcons();
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
});

// Kindle Wi-Fi Wireless Hub
let cachedHubUrl = "";

async function openKindleHubModal() {
  const modal = document.getElementById("kindleHubModal");
  const urlText = document.getElementById("kindleHubUrlText");
  const urlMini = document.getElementById("kindleHubUrlMini");
  const previewBtn = document.getElementById("previewKindleHubBtn");

  try {
    const res = await fetch("/api/network/ip");
    if (res.ok) {
      const data = await res.json();
      cachedHubUrl = data.hub_url;
      if (urlText) urlText.textContent = data.hub_url;
      if (urlMini) urlMini.textContent = data.hub_url;
      if (previewBtn) previewBtn.href = data.hub_url;
    }
  } catch (e) {
    console.error("Network IP lookup error:", e);
  }

  if (modal) {
    modal.classList.remove("hidden");
    lucide.createIcons();
  }
}

function closeKindleHubModal() {
  const modal = document.getElementById("kindleHubModal");
  if (modal) modal.classList.add("hidden");
}

function copyKindleHubUrl() {
  const url = cachedHubUrl || document.getElementById("kindleHubUrlText")?.textContent || "";
  if (url) {
    navigator.clipboard.writeText(url).then(() => {
      const btn = document.getElementById("copyHubUrlBtn");
      if (btn) {
        const orig = btn.textContent;
        btn.textContent = "Copied! ✓";
        btn.classList.add("bg-emerald-300");
        setTimeout(() => {
          btn.textContent = orig;
          btn.classList.remove("bg-emerald-300");
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
