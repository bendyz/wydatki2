// ==================== STATE ====================
const API_URL = "/api/v1";
let currentDraft = null;
let categoriesCache = [];
let currentEditingExpenseId = null;
let currentExpenses = [];

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
    showView("login");
    document.getElementById("navbar").classList.add("hidden");
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
    try {
        const expenses = await apiRequest("GET", "/expenses/?limit=100");
        const subs = await apiRequest("GET", "/subscriptions/?active_only=true");
        currentExpenses = expenses;

        const monthTotal = expenses.reduce((sum, e) => sum + e.amount, 0);
        document.getElementById("stat-month-total").textContent = monthTotal.toFixed(2) + " zł";
        document.getElementById("stat-count").textContent = expenses.length;
        document.getElementById("stat-subs").textContent = subs.length;

        renderExpenses(expenses);
        loadCategoriesSelect("filter-category");
    } catch (e) {
        showToast(e.message, "error");
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
            <td class="px-4 py-3 text-sm text-gray-900">${e.description || "-"}</td>
            <td class="px-4 py-3 text-sm text-gray-500">${e.category_name || "-"}</td>
            <td class="px-4 py-3 text-sm text-gray-900 text-right font-medium">${e.amount.toFixed(2)} zł</td>
            <td class="px-4 py-3 text-center text-sm">
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
                </div>
                <div class="text-right ml-3">
                    <p class="text-sm font-bold text-gray-900">${e.amount.toFixed(2)} zł</p>
                    <div class="mt-1">
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
    const start = document.getElementById("filter-start").value;
    const end = document.getElementById("filter-end").value;
    const cat = document.getElementById("filter-category").value;
    let url = "/expenses/?limit=100";
    if (start) url += `&start_date=${start}`;
    if (end) url += `&end_date=${end}`;
    if (cat) url += `&category_id=${cat}`;

    try {
        const expenses = await apiRequest("GET", url);
        renderExpenses(expenses);
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteExpense(id) {
    if (!confirm("Usunąć wydatek?")) return;
    try {
        await apiRequest("DELETE", `/expenses/${id}`);
        loadDashboard();
        showToast("Wydatek usunięty", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================== EXPENSE MODAL (EDIT / VIEW) ====================
function openExpenseModal(expenseId) {
    const expense = currentExpenses.find((e) => e.id === expenseId);
    if (!expense) return;
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

    document.getElementById("expense-modal").classList.remove("hidden");
}

function closeExpenseModal() {
    document.getElementById("expense-modal").classList.add("hidden");
    currentEditingExpenseId = null;
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
        showToast("Wydatek zaktualizowany!", "success");
        closeExpenseModal();
        loadDashboard();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteExpenseModal() {
    if (!currentEditingExpenseId) return;
    if (!confirm("Usunąć wydatek?")) return;
    try {
        await apiRequest("DELETE", `/expenses/${currentEditingExpenseId}`);
        closeExpenseModal();
        loadDashboard();
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

// ==================== RECEIPT UPLOAD ====================
const uploadArea = document.getElementById("receipt-upload-area");
const fileInput = document.getElementById("receipt-file-input");
if (uploadArea) {
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
}
if (fileInput) {
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
    const file = fileInput.files[0];
    if (!file) return showToast("Wybierz zdjęcie", "warning");

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

// ==================== DRAFT REVIEW ====================
function showDraft(draft) {
    currentDraft = draft;
    document.getElementById("draft-panel").classList.remove("hidden");

    document.getElementById("draft-amount").value = draft.amount;
    document.getElementById("draft-date").value = draft.date;
    document.getElementById("draft-description").value = draft.description || "";

    const dupDiv = document.getElementById("draft-duplicates");
    if (draft.duplicate_warnings && draft.duplicate_warnings.length) {
        dupDiv.classList.remove("hidden");
        document.getElementById("draft-duplicates-list").innerHTML = draft.duplicate_warnings
            .map((d) => `<div class="text-sm text-yellow-700"><i class="fas fa-exclamation-circle mr-1"></i>${escapeHtml(d.message)}</div>`)
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

    if (draft.user_hints && draft.user_hints.length) {
        draft.user_hints.forEach((h) => showToast(h, "warning"));
    }
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
        items.push({
            name: inputs[0].value,
            price: parseFloat(inputs[1].value),
            quantity: parseFloat(inputs[2].value),
            category_id: inputs[3].value || null,
        });
    });

    const data = {
        amount: parseFloat(document.getElementById("draft-amount").value),
        date: document.getElementById("draft-date").value,
        description: document.getElementById("draft-description").value,
        category_id: document.getElementById("draft-category").value || null,
        items: items,
    };

    try {
        await apiRequest("POST", "/expenses/", data);
        showToast("Wydatek zapisany!", "success");
        discardDraft();
        showView("dashboard");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function discardDraft() {
    currentDraft = null;
    document.getElementById("draft-panel").classList.add("hidden");
    document.getElementById("receipt-upload-area").classList.remove("hidden");
    document.getElementById("receipt-preview").classList.add("hidden");
    document.getElementById("text-expense-input").value = "";
}

// ==================== CATEGORIES ====================
async function loadCategories() {
    try {
        const cats = await apiRequest("GET", "/categories/?include_global=true");
        categoriesCache = cats;
        const tbody = document.getElementById("categories-list");
        tbody.innerHTML = cats.map((c) => `
            <tr>
                <td class="px-4 py-3 text-sm text-gray-900">${escapeHtml(c.name)}</td>
                <td class="px-4 py-3 text-right text-sm">
                    ${c.user_id ? `<button onclick="deleteCategory(${c.id})" class="text-danger hover:text-red-700"><i class="fas fa-trash"></i></button>` : '<span class="text-gray-400 text-xs">globalna</span>'}
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
        console.error("Błąd ładowania kategorii:", e);
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

// ==================== SUBSCRIPTIONS ====================
async function loadSubscriptions() {
    try {
        const subs = await apiRequest("GET", "/subscriptions/");
        const tbody = document.getElementById("subscriptions-list");
        tbody.innerHTML = subs.map((s) => `
            <tr>
                <td class="px-4 py-3 text-sm text-gray-900">${escapeHtml(s.name)}</td>
                <td class="px-4 py-3 text-sm text-gray-900 text-right">${s.amount.toFixed(2)} zł</td>
                <td class="px-4 py-3 text-sm text-gray-500">${s.next_billing_date}</td>
                <td class="px-4 py-3 text-right text-sm">
                    <button onclick="deleteSubscription(${s.id})" class="text-danger hover:text-red-700"><i class="fas fa-trash"></i></button>
                </td>
            </tr>
        `).join("");
        loadCategoriesSelect("sub-category");
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
    const start = document.getElementById("stats-start").value;
    const end = document.getElementById("stats-end").value;
    let url = "/stats/";
    if (start) url += `?start_date=${start}`;
    if (end) url += `${start ? "&" : "?"}end_date=${end}`;

    try {
        const data = await apiRequest("GET", url);

        document.getElementById("stats-total").textContent = data.total_amount.toFixed(2) + " zł";
        document.getElementById("stats-count").textContent = data.total_count;
        document.getElementById("stats-avg-day").textContent = (data.average_per_day || 0).toFixed(2) + " zł";
        document.getElementById("stats-avg-exp").textContent = data.average_per_expense.toFixed(2) + " zł";

        const tbody = document.getElementById("stats-monthly-list");
        if (data.monthly_summary && data.monthly_summary.length) {
            tbody.innerHTML = data.monthly_summary.map((m) => `
                <tr>
                    <td class="px-4 py-3 text-sm text-gray-900">${m.month_name} ${m.year}</td>
                    <td class="px-4 py-3 text-sm text-gray-900 text-right font-medium">${m.total_amount.toFixed(2)} zł</td>
                    <td class="px-4 py-3 text-sm text-gray-500 text-right">${m.expense_count}</td>
                </tr>
            `).join("");
        } else {
            tbody.innerHTML = '<tr><td colspan="3" class="px-6 py-4 text-center text-gray-500">Brak danych</td></tr>';
        }

        const catCtx = document.getElementById("chart-categories").getContext("2d");
        if (categoryChart) categoryChart.destroy();
        categoryChart = new Chart(catCtx, {
            type: "doughnut",
            data: {
                labels: data.category_summary.map((c) => c.category_name),
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

        const dailyCtx = document.getElementById("chart-daily").getContext("2d");
        if (dailyChart) dailyChart.destroy();
        dailyChart = new Chart(dailyCtx, {
            type: "line",
            data: {
                labels: data.daily_expenses.map((d) => d.date),
                datasets: [{
                    label: "Kwota (zł)",
                    data: data.daily_expenses.map((d) => d.amount),
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59, 130, 246, 0.1)",
                    fill: true,
                    tension: 0.3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: { y: { beginAtZero: true } },
            },
        });
    } catch (e) {
        showToast(e.message, "error");
    }
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
function initApp() {
    document.getElementById("navbar").classList.remove("hidden");
    showView("dashboard");
}

document.addEventListener("DOMContentLoaded", () => {
    if (isLoggedIn()) {
        initApp();
    } else {
        showView("login");
    }
});
