# 📖 MangaDrop — Manga Downloader & Converter

> **Scan, select chapter ranges, and export high-fidelity PDF, EPUB, or CBZ manga books with ease.**

---

## ✨ Features

- 🔗 **Smart URL & Search Bar**:
  - Paste URLs from **MangaDex**, **Manganato / MangaKakalot**, **MangaFreak**, or any other generic manga website.
  - Or simply search by manga title (e.g. *One Piece*, *Solo Leveling*, *Frieren*, *Chainsaw Man*) for instant results.
- 🎯 **Flexible Chapter Selection**:
  - **Numerical Range Selector**: Pick *"From Chapter X to Chapter Y"* with instant sync.
  - **Quick Presets**: `All Chapters`, `First 5`, `First 10`, `Latest 10`, or `Deselect All`.
  - **Interactive Checkbox Table**: Search & filter within chapters, with Shift+Click multi-selection.
- 📦 **Multiple High-Fidelity Export Formats**:
  - **PDF**: Dynamic page aspect ratios matching original artwork, with chapter bookmarks / Table of Contents navigation.
  - **EPUB**: EPUB3 Comic / Fixed-Layout standard compatible with Apple Books, Kindle (Send-to-Kindle), Kobo, and Calibre.
  - **CBZ**: Comic Book Archive with `ComicInfo.xml` metadata for apps like Tachiyomi, Mihon, Panels, and CDisplayEx.
- 📚 **Bundling Options**:
  - *Single Combined Book* (all selected chapters compiled into one file with bookmarks).
  - *Individual Chapter Files (.ZIP)* (each chapter packaged separately inside a ZIP archive).
- ⚡ **Real-Time Progress Streaming**:
  - Live progress modal powered by Server-Sent Events (SSE).
  - Shows current stage, active chapter, downloading page count (e.g. `Page 14/22`), and overall completion percentage.
  - Automatic download trigger and confetti celebration upon completion.
- 🕒 **Downloads History**:
  - Slide-out drawer with one-click re-download for files generated during your session.
- 🎨 **Modern Cyberpunk / Dark Aesthetic**:
  - Responsive dark UI built with Tailwind CSS, Lucide icons, glassmorphism cards, and blurred backdrop cover artwork.

---

## 🚀 Quick Start

### 1. Run the Startup Script

```bash
./run.sh
```

Or manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Open in Browser

Visit: **[http://localhost:8000](http://localhost:8000)**

---

## 🛠️ Project Architecture

```
manga/
├── backend/
│   ├── app.py                  # FastAPI web server and REST API endpoints
│   ├── scrapers/
│   │   ├── base.py             # Abstract scraper and data models (MangaInfo, ChapterInfo, PageInfo)
│   │   ├── mangadex.py         # MangaDex API client (metadata, chapters, high-res at-home server)
│   │   ├── manganato.py        # Manganato & MangaKakalot scraper
│   │   ├── mangafreak.py       # MangaFreak scraper
│   │   └── generic.py          # Intelligent heuristic HTML scraper for generic manga sites
│   ├── converters/
│   │   ├── pdf_builder.py      # Dynamic aspect ratio PDF generator with chapter bookmarks
│   │   ├── epub_builder.py     # EPUB3 Fixed-Layout comic standard with XHTML & OPF manifest
│   │   └── cbz_builder.py      # CBZ packager with ComicInfo.xml metadata
│   ├── services/
│   │   ├── download_manager.py # Async parallel downloader with retry, rate-limiting, and packaging
│   │   └── progress_tracker.py # SSE real-time progress broadcast service
│   └── utils/
│       └── image_utils.py      # Image validation, RGB/Alpha flattening, and format optimization
├── frontend/
│   ├── index.html              # Responsive dark-theme SPA with Tailwind CSS & Lucide icons
│   └── static/
│       ├── app.js              # Frontend state, SSE event listener, range controls, and UI logic
│       └── style.css           # Custom scrollbars, glowing badges, and animations
├── downloads/                  # Output directory for generated PDF/EPUB/CBZ files
├── tests/                      # Pytest unit and integration test suite
├── requirements.txt            # Python dependencies
└── run.sh                      # One-click startup script
```

---

## 🧪 Running Tests

```bash
PYTHONPATH=. ./venv/bin/pytest
```
