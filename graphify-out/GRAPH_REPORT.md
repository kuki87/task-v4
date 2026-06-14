# Graph Report - .  (2026-06-14)

## Corpus Check
- 26 files · ~7,200 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 231 nodes · 549 edges · 17 communities (16 shown, 1 thin omitted)
- Extraction: 84% EXTRACTED · 16% INFERRED · 0% AMBIGUOUS · INFERRED: 90 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Article & Device Services|Article & Device Services]]
- [[_COMMUNITY_Session & Pazar Model|Session & Pazar Model]]
- [[_COMMUNITY_Core Data Access Layer|Core Data Access Layer]]
- [[_COMMUNITY_Session Start Dialog|Session Start Dialog]]
- [[_COMMUNITY_App State & Main Window|App State & Main Window]]
- [[_COMMUNITY_Entry Point & Logger|Entry Point & Logger]]
- [[_COMMUNITY_Side Panel UI|Side Panel UI]]
- [[_COMMUNITY_Admin Auth|Admin Auth]]
- [[_COMMUNITY_Graphify Configuration|Graphify Configuration]]
- [[_COMMUNITY_DB Schema & Init|DB Schema & Init]]
- [[_COMMUNITY_Package Init Files|Package Init Files]]
- [[_COMMUNITY_Claude Dev Settings|Claude Dev Settings]]

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 45 edges
2. `Artikal` - 32 edges
3. `SessionState` - 31 edges
4. `AdminPanel` - 25 edges
5. `GlavniProzor` - 24 edges
6. `BocniPanel` - 19 edges
7. `UredjajKontroler` - 18 edges
8. `IzborStartaDijalog` - 17 edges
9. `GlavniProzor (Main Window)` - 17 edges
10. `naplati_uredjaj()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Graphify Knowledge Graph Hint (Hook Context)` --conceptually_related_to--> `Graphify Usage Rules`  [INFERRED]
  .claude/settings.json → CLAUDE.md
- `Artikal` --uses--> `float`  [INFERRED]
  models/artikal.py → ui/bocni_panel.py
- `Singleton DB Connection Pattern` --semantically_similar_to--> `Singleton AppState Pattern`  [INFERRED] [semantically similar]
  database/db.py → models/app_state.py
- `AppState` --uses--> `GlavniProzor`  [INFERRED]
  models/app_state.py → ui/glavni_prozor.py
- `AppState` --uses--> `int`  [INFERRED]
  models/app_state.py → ui/glavni_prozor.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Device Session Billing Flow** — ui_kartica_uredjaja_UredjajKontroler, models_session_state_SessionState, services_pazar_naplati_uredjaj, services_pazar_izracunaj_iznos_sesije, ui_dijalog_start_IzborStartaDijalog [INFERRED 0.92]
- **Admin Authentication Flow** — ui_admin_panel_AdminPanel, services_auth_provjeri_admin_lozinku, services_auth_promijeni_lozinku, services_auth_hash_lozinke, constants_ADMIN_DEFAULT_LOZINKA [EXTRACTED 1.00]
- **Shift (Smjena) Lifecycle Flow** — services_smjena_otvori_smjenu, services_smjena_zatvori_smjenu, services_smjena_prenesi_u_novu_smjenu, ui_glavni_prozor_GlavniProzor, models_app_state_AppState [INFERRED 0.90]

## Communities (17 total, 1 thin omitted)

### Community 0 - "Article & Device Services"
Cohesion: 0.09
Nodes (22): bool, brisi_artikal(), dodaj_artikal(), float, int, str, ucitaj_artikle(), uredi_artikal() (+14 more)

### Community 1 - "Session & Pazar Model"
Cohesion: 0.13
Nodes (25): Pricing & Pass Constants, UI Color Constants, Artikal Dataclass, SessionState Dataclass, bool, float, int, str (+17 more)

### Community 2 - "Core Data Access Layer"
Cohesion: 0.14
Nodes (27): DB_PATH Constant, get_db(), Connection, Application Entry Point, AppState (Singleton), Artikal, float, str (+19 more)

### Community 3 - "Session Start Dialog"
Cohesion: 0.13
Nodes (8): IzborStartaDijalog, float, str, _DijalogIzbora, Artikal, float, str, UredjajKontroler

### Community 4 - "App State & Main Window"
Cohesion: 0.12
Nodes (9): AppState, bool, int, str, str, _DijalogSmjena, _PrikazIzvjestaja, str (+1 more)

### Community 5 - "Entry Point & Logger"
Cohesion: 0.17
Nodes (5): int, str, upisi_log(), GlavniProzor, int

### Community 6 - "Side Panel UI"
Cohesion: 0.26
Nodes (4): BocniPanel, Artikal, float, str

### Community 7 - "Admin Auth"
Cohesion: 0.40
Nodes (8): Admin Default Password Constant, hash_lozinke(), promijeni_lozinku(), provjeri_admin_lozinku(), provjeri_lozinku(), bool, str, AdminPanel UI

### Community 8 - "Graphify Configuration"
Cohesion: 0.25
Nodes (8): graphify query Command, Graphify Usage Rules, graphify update Command, GRAPH_REPORT.md Broad Architecture Review, graphify-out/wiki/index.md Navigation, Bash Tool PreToolUse Hook, Claude Settings / PreToolUse Hooks, Graphify Knowledge Graph Hint (Hook Context)

### Community 9 - "DB Schema & Init"
Cohesion: 0.52
Nodes (5): Connection, inicijalizuj_bazu(), kreiraj_tabele(), pokreni_migracije(), Connection

### Community 10 - "Package Init Files"
Cohesion: 0.67
Nodes (4): Database Package Init, Models Package Init, Services Package Init, UI Package Init

## Knowledge Gaps
- **24 isolated node(s):** `PreToolUse`, `Connection`, `int`, `str`, `bool` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Core Data Access Layer` to `Article & Device Services`, `Session & Pazar Model`, `Session Start Dialog`, `Entry Point & Logger`, `Side Panel UI`, `Admin Auth`, `DB Schema & Init`?**
  _High betweenness centrality (0.270) - this node is a cross-community bridge._
- **Why does `SessionState` connect `Session & Pazar Model` to `Core Data Access Layer`, `Session Start Dialog`, `App State & Main Window`, `Entry Point & Logger`?**
  _High betweenness centrality (0.118) - this node is a cross-community bridge._
- **Why does `AdminPanel` connect `Article & Device Services` to `Core Data Access Layer`, `App State & Main Window`, `Entry Point & Logger`, `Admin Auth`?**
  _High betweenness centrality (0.116) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `Artikal` (e.g. with `Artikal` and `float`) actually correct?**
  _`Artikal` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `SessionState` (e.g. with `Artikal` and `float`) actually correct?**
  _`SessionState` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `AdminPanel` (e.g. with `_DijalogSmjena` and `GlavniProzor`) actually correct?**
  _`AdminPanel` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `GlavniProzor` (e.g. with `AppState` and `Artikal`) actually correct?**
  _`GlavniProzor` has 7 INFERRED edges - model-reasoned connections that need verification._