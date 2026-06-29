"""
ETAPE 3a — ADDITIVE FILTRE. Intet valg låser et andet.

Kernen: 'currentFilter' (en enkelt streng) erstattes af 'activeFlags'
(et Set). Så Tilbud + Alkoholfri + Smagekasser kan kombineres frit, og
stilart-valg rører dem ikke. Favoritter forbliver et selvstændigt flag.

Berørte funktioner: state, quickCat, filterAndSortBeers, renderActiveFilters,
clearFilter, sidebar-filter-knapper, loadPrefs/savePrefs, resetAllFilters.

Kør:  python patch_etape3a_filtre.py
Backup: index.html.bak3a
"""
import io, shutil

FILE = "index.html"
shutil.copy(FILE, FILE + ".bak3a")
s = io.open(FILE, encoding="utf-8").read()
ok = True

def patch(old, new, navn):
    global s, ok
    n = s.count(old)
    if n == 0:
        print(f"  [SPRINGER OVER] {navn} — fandt ikke teksten")
        ok = False
    elif n > 1:
        print(f"  [ADVARSEL] {navn} — findes {n} gange (ikke unik)")
        ok = False
    else:
        s = s.replace(old, new)
        print(f"  [OK] {navn}")

# ── 1. State: currentFilter -> activeFlags (Set) ──────────────────────
patch(
    "    let currentFilter = 'all', currentSort = 'price-asc';",
    "    let activeFlags = new Set(); let currentSort = 'price-asc';",
    "State: activeFlags Set"
)

# ── 2. quickCat: additiv toggle ───────────────────────────────────────
gammel_quickcat = """    function quickCat(cat) {
        const btn = document.querySelector(`.cat-btn[data-cat="${cat}"]`);

        if (cat === 'deals') {
            selectedTypes.clear();
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            currentFilter = 'deals';
            currentSort = 'discount';
            document.getElementById('sort-select').value = 'discount';
            document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b =>
                b.classList.toggle('active', b.dataset.filter === 'deals')
            );
            updateTypeBtn();

        } else if (cat === 'smagekasse') {
            selectedTypes.clear();
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            currentFilter = 'smagekasse';
            document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b =>
                b.classList.toggle('active', b.dataset.filter === 'smagekasse')
            );
            updateTypeBtn();

        } else {
            currentFilter = 'all';
            document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b =>
                b.classList.toggle('active', b.dataset.filter === 'all')
            );

            if (selectedTypes.has(cat)) {
                selectedTypes.delete(cat);
                if (btn) btn.classList.remove('active');
            } else {
                selectedTypes.add(cat);
                if (btn) btn.classList.add('active');
                document.querySelectorAll('.cat-btn[data-cat="deals"], .cat-btn[data-cat="smagekasse"]').forEach(b =>
                    b.classList.remove('active')
                );
            }
            updateTypeBtn();
        }

        currentPage = 1;
        savePrefs();
        renderGrid();
        renderActiveFilters();
        gtag('event', 'kategori_genvej', { kategori: cat });
        window.scrollTo({ top: document.querySelector('.grid-wrap').offsetTop - 60, behavior: 'smooth' });
    }"""

ny_quickcat = """    // ADDITIV: hver pill toggler uafhængigt. Flag (deals/smagekasse) og
    // stilarter kan kombineres frit — intet rydder noget andet.
    const FLAG_CATS = { 'deals': 'deals', 'smagekasse': 'smagekasse' };

    function quickCat(cat) {
        const btn = document.querySelector(`.cat-btn[data-cat="${cat}"]`);

        if (FLAG_CATS[cat]) {
            const flag = FLAG_CATS[cat];
            if (activeFlags.has(flag)) {
                activeFlags.delete(flag);
                if (btn) btn.classList.remove('active');
            } else {
                activeFlags.add(flag);
                if (btn) btn.classList.add('active');
                if (flag === 'deals') { currentSort = 'discount'; document.getElementById('sort-select').value = 'discount'; }
            }
            syncFlagButtons();
        } else {
            if (selectedTypes.has(cat)) {
                selectedTypes.delete(cat);
                if (btn) btn.classList.remove('active');
            } else {
                selectedTypes.add(cat);
                if (btn) btn.classList.add('active');
            }
            updateTypeBtn();
        }

        currentPage = 1;
        savePrefs();
        renderGrid();
        renderActiveFilters();
        gtag('event', 'kategori_genvej', { kategori: cat });
        window.scrollTo({ top: document.querySelector('.grid-wrap').offsetTop - 60, behavior: 'smooth' });
    }

    // Holder pills og sidebar-knapper synkroniserede med activeFlags
    function syncFlagButtons() {
        document.querySelectorAll('.cat-btn[data-cat]').forEach(b => {
            const c = b.dataset.cat;
            if (FLAG_CATS[c]) b.classList.toggle('active', activeFlags.has(FLAG_CATS[c]));
        });
        document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b => {
            const f = b.dataset.filter;
            if (f === 'all') b.classList.toggle('active', activeFlags.size === 0);
            else b.classList.toggle('active', activeFlags.has(f));
        });
    }"""

patch(gammel_quickcat, ny_quickcat, "quickCat additiv")

# ── 3. filterAndSortBeers: brug activeFlags ───────────────────────────
gammel_filter = """        filtered = filtered.filter(b => {
            if (currentFilter === 'deals' && (!b.max_discount_pct || b.max_discount_pct === 0)) return false;
            if (currentFilter === 'alcohol-free' && !isAlcoholFree(b)) return false;
            if (currentFilter === 'smagekasse' && !isSmagekasse(b)) return false;
            if (currentFilter === 'favs' && !favorites.has(b.normalized_name || b.name)) return false;
            return true;
        });"""

ny_filter = """        filtered = filtered.filter(b => {
            // ADDITIVE flag — alle aktive flag skal være opfyldt samtidig
            if (activeFlags.has('deals') && (!b.max_discount_pct || b.max_discount_pct === 0)) return false;
            if (activeFlags.has('alcohol-free') && !isAlcoholFree(b)) return false;
            if (activeFlags.has('smagekasse') && !isSmagekasse(b)) return false;
            if (activeFlags.has('favs') && !favorites.has(b.normalized_name || b.name)) return false;
            return true;
        });"""

patch(gammel_filter, ny_filter, "filterAndSortBeers flag-logik")

# ── 4. Sidebar-filter-knapper: additiv ────────────────────────────────
gammel_sidebar = """        document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b=>b.classList.remove('active'));
                btn.classList.add('active'); currentFilter=btn.dataset.filter; currentPage=1;
                if (currentFilter==='deals') { currentSort='discount'; document.getElementById('sort-select').value='discount'; }
                document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
                savePrefs(); renderGrid(); renderActiveFilters(); gtag('event','filter_klik',{filter:currentFilter});
                if (isMobile()) closeSidebar();
            });
        });"""

ny_sidebar = """        document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(btn => {
            btn.addEventListener('click', () => {
                const f = btn.dataset.filter;
                if (f === 'all') {
                    // "Alle øl" rydder kun flag (ikke stilart/butik/pris)
                    activeFlags.clear();
                } else if (activeFlags.has(f)) {
                    activeFlags.delete(f);
                } else {
                    activeFlags.add(f);
                    if (f === 'deals') { currentSort='discount'; document.getElementById('sort-select').value='discount'; }
                }
                currentPage=1; syncFlagButtons();
                savePrefs(); renderGrid(); renderActiveFilters(); gtag('event','filter_klik',{filter:f});
                if (isMobile()) closeSidebar();
            });
        });"""

patch(gammel_sidebar, ny_sidebar, "Sidebar-filter-knapper additiv")

# ── 5. renderActiveFilters: vis hvert flag som chip ───────────────────
gammel_chips = """        if (currentFilter !== 'all') {
            const labels = { 'deals':'🔥 Tilbud','favs':'❤️ Favoritter','alcohol-free':'🚫 Alkoholfri','smagekasse':'📦 Smagekasser' };
            const l = labels[currentFilter]||currentFilter;
            chips.push(`<span class="filter-chip">${l}<span class="x" onclick="clearFilter('quick')">✕</span></span>`);
            sc.push(`<span class="sidebar-chip" onclick="clearFilter('quick')">${l}<span class="x">✕</span></span>`);
        }"""

ny_chips = """        const flagLabels = { 'deals':'🔥 Tilbud','favs':'❤️ Favoritter','alcohol-free':'🚫 Alkoholfri','smagekasse':'📦 Smagekasser' };
        activeFlags.forEach(f => {
            const l = flagLabels[f] || f;
            chips.push(`<span class="filter-chip">${l}<span class="x" onclick="clearFilter('flag','${f}')">✕</span></span>`);
            sc.push(`<span class="sidebar-chip" onclick="clearFilter('flag','${f}')">${l}<span class="x">✕</span></span>`);
        });"""

patch(gammel_chips, ny_chips, "renderActiveFilters flag-chips")

# ── 6. clearFilter: håndter 'flag' ────────────────────────────────────
gammel_clear = """    window.clearFilter = function(type, value) {
        if (type==='quick') { currentFilter='all'; document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all')); document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active')); }
        else if (type==='shop') { selectedShops.delete(value); updateShopBtn(); }"""

ny_clear = """    window.clearFilter = function(type, value) {
        if (type==='flag') { activeFlags.delete(value); syncFlagButtons(); }
        else if (type==='shop') { selectedShops.delete(value); updateShopBtn(); }"""

patch(gammel_clear, ny_clear, "clearFilter flag-håndtering")

# ── 7. savePrefs/loadPrefs: gem activeFlags ───────────────────────────
patch(
    "        localStorage.setItem('bs_prefs', JSON.stringify({ sort: currentSort, types: [...selectedTypes], shops: [...selectedShops], filter: currentFilter, abvMin, abvMax }));",
    "        localStorage.setItem('bs_prefs', JSON.stringify({ sort: currentSort, types: [...selectedTypes], shops: [...selectedShops], flags: [...activeFlags], abvMin, abvMax }));",
    "savePrefs activeFlags"
)

gammel_loadprefs = """        if (p.abvMin !== undefined) abvMin = p.abvMin;
        if (p.abvMax !== undefined) abvMax = p.abvMax;
        if (p.filter) {
            currentFilter = p.filter;
            document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b =>
                b.classList.toggle('active', b.dataset.filter === p.filter));
        }"""

ny_loadprefs = """        if (p.abvMin !== undefined) abvMin = p.abvMin;
        if (p.abvMax !== undefined) abvMax = p.abvMax;
        if (p.flags) activeFlags = new Set(p.flags);
        syncFlagButtons();
        // Genskab aktive stilart-pills visuelt
        selectedTypes.forEach(t => {
            const b = document.querySelector(`.cat-btn[data-cat="${t}"]`);
            if (b) b.classList.add('active');
        });"""

patch(gammel_loadprefs, ny_loadprefs, "loadPrefs activeFlags")

# ── 8. resetAllFilters: ryd activeFlags ───────────────────────────────
gammel_reset = """        function resetAllFilters() {
            currentFilter='all'; selectedShops.clear(); currentSort='price-asc'; currentPage=1;
            selectedTypes.clear(); priceMin=0; abvMin=0; abvMax=15;"""

ny_reset = """        function resetAllFilters() {
            activeFlags.clear(); selectedShops.clear(); currentSort='price-asc'; currentPage=1;
            selectedTypes.clear(); priceMin=0; abvMin=0; abvMax=15;"""

patch(gammel_reset, ny_reset, "resetAllFilters activeFlags")

gammel_reset2 = """            document.querySelectorAll('.sidebar-filter-btn[data-filter]').forEach(b=>b.classList.remove('active'));
            document.querySelector('.sidebar-filter-btn[data-filter=all]').classList.add('active');
            document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
            savePrefs(); renderGrid(); renderActiveFilters(); gtag('event','nulstil_filter');"""

ny_reset2 = """            document.querySelectorAll('.cat-btn').forEach(b=>b.classList.remove('active'));
            syncFlagButtons();
            savePrefs(); renderGrid(); renderActiveFilters(); gtag('event','nulstil_filter');"""

patch(gammel_reset2, ny_reset2, "resetAllFilters knap-reset")

# ── Gem ───────────────────────────────────────────────────────────────
if ok:
    io.open(FILE, "w", encoding="utf-8").write(s)
    print("\n✅ Etape 3a færdig — filtre er nu additive. Backup: index.html.bak3a")
    print("   Test: vælg flere filtre på én gang (fx IPA + Tilbud) — intet bør låse.")
else:
    print("\n⚠️  En eller flere patches sprunget over — INTET gemt. Filen er urørt.")
    print("   Send outputtet, så justerer jeg de linjer der ikke ramte.")