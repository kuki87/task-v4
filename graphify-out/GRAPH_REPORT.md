# Graph Report - .  (2026-06-07)

## Corpus Check
- 26 files · ~7,200 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 226 nodes · 538 edges · 15 communities (14 shown, 1 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 89 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Core Data Access Layer|Core Data Access Layer]]
- [[_COMMUNITY_Item & Pricing Model|Item & Pricing Model]]
- [[_COMMUNITY_App State & Shift Logic|App State & Shift Logic]]
- [[_COMMUNITY_Article & Device Services|Article & Device Services]]
- [[_COMMUNITY_Session Start Dialog|Session Start Dialog]]
- [[_COMMUNITY_Admin Panel UI|Admin Panel UI]]
- [[_COMMUNITY_Session State Model|Session State Model]]
- [[_COMMUNITY_Graphify Configuration|Graphify Configuration]]
- [[_COMMUNITY_Package Init Files|Package Init Files]]
- [[_COMMUNITY_Claude Dev Settings|Claude Dev Settings]]

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 45 edges
2. `Artikal` - 32 edges
3. `SessionState` - 31 edges
4. `AdminPanel` - 24 edges
5. `GlavniProzor` - 23 edges
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
- `Artikal` --uses--> `BocniPanel`  [INFERRED]
  models/artikal.py → ui/bocni_panel.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Device Session Billing Flow** — ui_kartica_uredjaja_UredjajKontroler, models_session_state_SessionState, services_pazar_naplati_uredjaj, services_pazar_izracunaj_iznos_sesije, ui_dijalog_start_IzborStartaDijalog [INFERRED 0.92]
- **Admin Authentication Flow** — ui_admin_panel_AdminPanel, services_auth_provjeri_admin_lozinku, services_auth_promijeni_lozinku, services_auth_hash_lozinke, constants_ADMIN_DEFAULT_LOZINKA [EXTRACTED 1.00]
- **Shift (Smjena) Lifecycle Flow** — services_smjena_otvori_smjenu, services_smjena_zatvori_smjenu, services_smjena_prenesi_u_novu_smjenu, ui_glavni_prozor_GlavniProzor, models_app_state_AppState [INFERRED 0.90]

## Communities (15 total, 1 thin omitted)

### Community 0 - "Core Data Access Layer"
Cohesion: 0.11
Nodes (24): DB_PATH Constant, get_db(), inicijalizuj_bazu(), Connection, kreiraj_tabele(), pokreni_migracije(), Connection, Application Entry Point (+16 more)

### Community 1 - "Item & Pricing Model"
Cohesion: 0.13
Nodes (32): Pricing & Pass Constants, UI Color Constants, Artikal Dataclass, Artikal, float, str, SessionState Dataclass, SessionState (+24 more)

### Community 2 - "App State & Shift Logic"
Cohesion: 0.09
Nodes (13): AppState, bool, int, str, BocniPanel, Artikal, float, str (+5 more)

### Community 3 - "Article & Device Services"
Cohesion: 0.12
Nodes (23): Admin Default Password Constant, brisi_artikal(), dodaj_artikal(), float, int, str, ucitaj_artikle(), uredi_artikal() (+15 more)

### Community 4 - "Session Start Dialog"
Cohesion: 0.13
Nodes (8): IzborStartaDijalog, float, str, _DijalogIzbora, Artikal, float, str, UredjajKontroler

### Community 5 - "Admin Panel UI"
Cohesion: 0.16
Nodes (6): bool, AdminPanel, bool, float, int, str

### Community 6 - "Session State Model"
Cohesion: 0.24
Nodes (4): bool, float, int, str

### Community 7 - "Graphify Configuration"
Cohesion: 0.25
Nodes (8): graphify query Command, Graphify Usage Rules, graphify update Command, GRAPH_REPORT.md Broad Architecture Review, graphify-out/wiki/index.md Navigation, Bash Tool PreToolUse Hook, Claude Settings / PreToolUse Hooks, Graphify Knowledge Graph Hint (Hook Context)

### Community 8 - "Package Init Files"
Cohesion: 0.67
Nodes (4): Database Package Init, Models Package Init, Services Package Init, UI Package Init

## Knowledge Gaps
- **23 isolated node(s):** `PreToolUse`, `Connection`, `int`, `str`, `bool` (+18 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Core Data Access Layer` to `Item & Pricing Model`, `App State & Shift Logic`, `Article & Device Services`, `Session Start Dialog`, `Admin Panel UI`?**
  _High betweenness centrality (0.275) - this node is a cross-community bridge._
- **Why does `SessionState` connect `Item & Pricing Model` to `Core Data Access Layer`, `App State & Shift Logic`, `Session Start Dialog`, `Session State Model`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Why does `Artikal` connect `Item & Pricing Model` to `Core Data Access Layer`, `App State & Shift Logic`, `Session Start Dialog`?**
  _High betweenness centrality (0.114) - this node is a cross-community bridge._
- **Are the 24 inferred relationships involving `Artikal` (e.g. with `Artikal` and `float`) actually correct?**
  _`Artikal` has 24 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `SessionState` (e.g. with `Artikal` and `float`) actually correct?**
  _`SessionState` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `AdminPanel` (e.g. with `_DijalogSmjena` and `GlavniProzor`) actually correct?**
  _`AdminPanel` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `GlavniProzor` (e.g. with `AppState` and `Artikal`) actually correct?**
  _`GlavniProzor` has 7 INFERRED edges - model-reasoned connections that need verification._