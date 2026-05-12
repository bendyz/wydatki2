// ==================== STATE ====================
const API_URL = "/api/v1";
const EXPENSES_PER_PAGE = 50;
let currentDraft = null;
let currentReceiptFile = null;
let categoriesCache = [];
let currentEditingExpenseId = null;
let currentExpenses = [];
let currentExpensesOffset = 0;
let currentUser = null;
let _monthCategoryCache = {};
let _categoryExpenseCache = {};
let _tempResetToken = null;
let _modalDirty = false;

// ==================== AUTH ====================
function getToken() {
    return localStorage.getItem("token");
}
function setToken(token) {
    localStorage.setItem("token", token);
}
function isLoggedIn() {
    return !!getToken();
}
function logout() {
    localStorage.removeItem("token");
    currentUser = null;
    showView("login");
    document.getElementById("navbar").classList.add("hidden");
    document.getElementById("nav-admin-btn").classList.add("hidden");
    document.getElementById("nav-admin-btn-mobile").classList.add("hidden");
}
function toggleAuthMode() {
    document.getElementById("login-form").classList.toggle("hidden");
    document.getElementById("register-form").classList.toggle("hidden");
    document.getElementById("auth-error").classList.add("hidden");
}

async function apiRequest(method, endpoint, body = null, isForm = false) {
    const headers = {};
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (!isForm && body) headers["Content-Type"] = "application/json";

    const options = { method, headers };
    if (body) options.body = isForm ? body : JSON.stringify(body);

    const response = await fetch(`${API_URL}${endpoint}`, options);
    if (response.status === 401) {
        logout();
        throw new Error("Sesja wygasła. Zaloguj się ponownie.");
    }
    if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Błąd serwera" }));
        throw new Error(err.detail || "Błąd serwera");
    }
    if (response.status === 204) return null;
    return response.json();
}

async function login() {
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    try {
        const formData = new URLSearchParams();
        formData.append("username", email);
        formData.append("password", password);
        const response = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData,
        });
        if (!response.ok) throw new Error("Nieprawidłowy email lub hasło");
        const data = await response.json();
        if (data.password_reset_required) {
            _tempResetToken = data.temp_token;
            document.getElementById("login-form").classList.add("hidden");
            document.getElementById("register-form").classList.add("hidden");
            document.getElementById("set-password-form").classList.remove("hidden");
            document.getElementById("auth-error").classList.add("hidden");
            return;
        }
        setToken(data.access_token);
        initApp();
    } catch (e) {
        showError(e.message);
    }
}

async function setNewPassword() {
    const newPwd = document.getElementById("set-password-new").value;
    const confirmPwd = document.getElementById("set-password-confirm").value;
    if (newPwd !== confirmPwd) { showError("Hasła nie są zgodne"); return; }
    try {
        const response = await fetch(`${API_URL}/auth/set-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ temp_token: _tempResetToken, new_password: newPwd }),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || "Błąd ustawiania hasła");
        }
        const data = await response.json();
        _tempResetToken = null;
        setToken(data.access_token);
        initApp();
    } catch (e) {
        showError(e.message);
    }
}

async function register() {
    const email = document.getElementById("reg-email").value;
    const password = document.getElementById("reg-password").value;
    const fullName = document.getElementById("reg-fullname").value;
    try {
        await apiRequest("POST", "/auth/register", {
            email, password, full_name: fullName || null,
        });
        showToast("Konto utworzone! Zaloguj się.", "success");
        toggleAuthMode();
    } catch (e) {
        showError(e.message);
    }
}

function showError(msg) {
    const el = document.getElementById("auth-error");
    el.textContent = msg;
    el.classList.remove("hidden");
}

// ==================== NAVIGATION ====================
function showView(viewName) {
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    document.getElementById(`view-${viewName}`).classList.add("active");

    if (viewName === "dashboard") loadDashboard();
    if (viewName === "categories") loadCategories();
    if (viewName === "subscriptions") loadSubscriptions();
    if (viewName === "stats") loadStats();
    if (viewName === "admin") { loadAdminConfig(); loadAdminUsers(); }
    if (viewName === "tags") loadTagsView();
    if (viewName === "add-expense") {
        loadCategoriesSelect();
        document.getElementById("manual-date").valueAsDate = new Date();
    }
}

function toggleMobileMenu() {
    document.getElementById("mobile-menu").classList.toggle("hidden");
}

// ==================== DASHBOARD ====================
async function loadDashboard() {
    await loadCategoriesSelect("filter-category");
    await loadExpenses();
}

async function loadMoreExpenses() {
    currentExpensesOffset += EXPENSES_PER_PAGE;
    const start = document.getElementById("filter-start").value;
    const end = document.getElementById("filter-end").value;
    const cat = document.getElementById("filter-category").value;
    const search = (document.getElementById("filter-search")?.value || "").trim();
    const searchItems = document.getElementById("filter-search-items")?.checked;
    let url = `/expenses/?limit=${EXPENSES_PER_PAGE}&skip=${currentExpensesOffset}`;
    if (start) url += `&start_date=${start}`;
    if (end) url += `&end_date=${end}`;
    if (cat) url += `&category_id=${cat}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (search && searchItems) url += `&search_items=true`;
    try {
        const more = await apiRequest("GET", url);
        currentExpenses = [...currentExpenses, ...more];
        renderExpenses(currentExpenses);
        setLoadMoreVisible(more.length === EXPENSES_PER_PAGE);
    } catch (e) {
        showToast(e.message, "error");
    }
}

function setLoadMoreVisible(visible) {
    const el = document.getElementById("load-more-container");
    if (el) el.classList.toggle("hidden", !visible);
    updateFilterSummary(visible);
}

function updateFilterSummary(hasMore) {
    const summary = document.getElementById("filter-summary");
    if (!summary) return;
    if (!currentExpenses.length) { summary.classList.add("hidden"); return; }
    const total = currentExpenses.reduce((s, e) => s + e.amount, 0);
    const n = currentExpenses.length;
    const suffix = hasMore ? "+" : "";
    const label = n === 1 ? "wydatek" : n < 5 ? "wydatki" : "wydatków";
    document.getElementById("filter-summary-count").textContent = `${n}${suffix} ${label}`;
    document.getElementById("filter-summary-total").textContent = total.toFixed(2);
    summary.classList.remove("hidden");
}

// ==================== DASHBOARD AI QUICK ADD ====================
async function dashboardReceiptSelected(file) {
    if (!file) return;
    currentReceiptFile = file;
    const loading = document.getElementById("dash-ai-loading");
    loading.classList.remove("hidden");
    const formData = new FormData();
    formData.append("file", file);
    try {
        const response = await fetch(`${API_URL}/ai/receipt`, {
            method: "POST",
            headers: { Authorization: `Bearer ${getToken()}` },
            body: formData,
        });
        if (!response.ok) throw new Error("Błąd analizy AI");
        const draft = await response.json();
        showDraft(draft);
    } catch (e) {
        currentReceiptFile = null;
        showToast(e.message, "error");
    } finally {
        loading.classList.add("hidden");
        document.getElementById("dash-receipt-input").value = "";
    }
}

async function dashboardAnalyzeText() {
    const text = document.getElementById("dash-text-input").value.trim();
    if (!text) return showToast("Wpisz opis wydatku", "warning");
    const loading = document.getElementById("dash-ai-loading");
    loading.classList.remove("hidden");
    try {
        const draft = await apiRequest("POST", "/ai/text", { text });
        showDraft(draft);
        document.getElementById("dash-text-input").value = "";
    } catch (e) {
        showToast(e.message, "error");
    } finally {
        loading.classList.add("hidden");
    }
}

function renderExpenses(expenses) {
    currentExpenses = expenses;
    const tbody = document.getElementById("expenses-list");
    const mobileDiv = document.getElementById("expenses-list-mobile");

    if (!expenses.length) {
        const empty = '<tr><td colspan="5" class="px-6 py-4 text-center text-gray-500">Brak wydatków</td></tr>';
        tbody.innerHTML = empty;
        mobileDiv.innerHTML = '<div class="p-4 text-center text-gray-500">Brak wydatków</div>';
        return;
    }

    // Desktop table
    tbody.innerHTML = expenses.map((e) => `
        <tr class="hover:bg-gray-50 cursor-pointer" onclick="openExpenseModal(${e.id})">
            <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">${e.date}</td>
            <td class="px-4 py-3 text-sm text-gray-900">
                ${e.description || "-"}
                ${e.tags && e.tags.length ? `<div class="flex flex-wrap gap-1 mt-1">${e.tags.map(t => `<span class="bg-blue-100 text-blue-700 text-xs px-1.5 py-0.5 rounded-full">#${escapeHtml(t.name)}</span>`).join("")}</div>` : ""}
            </td>
            <td class="px-4 py-3 text-sm text-gray-500">${e.category_name || "-"}</td>
            <td class="px-4 py-3 text-sm text-gray-900 text-right font-medium">${e.amount.toFixed(2)} zł</td>
            <td class="px-4 py-3 text-center text-sm whitespace-nowrap">
                ${e.receipt_image_path ? `<button onclick="event.stopPropagation(); viewReceipt(${e.id})" class="text-gray-400 hover:text-gray-700 mr-2" title="Podgląd paragonu"><i class="fas fa-image"></i></button>` : ""}
                <button onclick="event.stopPropagation(); openExpenseModal(${e.id})" class="text-primary hover:text-blue-700 mr-2" title="Edytuj"><i class="fas fa-pen"></i></button>
                <button onclick="event.stopPropagation(); deleteExpense(${e.id})" class="text-danger hover:text-red-700" title="Usuń"><i class="fas fa-trash"></i></button>
            </td>
        </tr>
    `).join("");

    // Mobile cards with collapsible items
    mobileDiv.innerHTML = expenses.map((e) => {
        const hasItems = e.items && e.items.length > 0;
        const itemsHtml = hasItems ? e.items.map((it) => `
            <div class="flex justify-between text-sm py-1 border-b border-gray-100 last:border-0">
                <span class="text-gray-700">${it.quantity}x ${it.name}</span>
                <span class="text-gray-900 font-medium">${(it.price * it.quantity).toFixed(2)} zł</span>
            </div>
        `).join("") : "";
        return `
        <div class="p-4">
            <div class="flex justify-between items-start">
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-semibold text-gray-900 truncate">${e.description || "Bez opisu"}</p>
                    <p class="text-xs text-gray-500">${e.date} · ${e.category_name || "-"}</p>
                    ${e.tags && e.tags.length ? `<div class="flex flex-wrap gap-1 mt-1">${e.tags.map(t => `<span class="bg-blue-100 text-blue-700 text-xs px-1.5 py-0.5 rounded-full">#${escapeHtml(t.name)}</span>`).join("")}</div>` : ""}
                </div>
                <div class="text-right ml-3">
                    <p class="text-sm font-bold text-gray-900">${e.amount.toFixed(2)} zł</p>
                    <div class="mt-1">
                        ${e.receipt_image_path ? `<button onclick="viewReceipt(${e.id})" class="text-gray-400 hover:text-gray-700 mr-2" title="Paragon"><i class="fas fa-image"></i></button>` : ""}
                        <button onclick="openExpenseModal(${e.id})" class="text-primary hover:text-blue-700 mr-2" title="Edytuj"><i class="fas fa-pen"></i></button>
                        <button onclick="deleteExpense(${e.id})" class="text-danger hover:text-red-700" title="Usuń"><i class="fas fa-trash"></i></button>
                    </div>
                </div>
            </div>
            ${hasItems ? `
            <details class="mt-2">
                <summary class="text-xs text-primary cursor-pointer select-none">Pokaż ${e.items.length} pozycj${e.items.length === 1 ? 'ę' : e.items.length < 5 ? 'e' : 'i'}</summary>
                <div class="mt-2 bg-gray-50 rounded-md p-2 space-y-1">
                    ${itemsHtml}
                </div>
            </details>
            ` : ""}
        </div>
        `;
    }).join("");
}

async function loadExpenses() {
    currentExpensesOffset = 0;
    const start = document.getElementById("filter-start").value;
    const end = document.getElementById("filter-end").value;
    const cat = document.getElementById("filter-category").value;
    const search = (document.getElementById("filter-search")?.value || "").trim();
    const searchItems = document.getElementById("filter-search-items")?.checked;
    let url = `/expenses/?limit=${EXPENSES_PER_PAGE}&skip=0`;
    if (start) url += `&start_date=${start}`;
    if (end) url += `&end_date=${end}`;
    if (cat) url += `&category_id=${cat}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (search && searchItems) url += `&search_items=true`;
    try {
        const expenses = await apiRequest("GET", url);
        currentExpenses = expenses;
        renderExpenses(expenses);
        setLoadMoreVisible(expenses.length === EXPENSES_PER_PAGE);
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteExpense(id) {
    if (!confirm("Usunąć wydatek?")) return;
    try {
        await apiRequest("DELETE", `/expenses/${id}`);
        loadExpenses();
        showToast("Wydatek usunięty", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== TAGS ====================
let _tagsCache = [];
let _popularTagsCache = [];

async function loadTagsCache() {
    try {
        _tagsCache = await apiRequest("GET", "/tags/");
    } catch (_) { _tagsCache = []; }
}

async function loadPopularTagsCache() {
    try {
        _popularTagsCache = await apiRequest("GET", "/tags/?popular=true&limit=10");
    } catch (_) { _popularTagsCache = []; }
}

// ---- Tag suggestions dropdown ----

function _showTagDropdown(inputEl, onSelect) {
    const dropdown = document.getElementById("tag-dropdown");
    const list = document.getElementById("tag-dropdown-list");
    const empty = document.getElementById("tag-dropdown-empty");
    if (!dropdown) return;

    const tags = _popularTagsCache.length ? _popularTagsCache : _tagsCache;

    if (!tags.length) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
    } else {
        empty.classList.add("hidden");
        list.innerHTML = tags.map(t =>
            `<button class="bg-blue-100 text-blue-700 text-xs px-2 py-0.5 rounded-full hover:bg-blue-200 transition-colors"
                     data-tagname="${escapeHtml(t.name)}"
                     onmousedown="event.preventDefault(); _tagDropdownPick(this.dataset.tagname)">#${escapeHtml(t.name)}</button>`
        ).join("");
    }

    dropdown._onSelect = onSelect;

    const rect = inputEl.getBoundingClientRect();
    dropdown.style.top = (rect.bottom + 4) + "px";
    dropdown.style.left = rect.left + "px";
    dropdown.style.width = Math.max(rect.width, 220) + "px";
    dropdown.classList.remove("hidden");
}

function _hideTagDropdown() {
    document.getElementById("tag-dropdown")?.classList.add("hidden");
}

function _tagDropdownPick(tagName) {
    const dropdown = document.getElementById("tag-dropdown");
    if (dropdown?._onSelect) dropdown._onSelect(tagName);
    _hideTagDropdown();
}

function _renderTagChip(name, containerId, removable = true) {
    const container = document.getElementById(containerId);
    if (!container) return;
    // Nie dodawaj duplikatu
    const existing = [...container.querySelectorAll("[data-tag]")].map(el => el.dataset.tag);
    if (existing.includes(name)) return;
    const chip = document.createElement("span");
    chip.dataset.tag = name;
    chip.className = "inline-flex items-center gap-1 bg-blue-100 text-blue-800 text-xs font-medium px-2 py-0.5 rounded-full";
    chip.innerHTML = `#${escapeHtml(name)}${removable ? ` <button onclick="this.parentElement.remove()" class="text-blue-600 hover:text-blue-900 ml-0.5">&times;</button>` : ""}`;
    container.appendChild(chip);
}

function _getTagsFromContainer(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    return [...container.querySelectorAll("[data-tag]")].map(el => el.dataset.tag);
}

function _fillTagsDatalist(datalistId) {
    const dl = document.getElementById(datalistId);
    if (!dl) return;
    dl.innerHTML = _tagsCache.map(t => `<option value="#${t.name}">`).join("");
}

function _addTagToContainer(inputId, containerId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const raw = input.value.trim().replace(/^#+/, "").toLowerCase();
    if (raw) { _renderTagChip(raw, containerId); }
    input.value = "";
}

function addTagFromInput() { _addTagToContainer("modal-tag-input", "modal-tags-container"); }
function addDraftTagFromInput() { _addTagToContainer("draft-tag-input", "draft-tags-container"); }

async function _saveTagsForExpense(expenseId, containerId) {
    // Flush any text still sitting in the associated input
    const inputId = containerId === "modal-tags-container" ? "modal-tag-input" : "draft-tag-input";
    _addTagToContainer(inputId, containerId);

    const tagNames = _getTagsFromContainer(containerId);
    try {
        await apiRequest("PUT", `/tags/expenses/${expenseId}`, tagNames);
    } catch (e) {
        showToast("Błąd zapisu tagów: " + e.message, "error");
    }
}

// ==================== EXPENSE MODAL (EDIT / VIEW) ====================
let currentReceiptBlobUrl = null;

async function openExpenseModal(expenseId) {
    let expense = currentExpenses.find((e) => e.id === expenseId);
    if (!expense) {
        try {
            expense = await apiRequest("GET", `/expenses/${expenseId}`);
        } catch (e) {
            showToast("Nie można wczytać wydatku", "error");
            return;
        }
    }
    currentEditingExpenseId = expenseId;

    document.getElementById("modal-amount").value = expense.amount;
    document.getElementById("modal-date").value = expense.date;
    document.getElementById("modal-description").value = expense.description || "";
    loadCategoriesSelect("modal-category", expense.category_id);

    const itemsList = document.getElementById("modal-items-list");
    if (expense.items && expense.items.length) {
        itemsList.innerHTML = expense.items.map((item, i) => `
            <div class="flex flex-col sm:flex-row gap-2 items-start sm:items-center p-2 bg-gray-50 rounded">
                <input type="text" class="flex-1 w-full border rounded px-2 py-1 text-sm" value="${escapeHtml(item.name)}" id="modal-item-${i}-name">
                <div class="flex gap-2 w-full sm:w-auto">
                    <input type="number" step="0.01" class="w-24 border rounded px-2 py-1 text-sm" value="${item.price}" id="modal-item-${i}-price">
                    <input type="number" step="0.1" class="w-20 border rounded px-2 py-1 text-sm" value="${item.quantity}" id="modal-item-${i}-qty">
                    <select class="w-32 border rounded px-2 py-1 text-sm" id="modal-item-${i}-cat">
                        ${categoriesCache.map((c) => `<option value="${c.id}" ${c.id === item.category_id ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}
                    </select>
                    <button onclick="this.parentElement.parentElement.remove(); updateModalItemsTotal();" class="text-danger"><i class="fas fa-times"></i></button>
                </div>
            </div>
        `).join("");
    } else {
        itemsList.innerHTML = "";
    }
    updateModalItemsTotal();

    // Tags
    const tagsContainer = document.getElementById("modal-tags-container");
    tagsContainer.innerHTML = "";
    (expense.tags || []).forEach(t => _renderTagChip(t.name, "modal-tags-container"));
    document.getElementById("modal-tag-input").value = "";
    _fillTagsDatalist("modal-tags-datalist");

    // Receipt image
    if (currentReceiptBlobUrl) { URL.revokeObjectURL(currentReceiptBlobUrl); currentReceiptBlobUrl = null; }
    const receiptSection = document.getElementById("modal-receipt-section");
    receiptSection.classList.add("hidden");
    document.getElementById("modal-receipt-img").src = "";
    if (expense.receipt_image_path) {
        loadReceiptImage(expenseId);
    }

    document.getElementById("expense-modal").classList.remove("hidden");
    _modalDirty = false;
}

async function viewReceipt(expenseId) {
    try {
        const response = await fetch(`${API_URL}/receipts/${expenseId}/receipt`, {
            headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!response.ok) return showToast("Brak zdjęcia paragonu", "warning");
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        document.getElementById("receipt-fullscreen-img").src = url;
        document.getElementById("receipt-fullscreen").classList.remove("hidden");
        // revoke after close
        document.getElementById("receipt-fullscreen").dataset.blobUrl = url;
    } catch (e) {
        showToast("Błąd ładowania paragonu", "error");
    }
}

async function loadReceiptImage(expenseId) {
    try {
        const response = await fetch(`${API_URL}/receipts/${expenseId}/receipt`, {
            headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!response.ok) return;
        const blob = await response.blob();
        currentReceiptBlobUrl = URL.createObjectURL(blob);
        const img = document.getElementById("modal-receipt-img");
        img.src = currentReceiptBlobUrl;
        document.getElementById("modal-receipt-section").classList.remove("hidden");
    } catch (_) {}
}

function openReceiptFullscreen() {
    if (!currentReceiptBlobUrl) return;
    document.getElementById("receipt-fullscreen-img").src = currentReceiptBlobUrl;
    document.getElementById("receipt-fullscreen").classList.remove("hidden");
}

function closeReceiptFullscreen() {
    const el = document.getElementById("receipt-fullscreen");
    el.classList.add("hidden");
    const blobUrl = el.dataset.blobUrl;
    if (blobUrl) { URL.revokeObjectURL(blobUrl); delete el.dataset.blobUrl; }
}

function closeExpenseModal(force = false) {
    if (!force && _modalDirty && !confirm("Masz niezapisane zmiany. Zamknąć bez zapisywania?")) return;
    _modalDirty = false;
    document.getElementById("expense-modal").classList.add("hidden");
    currentEditingExpenseId = null;
    if (currentReceiptBlobUrl) { URL.revokeObjectURL(currentReceiptBlobUrl); currentReceiptBlobUrl = null; }
}

function addModalItem() {
    const div = document.createElement("div");
    div.className = "flex flex-col sm:flex-row gap-2 items-start sm:items-center p-2 bg-gray-50 rounded";
    div.innerHTML = `
        <input type="text" class="flex-1 w-full border rounded px-2 py-1 text-sm" placeholder="Nazwa" id="modal-item-new-name">
        <div class="flex gap-2 w-full sm:w-auto">
            <input type="number" step="0.01" class="w-24 border rounded px-2 py-1 text-sm" placeholder="Cena" id="modal-item-new-price">
            <input type="number" step="0.1" class="w-20 border rounded px-2 py-1 text-sm" value="1" id="modal-item-new-qty">
            <select class="w-32 border rounded px-2 py-1 text-sm" id="modal-item-new-cat">
                ${categoriesCache.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("")}
            </select>
            <button onclick="this.parentElement.parentElement.remove(); updateModalItemsTotal();" class="text-danger"><i class="fas fa-times"></i></button>
        </div>
    `;
    document.getElementById("modal-items-list").appendChild(div);
    updateModalItemsTotal();
}

function updateModalItemsTotal() {
    let total = 0;
    document.querySelectorAll("#modal-items-list > div").forEach((div) => {
        const inputs = div.querySelectorAll("input");
        const price = parseFloat(inputs[1]?.value || 0);
        const qty = parseFloat(inputs[2]?.value || 1);
        total += price * qty;
    });
    document.getElementById("modal-items-total").textContent = total > 0 ? `Suma pozycji: ${total.toFixed(2)} zł` : "";
}

async function saveExpenseModal() {
    const items = [];
    document.querySelectorAll("#modal-items-list > div").forEach((div) => {
        const inputs = div.querySelectorAll("input, select");
        const name = inputs[0].value.trim();
        if (!name) return;
        items.push({
            name,
            price: parseFloat(inputs[1].value) || 0,
            quantity: parseFloat(inputs[2].value) || 1,
            category_id: inputs[3].value || null,
        });
    });

    const data = {
        amount: parseFloat(document.getElementById("modal-amount").value),
        date: document.getElementById("modal-date").value,
        description: document.getElementById("modal-description").value,
        category_id: document.getElementById("modal-category").value || null,
        items: items,
    };

    try {
        await apiRequest("PUT", `/expenses/${currentEditingExpenseId}`, data);
        await _saveTagsForExpense(currentEditingExpenseId, "modal-tags-container");
        await Promise.all([loadTagsCache(), loadPopularTagsCache()]);
        showToast("Wydatek zaktualizowany!", "success");
        closeExpenseModal(true);
        loadExpenses();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteExpenseModal() {
    if (!currentEditingExpenseId) return;
    if (!confirm("Usunąć wydatek?")) return;
    try {
        await apiRequest("DELETE", `/expenses/${currentEditingExpenseId}`);
        closeExpenseModal(true);
        loadExpenses();
        showToast("Wydatek usunięty", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== ADD EXPENSE ====================
function showExpenseTab(tab) {
    ["manual", "receipt", "text"].forEach((t) => {
        document.getElementById(`expense-tab-${t}`).classList.add("hidden");
        const btn = document.getElementById(`tab-${t}`);
        btn.classList.remove("border-primary", "text-primary");
        btn.classList.add("border-transparent", "text-gray-500");
    });
    document.getElementById(`expense-tab-${tab}`).classList.remove("hidden");
    const activeBtn = document.getElementById(`tab-${tab}`);
    activeBtn.classList.remove("border-transparent", "text-gray-500");
    activeBtn.classList.add("border-primary", "text-primary");
}

async function addManualExpense() {
    const data = {
        amount: parseFloat(document.getElementById("manual-amount").value),
        date: document.getElementById("manual-date").value,
        description: document.getElementById("manual-description").value,
        category_id: document.getElementById("manual-category").value || null,
        items: [],
    };
    try {
        await apiRequest("POST", "/expenses/", data);
        showToast("Wydatek zapisany!", "success");
        showView("dashboard");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== RECEIPT UPLOAD (add-expense view) ====================
function initReceiptUpload() {
    const uploadArea = document.getElementById("receipt-upload-area");
    const fileInput = document.getElementById("receipt-file-input");
    if (!uploadArea || !fileInput) return;
    uploadArea.addEventListener("click", () => fileInput.click());
    uploadArea.addEventListener("dragover", (e) => {
        e.preventDefault();
        uploadArea.classList.add("drag-over");
    });
    uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("drag-over"));
    uploadArea.addEventListener("drop", (e) => {
        e.preventDefault();
        uploadArea.classList.remove("drag-over");
        if (e.dataTransfer.files.length) handleReceiptFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length) handleReceiptFile(e.target.files[0]);
    });
}

function handleReceiptFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById("receipt-preview-img").src = e.target.result;
        document.getElementById("receipt-preview").classList.remove("hidden");
        document.getElementById("receipt-upload-area").classList.add("hidden");
    };
    reader.readAsDataURL(file);
}

async function analyzeReceipt() {
    const file = document.getElementById("receipt-file-input").files[0];
    if (!file) return showToast("Wybierz zdjęcie", "warning");
    currentReceiptFile = file;

    document.getElementById("receipt-loading").classList.remove("hidden");
    document.getElementById("receipt-preview").classList.add("hidden");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch(`${API_URL}/ai/receipt`, {
            method: "POST",
            headers: { Authorization: `Bearer ${getToken()}` },
            body: formData,
        });
        if (!response.ok) throw new Error("Błąd analizy AI");
        const draft = await response.json();
        showDraft(draft);
    } catch (e) {
        showToast(e.message, "error");
    } finally {
        document.getElementById("receipt-loading").classList.add("hidden");
    }
}

// ==================== TEXT AI ====================
async function analyzeTextExpense() {
    const text = document.getElementById("text-expense-input").value;
    if (!text.trim()) return showToast("Wpisz opis wydatku", "warning");

    document.getElementById("text-loading").classList.remove("hidden");

    try {
        const draft = await apiRequest("POST", "/ai/text", { text: text.trim() });
        showDraft(draft);
    } catch (e) {
        showToast(e.message, "error");
    } finally {
        document.getElementById("text-loading").classList.add("hidden");
    }
}

// ==================== DRAFT REVIEW (modal) ====================
function showDraft(draft) {
    currentDraft = draft;

    document.getElementById("draft-amount").value = draft.amount;
    document.getElementById("draft-date").value = draft.date;
    document.getElementById("draft-description").value = draft.description || "";

    const dupDiv = document.getElementById("draft-duplicates");
    if (draft.duplicate_warnings && draft.duplicate_warnings.length) {
        dupDiv.classList.remove("hidden");
        document.getElementById("draft-duplicates-list").innerHTML = draft.duplicate_warnings
            .map((d) => `<div><i class="fas fa-exclamation-circle mr-1"></i>${escapeHtml(d.message)}</div>`)
            .join("");
    } else {
        dupDiv.classList.add("hidden");
    }

    loadCategoriesSelect("draft-category", draft.category_id);

    const itemsDiv = document.getElementById("draft-items-list");
    if (draft.items && draft.items.length) {
        document.getElementById("draft-items-section").classList.remove("hidden");
        itemsDiv.innerHTML = draft.items.map((item, i) => `
            <div class="flex flex-col sm:flex-row gap-2 items-start sm:items-center p-2 bg-gray-50 rounded">
                <input type="text" class="flex-1 w-full border rounded px-2 py-1 text-sm" value="${escapeHtml(item.name)}" id="draft-item-${i}-name">
                <div class="flex gap-2 w-full sm:w-auto">
                    <input type="number" step="0.01" class="w-24 border rounded px-2 py-1 text-sm" value="${item.price}" id="draft-item-${i}-price">
                    <input type="number" step="0.1" class="w-20 border rounded px-2 py-1 text-sm" value="${item.quantity}" id="draft-item-${i}-qty">
                    <select class="w-32 border rounded px-2 py-1 text-sm" id="draft-item-${i}-cat">
                        ${categoriesCache.map((c) => `<option value="${c.id}" ${c.id === item.category_id ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("")}
                    </select>
                    <button onclick="this.parentElement.parentElement.remove()" class="text-danger"><i class="fas fa-times"></i></button>
                </div>
            </div>
        `).join("");
    } else {
        document.getElementById("draft-items-section").classList.add("hidden");
    }

    // Tags
    document.getElementById("draft-tags-container").innerHTML = "";
    document.getElementById("draft-tag-input").value = "";
    _fillTagsDatalist("draft-tags-datalist");

    const suggestedDiv = document.getElementById("draft-suggested-tags");
    const suggestedList = document.getElementById("draft-suggested-tags-list");
    if (draft.suggested_tags && draft.suggested_tags.length) {
        suggestedDiv.classList.remove("hidden");
        suggestedList.innerHTML = draft.suggested_tags.map(t => `
            <button onclick="this.classList.toggle('ring-2'); _renderTagChip('${t}', 'draft-tags-container')"
                class="inline-flex items-center bg-blue-50 border border-blue-200 text-blue-700 text-xs px-2 py-0.5 rounded-full hover:bg-blue-100 transition-colors">
                #${escapeHtml(t)} <i class="fas fa-plus ml-1 text-[10px]"></i>
            </button>`).join("");
    } else {
        suggestedDiv.classList.add("hidden");
    }

    if (draft.user_hints && draft.user_hints.length) {
        draft.user_hints.forEach((h) => showToast(h, "warning"));
    }

    document.getElementById("draft-modal").classList.remove("hidden");
}

function addDraftItem() {
    const div = document.createElement("div");
    div.className = "flex flex-col sm:flex-row gap-2 items-start sm:items-center p-2 bg-gray-50 rounded";
    div.innerHTML = `
        <input type="text" class="flex-1 w-full border rounded px-2 py-1 text-sm" placeholder="Nazwa">
        <div class="flex gap-2 w-full sm:w-auto">
            <input type="number" step="0.01" class="w-24 border rounded px-2 py-1 text-sm" placeholder="Cena">
            <input type="number" step="0.1" class="w-20 border rounded px-2 py-1 text-sm" value="1">
            <select class="w-32 border rounded px-2 py-1 text-sm">
                ${categoriesCache.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("")}
            </select>
            <button onclick="this.parentElement.parentElement.remove()" class="text-danger"><i class="fas fa-times"></i></button>
        </div>
    `;
    document.getElementById("draft-items-list").appendChild(div);
}

async function saveDraftExpense() {
    const items = [];
    document.querySelectorAll("#draft-items-list > div").forEach((div) => {
        const inputs = div.querySelectorAll("input, select");
        const name = inputs[0].value.trim();
        if (!name) return;
        items.push({
            name,
            price: parseFloat(inputs[1].value) || 0,
            quantity: parseFloat(inputs[2].value) || 1,
            category_id: inputs[3].value || null,
        });
    });

    const data = {
        amount: parseFloat(document.getElementById("draft-amount").value),
        date: document.getElementById("draft-date").value,
        description: document.getElementById("draft-description").value,
        category_id: document.getElementById("draft-category").value || null,
        items,
    };

    try {
        const saved = await apiRequest("POST", "/expenses/", data);
        if (saved && saved.id) {
            // Zapisz tagi
            await _saveTagsForExpense(saved.id, "draft-tags-container");
            await Promise.all([loadTagsCache(), loadPopularTagsCache()]);
            // Dołącz zdjęcie paragonu
            if (currentReceiptFile) {
                const formData = new FormData();
                formData.append("file", currentReceiptFile);
                await fetch(`${API_URL}/receipts/${saved.id}/receipt`, {
                    method: "POST",
                    headers: { Authorization: `Bearer ${getToken()}` },
                    body: formData,
                }).catch(() => {});
            }
        }
        showToast("Wydatek zapisany!", "success");
        discardDraft();
        loadExpenses();
    } catch (e) {
        showToast(e.message, "error");
    }
}

function discardDraft() {
    currentDraft = null;
    currentReceiptFile = null;
    document.getElementById("draft-modal").classList.add("hidden");
    // Reset upload area in add-expense view
    const uploadArea = document.getElementById("receipt-upload-area");
    if (uploadArea) uploadArea.classList.remove("hidden");
    const preview = document.getElementById("receipt-preview");
    if (preview) preview.classList.add("hidden");
    const textInput = document.getElementById("text-expense-input");
    if (textInput) textInput.value = "";
}

// ==================== CATEGORIES ====================
async function loadCategories() {
    try {
        const cats = await apiRequest("GET", "/categories/?include_global=true");
        categoriesCache = cats;
        const tbody = document.getElementById("categories-list");
        tbody.innerHTML = cats.map((c) => `
            <tr id="cat-row-${c.id}">
                <td class="px-4 py-3 text-sm text-gray-900" id="cat-name-${c.id}">${escapeHtml(c.name)}</td>
                <td class="px-4 py-3 text-right text-sm whitespace-nowrap">
                    ${c.user_id ? `
                        <button onclick="startRenameCategory(${c.id}, '${escapeHtml(c.name)}')" class="text-gray-400 hover:text-primary mr-3" title="Zmień nazwę"><i class="fas fa-pen text-xs"></i></button>
                        <button onclick="deleteCategory(${c.id})" class="text-gray-400 hover:text-danger" title="Usuń"><i class="fas fa-trash text-xs"></i></button>
                    ` : '<span class="text-gray-400 text-xs">globalna</span>'}
                </td>
            </tr>
        `).join("");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function loadCategoriesSelect(selectId = "manual-category", selectedId = null) {
    try {
        const cats = await apiRequest("GET", "/categories/?include_global=true");
        categoriesCache = cats;
        const select = document.getElementById(selectId);
        if (!select) return;
        select.innerHTML = '<option value="">-- wybierz --</option>' +
            cats.map((c) => `<option value="${c.id}" ${c.id == selectedId ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("");
    } catch (e) {
        showToast("Błąd ładowania kategorii: " + e.message, "error");
    }
}

function showAddCategoryForm() {
    document.getElementById("add-category-form").classList.remove("hidden");
}
function hideAddCategoryForm() {
    document.getElementById("add-category-form").classList.add("hidden");
}

async function addCategory() {
    const name = document.getElementById("new-category-name").value;
    if (!name) return;
    try {
        await apiRequest("POST", "/categories/", { name });
        hideAddCategoryForm();
        loadCategories();
        showToast("Kategoria dodana!", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteCategory(id) {
    if (!confirm("Usunąć kategorię?")) return;
    try {
        await apiRequest("DELETE", `/categories/${id}`);
        loadCategories();
        showToast("Kategoria usunięta", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function startRenameCategory(id, currentName) {
    const nameTd = document.getElementById(`cat-name-${id}`);
    nameTd.innerHTML = `
        <form onsubmit="submitRenameCategory(event, ${id})" class="flex items-center gap-2">
            <input type="text" value="${escapeHtml(currentName)}" id="cat-rename-${id}"
                class="border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary w-48"
                onkeydown="if(event.key==='Escape') loadCategories()" />
            <button type="submit" class="text-success hover:text-green-700 text-xs"><i class="fas fa-check"></i></button>
            <button type="button" onclick="loadCategories()" class="text-gray-400 hover:text-gray-600 text-xs"><i class="fas fa-times"></i></button>
        </form>`;
    document.getElementById(`cat-rename-${id}`).focus();
}

async function submitRenameCategory(event, id) {
    event.preventDefault();
    const input = document.getElementById(`cat-rename-${id}`);
    const newName = input.value.trim();
    if (!newName) return;
    try {
        await apiRequest("PUT", `/categories/${id}`, { name: newName });
        loadCategories();
        showToast("Nazwa kategorii zmieniona", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== SUBSCRIPTIONS ====================
async function loadSubscriptions() {
    try {
        const subs = await apiRequest("GET", "/subscriptions/");
        const tbody = document.getElementById("subscriptions-list");
        if (!subs.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-4 text-center text-gray-500">Brak abonamentów</td></tr>';
        } else {
            tbody.innerHTML = subs.map((s) => `
                <tr class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-sm text-gray-900 font-medium">${escapeHtml(s.name)}</td>
                    <td class="px-4 py-3 text-sm text-gray-900 text-right">${s.amount.toFixed(2)} zł</td>
                    <td class="px-4 py-3 text-sm text-gray-500 hidden sm:table-cell">co ${s.frequency_days} dni</td>
                    <td class="px-4 py-3 text-sm text-gray-500">${s.next_billing_date}</td>
                    <td class="px-4 py-3 text-right text-sm">
                        <button onclick="openSubModal(${s.id})" class="text-primary hover:text-blue-700 mr-2"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteSubscription(${s.id})" class="text-danger hover:text-red-700"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
            `).join("");
        }
        loadCategoriesSelect("sub-category");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function openSubModal(id) {
    try {
        const s = await apiRequest("GET", `/subscriptions/${id}`);
        document.getElementById("sub-modal-id").value = s.id;
        document.getElementById("sub-modal-name").value = s.name;
        document.getElementById("sub-modal-amount").value = s.amount;
        document.getElementById("sub-modal-frequency").value = s.frequency_days;
        document.getElementById("sub-modal-next").value = s.next_billing_date;
        document.getElementById("sub-modal-end").value = s.end_date || "";
        document.getElementById("sub-modal-installments").value = s.remaining_installments || "";
        await loadCategoriesSelect("sub-modal-category");
        document.getElementById("sub-modal-category").value = s.category_id || "";
        document.getElementById("sub-modal").classList.remove("hidden");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function closeSubModal() {
    document.getElementById("sub-modal").classList.add("hidden");
}

async function saveSubModal() {
    const id = document.getElementById("sub-modal-id").value;
    const installmentsVal = document.getElementById("sub-modal-installments").value;
    const data = {
        name: document.getElementById("sub-modal-name").value,
        amount: parseFloat(document.getElementById("sub-modal-amount").value),
        frequency_days: parseInt(document.getElementById("sub-modal-frequency").value),
        next_billing_date: document.getElementById("sub-modal-next").value,
        end_date: document.getElementById("sub-modal-end").value || null,
        remaining_installments: installmentsVal ? parseInt(installmentsVal) : null,
        category_id: document.getElementById("sub-modal-category").value || null,
    };
    try {
        await apiRequest("PUT", `/subscriptions/${id}`, data);
        closeSubModal();
        loadSubscriptions();
        showToast("Abonament zaktualizowany", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function showAddSubscriptionForm() {
    document.getElementById("add-subscription-form").classList.remove("hidden");
}
function hideAddSubscriptionForm() {
    document.getElementById("add-subscription-form").classList.add("hidden");
}

async function addSubscription() {
    const data = {
        name: document.getElementById("sub-name").value,
        amount: parseFloat(document.getElementById("sub-amount").value),
        frequency_days: parseInt(document.getElementById("sub-frequency").value),
        start_date: document.getElementById("sub-start").value,
        end_date: document.getElementById("sub-end").value || null,
        next_billing_date: document.getElementById("sub-start").value,
        remaining_installments: document.getElementById("sub-installments").value ? parseInt(document.getElementById("sub-installments").value) : null,
        category_id: document.getElementById("sub-category").value || null,
    };
    try {
        await apiRequest("POST", "/subscriptions/", data);
        hideAddSubscriptionForm();
        loadSubscriptions();
        showToast("Abonament dodany!", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteSubscription(id) {
    if (!confirm("Usunąć abonament?")) return;
    try {
        await apiRequest("DELETE", `/subscriptions/${id}`);
        closeSubModal();
        loadSubscriptions();
        showToast("Abonament usunięty", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== STATS & CHARTS ====================
let categoryChart = null;
let dailyChart = null;

async function loadStats() {
    const now = new Date();

    // Default: last 12 months
    const startEl = document.getElementById("stats-start");
    const endEl = document.getElementById("stats-end");
    if (!startEl.value) {
        const d = new Date(now.getFullYear(), now.getMonth() - 11, 1);
        startEl.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
    }
    if (!endEl.value) {
        endEl.value = now.toISOString().split("T")[0];
    }

    const start = startEl.value;
    const end = endEl.value;

    // Reset expansion caches on each full reload
    _monthCategoryCache = {};
    _categoryExpenseCache = {};

    const monthStart = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;

    try {
        const [data, monthData, subs] = await Promise.all([
            apiRequest("GET", `/stats/?start_date=${start}&end_date=${end}`),
            apiRequest("GET", `/stats/?start_date=${monthStart}`),
            apiRequest("GET", "/subscriptions/?active_only=true"),
        ]);

        // Top quick cards
        document.getElementById("stat-month-total").textContent = monthData.total_amount.toFixed(2) + " zł";
        document.getElementById("stat-count").textContent = data.total_count;
        document.getElementById("stat-subs").textContent = subs.length;

        // Detailed summary cards
        document.getElementById("stats-total").textContent = data.total_amount.toFixed(2) + " zł";
        document.getElementById("stats-count").textContent = data.total_count;
        document.getElementById("stats-avg-day").textContent = (data.average_per_day || 0).toFixed(2) + " zł";
        document.getElementById("stats-avg-exp").textContent = data.average_per_expense.toFixed(2) + " zł";

        // Monthly table (expandable)
        renderMonthlyTable(data.monthly_summary);

        // Category doughnut chart
        const catCtx = document.getElementById("chart-categories").getContext("2d");
        if (categoryChart) categoryChart.destroy();
        categoryChart = new Chart(catCtx, {
            type: "doughnut",
            data: {
                labels: data.category_summary.map((c) => c.category_name || "Bez kategorii"),
                datasets: [{
                    data: data.category_summary.map((c) => c.total_amount),
                    backgroundColor: ["#3b82f6","#22c55e","#f59e0b","#ef4444","#8b5cf6","#06b6d4","#ec4899","#84cc16"],
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom" } },
            },
        });

        // Monthly bar chart (sorted ascending)
        const sorted = [...data.monthly_summary].sort((a, b) => a.year !== b.year ? a.year - b.year : a.month - b.month);
        const dailyCtx = document.getElementById("chart-daily").getContext("2d");
        if (dailyChart) dailyChart.destroy();
        dailyChart = new Chart(dailyCtx, {
            type: "bar",
            data: {
                labels: sorted.map((m) => `${m.month_name} ${m.year}`),
                datasets: [{
                    label: "Kwota (zł)",
                    data: sorted.map((m) => m.total_amount),
                    backgroundColor: "rgba(59, 130, 246, 0.7)",
                    borderColor: "#3b82f6",
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: true } },
                plugins: { legend: { display: false } },
            },
        });
    } catch (e) {
        showToast(e.message, "error");
    }
}

function renderMonthlyTable(monthlySummary) {
    const tbody = document.getElementById("stats-monthly-list");
    if (!monthlySummary || !monthlySummary.length) {
        tbody.innerHTML = '<tr><td colspan="3" class="px-6 py-4 text-center text-gray-500">Brak danych</td></tr>';
        return;
    }
    // Sort descending (newest first)
    const rows = [...monthlySummary].sort((a, b) => a.year !== b.year ? b.year - a.year : b.month - a.month);
    tbody.innerHTML = rows.map((m) => `
        <tr class="month-row cursor-pointer hover:bg-blue-50 transition-colors"
            data-year="${m.year}" data-month="${m.month}"
            onclick="toggleMonthDetails(${m.year}, ${m.month}, this)">
            <td class="px-4 py-3 text-sm text-gray-900 font-medium">
                <i class="fas fa-chevron-right text-gray-400 mr-2 expand-icon transition-transform duration-200"></i>
                ${m.month_name} ${m.year}
            </td>
            <td class="px-4 py-3 text-sm text-gray-900 text-right font-semibold">${m.total_amount.toFixed(2)} zł</td>
            <td class="px-4 py-3 text-sm text-gray-500 text-right">${m.expense_count}</td>
        </tr>
    `).join("");
}

async function toggleMonthDetails(year, month, rowEl) {
    const key = `${year}-${month}`;
    const existingDetail = document.getElementById(`month-detail-${key}`);
    if (existingDetail) {
        existingDetail.remove();
        rowEl.querySelector(".expand-icon").style.transform = "";
        return;
    }

    rowEl.querySelector(".expand-icon").style.transform = "rotate(90deg)";

    if (!_monthCategoryCache[key]) {
        const monthStr = String(month).padStart(2, "0");
        const lastDay = new Date(year, month, 0).getDate();
        const start = `${year}-${monthStr}-01`;
        const end = `${year}-${monthStr}-${lastDay}`;
        try {
            const data = await apiRequest("GET", `/stats/?start_date=${start}&end_date=${end}`);
            _monthCategoryCache[key] = { cats: data.category_summary, start, end };
        } catch (e) {
            showToast(e.message, "error");
            rowEl.querySelector(".expand-icon").style.transform = "";
            return;
        }
    }

    const { cats, start, end } = _monthCategoryCache[key];
    const detailRow = document.createElement("tr");
    detailRow.id = `month-detail-${key}`;
    detailRow.innerHTML = `
        <td colspan="3" class="px-0 py-0 bg-gray-50">
            <table class="min-w-full">
                <tbody id="month-cats-${key}">
                    ${cats.map((c) => {
                        const catId = c.category_id || "null";
                        const catName = c.category_name || "Bez kategorii";
                        return `<tr class="cat-row cursor-pointer hover:bg-blue-100 transition-colors"
                                    onclick="toggleCategoryExpenses('${key}-${catId}', '${key}', ${c.category_id || "null"}, '${start}', '${end}', this)">
                                    <td class="pl-10 pr-4 py-2 text-sm text-gray-700">
                                        <i class="fas fa-chevron-right text-gray-400 mr-2 expand-icon transition-transform duration-200"></i>
                                        ${catName}
                                    </td>
                                    <td class="px-4 py-2 text-sm text-gray-800 text-right font-medium">${c.total_amount.toFixed(2)} zł</td>
                                    <td class="px-4 py-2 text-sm text-gray-500 text-right">${c.expense_count}</td>
                                </tr>`;
                    }).join("")}
                </tbody>
            </table>
        </td>`;
    rowEl.insertAdjacentElement("afterend", detailRow);
}

async function toggleCategoryExpenses(cacheKey, monthKey, categoryId, start, end, rowEl) {
    const existingDetail = document.getElementById(`cat-detail-${cacheKey}`);
    if (existingDetail) {
        existingDetail.remove();
        rowEl.querySelector(".expand-icon").style.transform = "";
        return;
    }

    rowEl.querySelector(".expand-icon").style.transform = "rotate(90deg)";

    if (!_categoryExpenseCache[cacheKey]) {
        try {
            let url;
            if (categoryId === null || categoryId === "null") {
                // Fetch all for the month, then filter uncategorized client-side
                const all = await apiRequest("GET", `/expenses/?start_date=${start}&end_date=${end}&limit=500`);
                _categoryExpenseCache[cacheKey] = all.filter(e => !e.category_id);
            } else {
                _categoryExpenseCache[cacheKey] = await apiRequest("GET", `/expenses/?start_date=${start}&end_date=${end}&category_id=${categoryId}&limit=500`);
            }
        } catch (e) {
            showToast(e.message, "error");
            rowEl.querySelector(".expand-icon").style.transform = "";
            return;
        }
    }

    const expenses = _categoryExpenseCache[cacheKey];
    const tbody = rowEl.closest("tbody");
    const detailRow = document.createElement("tr");
    detailRow.id = `cat-detail-${cacheKey}`;

    if (!expenses.length) {
        detailRow.innerHTML = `<td colspan="3" class="pl-16 pr-4 py-2 text-xs text-gray-400 italic">Brak wydatków</td>`;
    } else {
        detailRow.innerHTML = `
            <td colspan="3" class="px-0 py-0">
                <table class="min-w-full bg-white">
                    <tbody>
                        ${expenses.map(e => `
                            <tr class="hover:bg-gray-50">
                                <td class="pl-16 pr-4 py-1.5 text-xs text-gray-600">${e.date} — ${e.description || "—"}</td>
                                <td class="px-4 py-1.5 text-xs text-gray-800 text-right font-medium">${e.amount.toFixed(2)} zł</td>
                                <td class="px-4 py-1.5 text-xs text-gray-400 text-right">
                                    <button onclick="event.stopPropagation(); openExpenseModal(${e.id})" class="text-primary hover:underline">edytuj</button>
                                </td>
                            </tr>`).join("")}
                    </tbody>
                </table>
            </td>`;
    }

    rowEl.insertAdjacentElement("afterend", detailRow);
}

async function exportCSV() {
    const start = document.getElementById("stats-start").value;
    const end = document.getElementById("stats-end").value;
    let url = "/stats/export";
    if (start) url += `?start_date=${start}`;
    if (end) url += `${start ? "&" : "?"}end_date=${end}`;

    try {
        const response = await fetch(`${API_URL}${url}`, {
            headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!response.ok) throw new Error("Błąd eksportu");
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = `wydatki_${new Date().toISOString().split("T")[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
        showToast("CSV pobrany!", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== UTILS ====================
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    const colors = {
        success: "bg-green-500",
        error: "bg-red-500",
        warning: "bg-yellow-500",
        info: "bg-blue-500",
    };
    toast.className = `${colors[type] || colors.info} text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 fade-in`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ==================== INIT ====================
async function initApp() {
    document.getElementById("navbar").classList.remove("hidden");
    try {
        currentUser = await apiRequest("GET", "/auth/me");
        if (currentUser.is_admin) {
            document.getElementById("nav-admin-btn").classList.remove("hidden");
            document.getElementById("nav-admin-btn-mobile").classList.remove("hidden");
        }
    } catch (e) {
        // kontynuuj bez danych użytkownika
    }
    loadTagsCache();
    loadPopularTagsCache();
    showView("dashboard");

    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (!document.getElementById("receipt-fullscreen").classList.contains("hidden")) {
            closeReceiptFullscreen(); return;
        }
        if (!document.getElementById("expense-modal").classList.contains("hidden")) {
            closeExpenseModal(); return;
        }
        if (!document.getElementById("draft-modal").classList.contains("hidden")) {
            discardDraft(); return;
        }
        if (!document.getElementById("sub-modal")?.classList.contains("hidden")) {
            closeSubModal(); return;
        }
        if (!document.getElementById("change-password-modal")?.classList.contains("hidden")) {
            closeChangePasswordModal(); return;
        }
    });
}

// ==================== TAG MANAGEMENT VIEW ====================
let _tagStatsCache = [];

async function loadTagsView() {
    document.getElementById("tags-management-panel").classList.remove("hidden");
    document.getElementById("tag-detail-panel").classList.add("hidden");
    document.getElementById("tags-loading").classList.remove("hidden");
    document.getElementById("tags-table-wrap").classList.add("hidden");

    try {
        _tagStatsCache = await apiRequest("GET", "/tags/stats");
    } catch (e) {
        showToast(e.message, "error");
        return;
    }

    document.getElementById("tags-loading").classList.add("hidden");
    document.getElementById("tags-table-wrap").classList.remove("hidden");

    const tbody = document.getElementById("tags-table-body");
    const empty = document.getElementById("tags-empty");

    if (!_tagStatsCache.length) {
        empty.classList.remove("hidden");
        tbody.innerHTML = "";
        return;
    }
    empty.classList.add("hidden");

    tbody.innerHTML = _tagStatsCache.map(t => `
        <tr class="hover:bg-gray-50" id="tag-row-${t.id}">
            <td class="px-4 py-3 text-sm font-medium">
                <button onclick="openTagDetail('${escapeHtml(t.name)}')"
                    class="text-primary hover:underline font-medium">#${escapeHtml(t.name)}</button>
            </td>
            <td class="px-4 py-3 text-sm text-gray-600 text-right">${t.expense_count}</td>
            <td class="px-4 py-3 text-sm text-gray-900 font-medium text-right">${t.total_amount.toFixed(2)} zł</td>
            <td class="px-4 py-3 text-right whitespace-nowrap">
                <button onclick="startRenameTag(${t.id}, '${escapeHtml(t.name)}')"
                    class="text-gray-400 hover:text-primary mr-3" title="Zmień nazwę">
                    <i class="fas fa-pen text-xs"></i>
                </button>
                <button onclick="deleteTagFromView(${t.id}, '${escapeHtml(t.name)}')"
                    class="text-gray-400 hover:text-danger" title="Usuń">
                    <i class="fas fa-trash text-xs"></i>
                </button>
            </td>
        </tr>
    `).join("");
}

function startRenameTag(tagId, currentName) {
    const row = document.getElementById(`tag-row-${tagId}`);
    const nameTd = row.querySelector("td:first-child");
    nameTd.innerHTML = `
        <form onsubmit="submitRenameTag(event, ${tagId})" class="flex items-center gap-2">
            <input type="text" value="${escapeHtml(currentName)}" id="rename-input-${tagId}"
                class="border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary w-36"
                onkeydown="if(event.key==='Escape') loadTagsView()" />
            <button type="submit" class="text-success hover:text-green-700 text-xs"><i class="fas fa-check"></i></button>
            <button type="button" onclick="loadTagsView()" class="text-gray-400 hover:text-gray-600 text-xs"><i class="fas fa-times"></i></button>
        </form>`;
    document.getElementById(`rename-input-${tagId}`).focus();
}

async function submitRenameTag(event, tagId) {
    event.preventDefault();
    const input = document.getElementById(`rename-input-${tagId}`);
    const newName = input.value.trim();
    if (!newName) return;
    try {
        await apiRequest("PUT", `/tags/${tagId}`, { name: newName });
        await Promise.all([loadTagsCache(), loadPopularTagsCache()]);
        loadTagsView();
        showToast("Nazwa tagu zmieniona", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteTagFromView(tagId, tagName) {
    if (!confirm(`Usunąć tag #${tagName}? Zostanie odłączony od wszystkich wydatków.`)) return;
    try {
        await apiRequest("DELETE", `/tags/${tagId}`);
        await Promise.all([loadTagsCache(), loadPopularTagsCache()]);
        loadTagsView();
        showToast(`Tag #${tagName} usunięty`, "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ---- Tag detail ----

async function openTagDetail(tagName) {
    document.getElementById("tags-management-panel").classList.add("hidden");
    document.getElementById("tag-detail-panel").classList.remove("hidden");
    document.getElementById("tag-detail-title").textContent = `#${tagName}`;
    document.getElementById("tag-detail-total").textContent = "";
    document.getElementById("tag-detail-categories").innerHTML =
        '<div class="text-sm text-gray-400"><i class="fas fa-spinner fa-spin mr-1"></i>Wczytywanie...</div>';
    document.getElementById("tag-detail-expenses").innerHTML = "";

    let expenses;
    try {
        expenses = await apiRequest("GET", `/tags/expenses?tag=${encodeURIComponent(tagName)}`);
    } catch (e) {
        showToast(e.message, "error");
        return;
    }

    const total = expenses.reduce((s, e) => s + e.amount, 0);
    document.getElementById("tag-detail-total").textContent =
        `${expenses.length} wydatk${expenses.length === 1 ? "" : expenses.length < 5 ? "i" : "ów"} · ${total.toFixed(2)} zł`;

    // Category breakdown
    const catMap = {};
    expenses.forEach(e => {
        const key = e.category_name || "Bez kategorii";
        catMap[key] = (catMap[key] || 0) + e.amount;
    });
    const sorted = Object.entries(catMap).sort((a, b) => b[1] - a[1]);
    const maxVal = sorted[0]?.[1] || 1;
    document.getElementById("tag-detail-categories").innerHTML = sorted.map(([name, amount]) => `
        <div class="flex items-center gap-3">
            <span class="text-sm text-gray-600 w-32 truncate shrink-0">${escapeHtml(name)}</span>
            <div class="flex-1 bg-gray-100 rounded-full h-2">
                <div class="bg-primary h-2 rounded-full" style="width:${(amount / maxVal * 100).toFixed(1)}%"></div>
            </div>
            <span class="text-sm font-medium text-gray-900 w-24 text-right shrink-0">${amount.toFixed(2)} zł</span>
        </div>
    `).join("") || '<p class="text-sm text-gray-400 italic">Brak danych</p>';

    // Expense list
    document.getElementById("tag-detail-expenses").innerHTML = expenses.map(e => `
        <div class="flex items-center justify-between px-4 py-3 hover:bg-gray-50">
            <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 truncate">${escapeHtml(e.description || "Bez opisu")}</p>
                <p class="text-xs text-gray-500">${e.date} · ${e.category_name || "—"}</p>
            </div>
            <div class="flex items-center gap-4 ml-3 shrink-0">
                <span class="text-sm font-semibold text-gray-900">${e.amount.toFixed(2)} zł</span>
                <button onclick="openExpenseModal(${e.id})" class="text-primary hover:text-blue-700 text-xs">
                    <i class="fas fa-pen"></i>
                </button>
            </div>
        </div>
    `).join("") || '<div class="p-4 text-center text-sm text-gray-400">Brak wydatków</div>';
}

function closeTagDetail() {
    document.getElementById("tag-detail-panel").classList.add("hidden");
    document.getElementById("tags-management-panel").classList.remove("hidden");
}

// ==================== ADMIN ====================
// ==================== CHANGE PASSWORD ====================
function openChangePasswordModal() {
    document.getElementById("cp-old").value = "";
    document.getElementById("cp-new").value = "";
    document.getElementById("cp-confirm").value = "";
    document.getElementById("change-password-modal").classList.remove("hidden");
}
function closeChangePasswordModal() {
    document.getElementById("change-password-modal").classList.add("hidden");
}
async function changePassword() {
    const oldPwd = document.getElementById("cp-old").value;
    const newPwd = document.getElementById("cp-new").value;
    const confirmPwd = document.getElementById("cp-confirm").value;
    if (newPwd !== confirmPwd) { showToast("Nowe hasła nie są zgodne", "error"); return; }
    try {
        await apiRequest("POST", "/auth/change-password", { old_password: oldPwd, new_password: newPwd });
        showToast("Hasło zmienione pomyślnie", "success");
        closeChangePasswordModal();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== ADMIN USERS ====================
async function loadAdminUsers() {
    try {
        const users = await apiRequest("GET", "/admin/users");
        const tbody = document.getElementById("admin-users-list");
        tbody.innerHTML = users.map((u) => `
            <tr>
                <td class="px-3 py-2 text-gray-500">${u.id}</td>
                <td class="px-3 py-2 text-gray-900">${u.email}</td>
                <td class="px-3 py-2 text-gray-500">${u.full_name || "—"}</td>
                <td class="px-3 py-2 text-center">${u.is_admin ? '<span class="text-primary font-semibold text-xs">admin</span>' : "—"}</td>
                <td class="px-3 py-2 text-center">${u.force_password_reset ? '<span class="text-warning font-semibold text-xs">tak</span>' : "—"}</td>
                <td class="px-3 py-2 text-center space-x-2 whitespace-nowrap">
                    <button onclick="adminForcePasswordReset(${u.id})" class="text-xs text-warning hover:underline">Resetuj hasło</button>
                    <button onclick="adminDeleteUser(${u.id}, '${u.email}')" class="text-xs text-danger hover:underline">Usuń</button>
                </td>
            </tr>`).join("");
    } catch (e) {
        showToast("Błąd ładowania użytkowników: " + e.message, "error");
    }
}

async function adminForcePasswordReset(userId) {
    if (!confirm("Wymusić reset hasła dla tego użytkownika? Przy kolejnym logowaniu zostanie poproszony o ustawienie nowego hasła.")) return;
    try {
        await apiRequest("POST", `/admin/users/${userId}/force-password-reset`);
        showToast("Wymuszono reset hasła", "success");
        loadAdminUsers();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function adminDeleteUser(userId, email) {
    if (!confirm(`Czy na pewno usunąć użytkownika ${email}? Usunięte zostaną wszystkie jego wydatki i dane.`)) return;
    try {
        await apiRequest("DELETE", `/admin/users/${userId}`);
        showToast("Użytkownik usunięty", "success");
        loadAdminUsers();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function loadAdminConfig() {
    try {
        const cfg = await apiRequest("GET", "/admin/config");
        document.getElementById("cfg-registration-enabled").checked = cfg.registration_enabled;
        document.getElementById("cfg-app-name").value = cfg.app_name;
        document.getElementById("cfg-debug").checked = cfg.debug;
        document.getElementById("cfg-secret-key").value = cfg.SECRET_KEY;
        document.getElementById("cfg-token-expire").value = cfg.ACCESS_TOKEN_EXPIRE_MINUTES;
        document.getElementById("cfg-server-host").value = cfg.server_host;
        document.getElementById("cfg-server-port").value = cfg.server_port;
        document.getElementById("cfg-openrouter-key").value = cfg.openrouter_api_key;
        document.getElementById("cfg-openrouter-model").value = cfg.openrouter_model;
        document.getElementById("cfg-openrouter-max-tokens").value = cfg.openrouter_max_tokens;
        document.getElementById("cfg-openrouter-temperature").value = cfg.openrouter_temperature;
        document.getElementById("cfg-personal-context").value = cfg.personal_context.join("\n");
        document.getElementById("cfg-dup-days").value = cfg.duplicates_date_range_days;
        document.getElementById("cfg-dup-amount").value = cfg.duplicates_amount_threshold;
    } catch (e) {
        showToast("Błąd ładowania konfiguracji: " + e.message, "error");
    }
}

async function saveAdminConfig(event) {
    event.preventDefault();
    const personalContextRaw = document.getElementById("cfg-personal-context").value;
    const personalContext = personalContextRaw
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l.length > 0);

    const payload = {
        registration_enabled: document.getElementById("cfg-registration-enabled").checked,
        app_name: document.getElementById("cfg-app-name").value,
        debug: document.getElementById("cfg-debug").checked,
        SECRET_KEY: document.getElementById("cfg-secret-key").value,
        ACCESS_TOKEN_EXPIRE_MINUTES: parseInt(document.getElementById("cfg-token-expire").value),
        server_host: document.getElementById("cfg-server-host").value,
        server_port: parseInt(document.getElementById("cfg-server-port").value),
        database_url: null, // filled below
        storage_uploads_path: null,
        openrouter_api_key: document.getElementById("cfg-openrouter-key").value,
        openrouter_model: document.getElementById("cfg-openrouter-model").value,
        openrouter_max_tokens: parseInt(document.getElementById("cfg-openrouter-max-tokens").value),
        openrouter_temperature: parseFloat(document.getElementById("cfg-openrouter-temperature").value),
        personal_context: personalContext,
        duplicates_date_range_days: parseInt(document.getElementById("cfg-dup-days").value),
        duplicates_amount_threshold: parseFloat(document.getElementById("cfg-dup-amount").value),
    };

    // pobierz pozostałe pola (database_url, storage) z aktualnej konfiguracji
    try {
        const current = await apiRequest("GET", "/admin/config");
        payload.database_url = current.database_url;
        payload.storage_uploads_path = current.storage_uploads_path;
    } catch (_) {}

    try {
        await apiRequest("PUT", "/admin/config", payload);
        showToast("Konfiguracja zapisana", "success");
    } catch (e) {
        showToast("Błąd zapisu: " + e.message, "error");
    }
}

function toggleApiKeyVisibility() {
    const el = document.getElementById("cfg-openrouter-key");
    el.type = el.type === "password" ? "text" : "password";
}

document.addEventListener("DOMContentLoaded", async () => {
    initReceiptUpload();

    // Dashboard receipt input handled via onchange attribute in HTML

    // Sprawdź status rejestracji i pokaż/ukryj link rejestracji
    try {
        const status = await fetch(`${API_URL}/auth/registration-status`);
        const data = await status.json();
        if (!data.enabled) {
            const regLink = document.querySelector("#login-form p");
            if (regLink) regLink.classList.add("hidden");
        }
    } catch (_) {}

    if (isLoggedIn()) {
        initApp();
    } else {
        showView("login");
    }
});
