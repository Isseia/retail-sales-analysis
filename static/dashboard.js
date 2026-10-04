/* ─── Formatters ─────────────────────────────────────────────────────────── */
const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const money2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

/* ─── Design tokens ──────────────────────────────────────────────────────── */
const palette = {
    primary: "#2563eb",
    success: "#10b981",
    warning: "#f59e0b",
    danger: "#ef4444",
    purple: "#8b5cf6",
    cyan: "#06b6d4",
    slate: "#1e293b",
    muted: "#64748b",
    grid: "#e2e8f0"
};

const COLORS = [
    palette.primary, palette.purple, palette.cyan,
    palette.warning, palette.success, palette.danger
];

const layoutBase = {
    margin: { l: 55, r: 20, t: 25, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, system-ui, -apple-system, sans-serif", color: "#1e293b", size: 12 },
    hoverlabel: { bgcolor: "#1e293b", font: { color: "#fff", size: 12 } }
};

const plotConfig = { responsive: true, displaylogo: false, displayModeBar: false };

/* ─── Helpers ────────────────────────────────────────────────────────────── */
function hexToRgba(hex, alpha = 0.12) {
    if (!hex || !hex.startsWith("#")) return `rgba(37,99,235,${alpha})`;
    const h = hex.replace("#", "");
    const bigint = parseInt(h.length === 3 ? h.split("").map(c => c + c).join("") : h, 16);
    const r = (bigint >> 16) & 255;
    const g = (bigint >> 8) & 255;
    const b = bigint & 255;
    return `rgba(${r},${g},${b},${alpha})`;
}

/* ─── Filter state ───────────────────────────────────────────────────────── */
const state = { start: null, end: null, category: "", channel: "" };
let meta = null;       // /api/filters payload (null = filtering unavailable)
let requestId = 0;     // guards against out-of-order responses

function isFullRange() {
    if (!meta) return true;
    return state.start === meta.months[0] && state.end === meta.months[meta.months.length - 1];
}

function filtersActive() {
    return !!meta && (!isFullRange() || !!state.category || !!state.channel);
}

function queryString() {
    const p = new URLSearchParams();
    if (meta && !isFullRange()) { p.set("start", state.start); p.set("end", state.end); }
    if (state.category) p.set("category", state.category);
    if (state.channel) p.set("channel", state.channel);
    return p.toString();
}

async function api(name, filtered = true) {
    const q = filtered ? queryString() : "";
    const res = await fetch(`/api/${name}${q ? "?" + q : ""}`);
    if (!res.ok) {
        const msg = await res.text().catch(() => res.statusText);
        throw new Error(`API /${name} → ${res.status}: ${msg}`);
    }
    return res.json();
}

function layout(extra = {}) {
    return Object.assign({}, layoutBase, extra);
}

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text ?? "—";
}

function setTrend(elemId, current, prev) {
    const el = document.getElementById(elemId);
    if (!el) return;
    el.className = "";
    if (current == null || prev == null || prev === 0) { el.textContent = "—"; return; }
    const pct = ((current - prev) / Math.abs(prev)) * 100;
    const up = pct >= 0;
    el.className = up ? "trend-up" : "trend-down";
    el.textContent = `${up ? "↑ +" : "↓ "}${Math.abs(pct).toFixed(1)}%`;
}

function renderSparkline(id, values, color = palette.primary) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!values || values.length < 2) { if (el.data) Plotly.purge(el); return; }
    Plotly.newPlot(el, [{
        y: values,
        type: "scatter",
        mode: "lines",
        line: { color, width: 2, shape: "spline" },
        fill: "tozeroy",
        fillcolor: hexToRgba(color, 0.15),
        hoverinfo: "none"
    }], {
        margin: { l: 0, r: 0, t: 2, b: 2 },
        xaxis: { visible: false },
        yaxis: { visible: false },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)"
    }, { staticPlot: true, responsive: true });
}

/* Draws a chart, clearing any "no data" message left by a previous filter */
function plot(id, data, lay, cfg) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.classList.contains("is-empty")) { el.classList.remove("is-empty"); el.innerHTML = ""; }
    Plotly.newPlot(el, data, lay, cfg);
}

function emptyChart(id, msg = "No data for this selection") {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.data) Plotly.purge(el);
    el.classList.add("is-empty");
    el.innerHTML = `<div class="chart-empty">${escapeHtml(msg)}</div>`;
}

/* Click-to-filter: handler receives the clicked Plotly point */
function onPointClick(id, handler) {
    const el = document.getElementById(id);
    if (!el || typeof el.on !== "function") return;
    el.classList.add("clickable");
    if (typeof el.removeAllListeners === "function") el.removeAllListeners("plotly_click");
    el.on("plotly_click", ev => {
        const p = ev && ev.points && ev.points[0];
        if (p) handler(p);
    });
}

function escapeHtml(v) {
    return String(v ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function safeRender(chartName, renderFn) {
    try {
        renderFn();
    } catch (e) {
        console.error(`[Dashboard] Failed to render "${chartName}":`, e);
    }
}

/* ─── KPI cards ──────────────────────────────────────────────────────────── */
function setPeriodLabel(text) {
    document.querySelectorAll(".period-label").forEach(el => { el.textContent = text; });
}

function renderKPIs(k, monthly) {
    if (!k || typeof k !== "object") { console.error("KPI data invalid", k); return; }

    setText("kpi-revenue", money.format(k.total_revenue ?? 0));
    setText("kpi-profit", money.format(k.total_profit ?? 0));
    setText("kpi-orders", fmt.format(k.total_orders ?? 0));
    setText("kpi-customers", fmt.format(k.total_customers ?? 0));
    setText("recordStatus",
        `${fmt.format(k.total_transactions ?? 0)} transactions analyzed${filtersActive() ? " (filtered)" : ""}`);

    const series = Array.isArray(monthly) ? monthly : [];
    const prevPeriod = k.previous;

    if (prevPeriod) {
        /* Date range selected: compare with the equally long period before it */
        setPeriodLabel("vs previous period");
        setTrend("revenue-trend", k.total_revenue, prevPeriod.total_revenue);
        setTrend("profit-trend", k.total_profit, prevPeriod.total_profit);
        setTrend("orders-trend", k.total_orders, prevPeriod.total_orders);
        setTrend("customers-trend", k.total_customers, prevPeriod.total_customers);
    } else {
        /* Otherwise compare the last two months of the series */
        setPeriodLabel("vs last month");
        const last = series[series.length - 1];
        const prev = series[series.length - 2];
        if (last && prev) {
            setTrend("revenue-trend", last.revenue, prev.revenue);
            setTrend("profit-trend", last.profit, prev.profit);
            setTrend("orders-trend", last.orders_count, prev.orders_count);
            setTrend("customers-trend", last.customers_count, prev.customers_count);
        } else {
            ["revenue", "profit", "orders", "customers"].forEach(n => setTrend(`${n}-trend`, null, null));
        }
    }

    const rev = series.map(m => m.revenue ?? 0);
    const prof = series.map(m => m.profit ?? 0);
    const ord = series.map(m => m.orders_count ?? 0);
    /* customers_count needs the updated dashboard.py export; skip the sparkline if absent */
    const cust = series.length && series.every(m => m.customers_count != null)
        ? series.map(m => m.customers_count) : [];

    safeRender("Revenue Sparkline", () => renderSparkline("revenue-sparkline", rev, palette.primary));
    safeRender("Profit Sparkline", () => renderSparkline("profit-sparkline", prof, palette.success));
    safeRender("Orders Sparkline", () => renderSparkline("orders-sparkline", ord, palette.purple));
    safeRender("Customers Sparkline", () => renderSparkline("customers-sparkline", cust, palette.cyan));
}

/* ─── Charts ─────────────────────────────────────────────────────────────── */
function renderTrend(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("trend"); return; }
    const x = data.map(d => d.Year_Month);
    plot("trend", [
        {
            x, y: data.map(d => d.revenue),
            name: "Revenue", type: "scatter", mode: "lines+markers",
            line: { color: palette.primary, width: 2.5 }, marker: { size: 4 }
        },
        {
            x, y: data.map(d => d.profit),
            name: "Profit", type: "scatter", mode: "lines+markers",
            yaxis: "y2",
            line: { color: palette.success, width: 2.5 }, marker: { size: 4 }
        }
    ], layout({
        hovermode: "x unified",
        margin: { l: 65, r: 65, t: 35, b: 50 },
        xaxis: { gridcolor: palette.grid, tickangle: -45 },
        yaxis: { title: "Revenue ($)", gridcolor: palette.grid },
        yaxis2: { title: "Profit ($)", overlaying: "y", side: "right", showgrid: false },
        legend: { orientation: "h", y: 1.15, x: 0 }
    }), plotConfig);
}

function renderCategories(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("categories"); return; }
    const d = [...data].sort((a, b) => b.revenue - a.revenue);
    const sel = state.category;
    plot("categories", [{
        x: d.map(r => r.revenue),
        y: d.map(r => r.Product_Category),
        type: "bar", orientation: "h",
        marker: { color: d.map((r, i) => (!sel || r.Product_Category === sel) ? COLORS[i % COLORS.length] : "#cbd5e1") },
        text: d.map(r => money.format(r.revenue)),
        textposition: "auto"
    }], layout({
        margin: { l: 120, r: 25, t: 20, b: 45 },
        xaxis: { title: "Revenue ($)", gridcolor: palette.grid },
        yaxis: { automargin: true, autorange: "reversed" }
    }), plotConfig);
    if (meta) onPointClick("categories", p => toggleFilter("category", p.y));
}

function renderChannels(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("channels"); return; }
    const sel = state.channel;
    plot("channels", [{
        labels: data.map(r => r.Sales_Channel),
        values: data.map(r => r.revenue),
        type: "pie",
        hole: 0.52,
        marker: { colors: data.map((r, i) => (!sel || r.Sales_Channel === sel) ? COLORS[i % COLORS.length] : "#cbd5e1") },
        pull: data.map(r => (sel && r.Sales_Channel === sel) ? 0.06 : 0),
        textinfo: "label+percent"
    }], layout({ showlegend: false, margin: { l: 10, r: 10, t: 15, b: 10 } }), plotConfig);
    if (meta) onPointClick("channels", p => toggleFilter("channel", p.label));
}

function renderRegions(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("regions"); return; }
    const d = [...data].sort((a, b) => b.revenue - a.revenue).slice(0, 10);
    plot("regions", [{
        x: d.map(r => r.revenue),
        y: d.map(r => `${r.Country} — ${r.Region}`),
        type: "bar", orientation: "h",
        marker: { color: palette.primary },
        text: d.map(r => money.format(r.revenue)),
        textposition: "auto"
    }], layout({
        margin: { l: 160, r: 20, t: 20, b: 45 },
        xaxis: { title: "Revenue ($)", gridcolor: palette.grid },
        yaxis: { automargin: true, autorange: "reversed" }
    }), plotConfig);
}

function renderSegments(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("segments"); return; }
    const d = [...data].sort((a, b) => b.revenue - a.revenue);
    plot("segments", [{
        x: d.map(r => r.Customer_Segment),
        y: d.map(r => r.revenue),
        type: "bar",
        marker: { color: COLORS },
        text: d.map(r => money.format(r.revenue)),
        textposition: "auto"
    }], layout({
        margin: { l: 60, r: 20, t: 20, b: 45 },
        yaxis: { title: "Revenue ($)", gridcolor: palette.grid },
        xaxis: { automargin: true }
    }), plotConfig);
}

function renderPayments(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("payments"); return; }
    plot("payments", [{
        labels: data.map(r => r.Payment_Method),
        values: data.map(r => r.transaction_count),
        type: "pie",
        hole: 0.45,
        marker: {
            /* cycle the palette; "Other" always gets a neutral gray */
            colors: data.map((r, i) => r.Payment_Method === "Other" ? "#94a3b8" : COLORS[i % COLORS.length])
        },
        textinfo: "percent",       /* names are in the legend, so keep slice labels short */
        textposition: "auto",      /* small slices put their % outside */
        automargin: true           /* reserve room so outside labels never get clipped */
    }], layout({ showlegend: true, margin: { l: 20, r: 20, t: 25, b: 25 } }), plotConfig);
}

function renderDemographics(data) {
    if (!Array.isArray(data) || data.length === 0) { emptyChart("demographics"); return; }
    const ageOrder = ["<25", "25-34", "35-49", "50+"];
    const allAges = [...new Set(data.map(r => r.Age_Group))];
    const ages = ageOrder.filter(a => allAges.includes(a))
        .concat(allAges.filter(a => !ageOrder.includes(a)));
    const genders = [...new Set(data.map(r => r.Customer_Gender))];

    const traces = genders.map((g, i) => ({
        x: ages,
        y: ages.map(a => {
            const row = data.find(r => r.Age_Group === a && r.Customer_Gender === g);
            return row ? (row.revenue ?? 0) : 0;
        }),
        name: g,
        type: "bar",
        marker: { color: COLORS[i % COLORS.length] }
    }));

    plot("demographics", traces, layout({
        barmode: "group",
        margin: { l: 65, r: 20, t: 35, b: 50 },
        yaxis: { title: "Revenue ($)", gridcolor: palette.grid },
        xaxis: { title: "Age Group" },
        legend: { orientation: "h", y: 1.12 }
    }), plotConfig);
}

function renderProducts(data) {
    const body = document.getElementById("productTable");
    if (!body) return;
    if (!Array.isArray(data) || data.length === 0) {
        body.innerHTML = '<tr><td colspan="7" class="chart-empty-row">No data for this selection</td></tr>';
        return;
    }
    body.innerHTML = data.map((p) => `
        <tr>
            <td><strong>${escapeHtml(p.Product_Name)}</strong><br>
                <small style="color:#64748b">${escapeHtml(p.Product_ID)}</small></td>
            <td>${escapeHtml(p.Product_Category)}</td>
            <td>${money.format(p.revenue ?? 0)}</td>
            <td>${money.format(p.profit ?? 0)}</td>
            <td>${fmt.format(p.units_sold ?? 0)}</td>
            <td>⭐ ${Number(p.avg_rating ?? 0).toFixed(1)}</td>
            <td><strong>${Number(p.profit_margin_pct ?? 0).toFixed(1)}%</strong></td>
        </tr>`).join("");
}

function renderReturnReasons(data) {
    const d = data?.return_reasons;
    if (!Array.isArray(d) || d.length === 0) { emptyChart("returnReasons"); return; }
    const sorted = [...d].sort((a, b) => b.return_count - a.return_count);
    plot("returnReasons", [{
        labels: sorted.map(r => r.Return_Reason),
        values: sorted.map(r => r.return_count),
        type: "pie",
        hole: 0.45,
        marker: { colors: COLORS },
        textinfo: "label+percent"
    }], layout({ showlegend: false, margin: { l: 10, r: 10, t: 15, b: 10 } }), plotConfig);
}

function renderDeliverySpeed(data) {
    const d = data?.delivery_speed;
    if (!Array.isArray(d) || d.length === 0) { emptyChart("deliverySpeed"); return; }
    plot("deliverySpeed", [{
        x: d.map(r => r.Delivery_Speed_Category),
        y: d.map(r => r.count),
        type: "bar",
        marker: { color: COLORS }
    }], layout({
        margin: { l: 60, r: 20, t: 20, b: 45 },
        yaxis: { title: "Orders", gridcolor: palette.grid },
        xaxis: { automargin: true }
    }), plotConfig);
}

function renderShipping(data) {
    const d = data?.shipping_methods;
    if (!Array.isArray(d) || d.length === 0) { emptyChart("shipping"); return; }
    plot("shipping", [{
        x: d.map(r => r.Shipping_Method),
        y: d.map(r => r.avg_days),
        type: "bar",
        marker: { color: palette.warning },
        text: d.map(r => `${Number(r.avg_days).toFixed(1)} d`),
        textposition: "auto"
    }], layout({
        margin: { l: 60, r: 20, t: 20, b: 45 },
        yaxis: { title: "Avg Delivery Days", gridcolor: palette.grid },
        xaxis: { automargin: true }
    }), plotConfig);
}

/* ─── Navigation ─────────────────────────────────────────────────────────── */
function setupNav() {
    const links = document.querySelectorAll(".nav a");
    const sections = document.querySelectorAll("main section[id]");

    /* Click-based active state */
    links.forEach(link => {
        link.addEventListener("click", () => {
            links.forEach(l => l.classList.remove("active"));
            link.classList.add("active");
        });
    });

    /* Scroll-based active state using IntersectionObserver */
    if ("IntersectionObserver" in window && sections.length) {
        const obs = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = entry.target.id;
                    links.forEach(l => {
                        l.classList.toggle("active", l.getAttribute("href") === `#${id}`);
                    });
                }
            });
        }, { threshold: 0.35 });
        sections.forEach(s => obs.observe(s));
    }
}

/* ─── Filters UI ─────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);

function monthLabel(ym) {
    const [y, m] = ym.split("-").map(Number);
    return new Date(y, m - 1, 1).toLocaleString("en-US", { month: "short", year: "numeric" });
}

function fillSelect(sel, options, allLabel) {
    sel.innerHTML = "";
    if (allLabel != null) sel.add(new Option(allLabel, ""));
    options.forEach(([value, text]) => sel.add(new Option(text, value)));
}

function defaultState() {
    return { start: meta.months[0], end: meta.months[meta.months.length - 1], category: "", channel: "" };
}

function presetStart(n) {
    return n === "all" ? meta.months[0] : meta.months[Math.max(0, meta.months.length - Number(n))];
}

function syncControls() {
    $("fltFrom").value = state.start;
    $("fltTo").value = state.end;
    $("fltCategory").value = state.category;
    $("fltChannel").value = state.channel;

    const last = meta.months[meta.months.length - 1];
    $("presetGroup").querySelectorAll("[data-months]").forEach(btn => {
        btn.classList.toggle("active", state.end === last && state.start === presetStart(btn.dataset.months));
    });

    const chips = [];
    if (state.category) chips.push(["category", `Category: ${state.category}`]);
    if (state.channel) chips.push(["channel", `Channel: ${state.channel}`]);
    $("filterChips").innerHTML = chips.map(([key, text]) =>
        `<button type="button" class="chip" data-clear="${key}" title="Remove filter">${escapeHtml(text)} <span aria-hidden="true">✕</span></button>`
    ).join("");

    $("fltReset").hidden = !filtersActive();
}

function applyFilters() {
    syncControls();
    loadDashboard();
}

function toggleFilter(key, value) {
    state[key] = state[key] === value ? "" : value;
    applyFilters();
}

function setupFilters() {
    const months = meta.months;
    const monthOpts = months.map(m => [m, monthLabel(m)]);
    fillSelect($("fltFrom"), monthOpts);
    fillSelect($("fltTo"), monthOpts);
    fillSelect($("fltCategory"), meta.categories.map(c => [c, c]), "All categories");
    fillSelect($("fltChannel"), meta.channels.map(c => [c, c]), "All channels");
    Object.assign(state, defaultState());

    $("fltFrom").addEventListener("change", e => {
        state.start = e.target.value;
        if (state.start > state.end) state.end = state.start;
        applyFilters();
    });
    $("fltTo").addEventListener("change", e => {
        state.end = e.target.value;
        if (state.end < state.start) state.start = state.end;
        applyFilters();
    });
    $("fltCategory").addEventListener("change", e => { state.category = e.target.value; applyFilters(); });
    $("fltChannel").addEventListener("change", e => { state.channel = e.target.value; applyFilters(); });

    $("presetGroup").querySelectorAll("[data-months]").forEach(btn => {
        btn.addEventListener("click", () => {
            state.end = months[months.length - 1];
            state.start = presetStart(btn.dataset.months);
            applyFilters();
        });
    });

    $("filterChips").addEventListener("click", e => {
        const chip = e.target.closest("[data-clear]");
        if (chip) { state[chip.dataset.clear] = ""; applyFilters(); }
    });

    $("fltReset").addEventListener("click", () => { Object.assign(state, defaultState()); applyFilters(); });

    $("filterBar").hidden = false;
    document.body.classList.add("filters-on");
    syncControls();
}

/* ─── Load + render everything for the current filters ──────────────────── */
async function loadDashboard() {
    const myId = ++requestId;
    document.body.classList.add("is-loading");
    try {
        const [kpis, monthly, categories, regional, channels,
            segments, demographics, payments, products, fulfillment]
            = await Promise.all([
                api("kpis"), api("monthly"), api("categories"),
                api("regional"), api("channels"), api("segments"),
                api("demographics"), api("payments"),
                api("products"), api("fulfillment")
            ]);

        if (myId !== requestId) return;   // a newer selection superseded this response

        safeRender("KPIs", () => renderKPIs(kpis, monthly));
        safeRender("Revenue & Profit", () => renderTrend(monthly));
        safeRender("Categories", () => renderCategories(categories));
        safeRender("Regional", () => renderRegions(regional));
        safeRender("Channels", () => renderChannels(channels));
        safeRender("Segments", () => renderSegments(segments));
        safeRender("Demographics", () => renderDemographics(demographics));
        safeRender("Payments", () => renderPayments(payments));
        safeRender("Products", () => renderProducts(products));
        safeRender("Return Reasons", () => renderReturnReasons(fulfillment));
        safeRender("Delivery Speed", () => renderDeliverySpeed(fulfillment));
        safeRender("Shipping Methods", () => renderShipping(fulfillment));
    } catch (err) {
        if (myId !== requestId) return;
        console.error("[Dashboard] Load failed:", err);
        setText("recordStatus", "⚠ Could not load data — check console (F12)");
    } finally {
        if (myId === requestId) document.body.classList.remove("is-loading");
    }
}

/* ─── Main init ──────────────────────────────────────────────────────────── */
async function init() {
    if (typeof Plotly === "undefined") {
        console.warn("[Dashboard] Plotly not loaded yet, retrying in 100ms...");
        setTimeout(init, 100);
        return;
    }

    setupNav();

    /* Filters are optional: if the API can't provide them, the dashboard works unfiltered */
    try {
        const info = await api("filters", false);
        if (info && info.enabled && Array.isArray(info.months) && info.months.length) {
            meta = info;
            setupFilters();
        } else {
            console.info("[Dashboard] Filters disabled:", info && info.reason);
        }
    } catch (err) {
        console.warn("[Dashboard] Filters unavailable:", err);
    }

    await loadDashboard();

    /* Re-render Lucide icons after the first paint */
    setTimeout(() => {
        if (window.lucide && typeof lucide.createIcons === "function") lucide.createIcons();
    }, 100);
}

/* ─── Boot ───────────────────────────────────────────────────────────────── */
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}