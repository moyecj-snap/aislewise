const API_URL = window.WINE_AISLE_API_URL || "";

const demoBottles = [
  {
    display_name: "Kirkland Signature Rioja Reserva",
    producer: "Kirkland Signature",
    price: 12.99,
    varietal: "Tempranillo",
    score: 94,
    rating_estimate: 4.1,
    badge: "Best Value",
    confidence_label: "High confidence",
    style: "Medium-bodied, smooth, earthy cherry",
    reasons: [
      "Under your selected budget",
      "Great with steak, burgers, and grilled food",
      "Reliable crowd-pleaser for a casual dinner"
    ]
  },
  {
    display_name: "Decoy Cabernet Sauvignon",
    producer: "Decoy",
    price: 19.99,
    varietal: "Cabernet Sauvignon",
    score: 89,
    rating_estimate: 4.0,
    badge: "Safer Pick",
    confidence_label: "Medium-high confidence",
    style: "Full-bodied, dark fruit, polished finish",
    reasons: [
      "Familiar brand for guests",
      "Good gift or dinner-table bottle",
      "Pairs well with red meat and rich pasta"
    ]
  },
  {
    display_name: "La Crema Pinot Noir",
    producer: "La Crema",
    price: 22.99,
    varietal: "Pinot Noir",
    score: 72,
    rating_estimate: 3.9,
    badge: "Over Budget",
    confidence_label: "Lower match",
    style: "Light-medium, cherry, silky",
    reasons: [
      "Good wine, but above your selected budget",
      "Better for chicken or salmon than steak",
      "Useful backup if you want a lighter red"
    ]
  }
];

const state = {
  screen: "start",
  budget: "$20",
  food: "Steak",
  occasion: "Dinner party",
  photo: null,
  photoPreview: "",
  detected: [],
  recommendations: [],
  selected: null,
  loading: false,
  error: ""
};

const options = {
  budget: ["$15", "$20", "$30+"],
  food: ["Steak", "Chicken", "Pasta", "Cheese", "Seafood", "None"],
  occasion: ["Weeknight", "Date night", "Gift", "Dinner party"]
};

const screen = document.querySelector("#screen");

initAnalytics();

function setChoice(key, value) {
  state[key] = value;
  track("filter_changed", { filter_name: key, filter_value: value });
  render();
}

function goTo(screenName) {
  state.screen = screenName;
  state.error = "";
  state.selected = null;
  track("screen_view", { screen_name: screenName });
  render();
}

function choosePhoto(input, method = "upload") {
  const file = input.files?.[0];
  if (!file) return;

  state.photo = file;
  const reader = new FileReader();
  reader.onload = () => {
    state.photoPreview = reader.result;
    state.error = "";
    track("photo_selected", {
      method,
      file_type: file.type || "unknown",
      file_size: file.size || 0
    });
    render();
  };
  reader.readAsDataURL(file);
}

async function recommend() {
  state.loading = true;
  state.error = "";
  track("recommendation_requested", {
    has_photo: Boolean(state.photo),
    budget: state.budget,
    food: state.food,
    occasion: state.occasion
  });
  render();

  try {
    const response = await callRecommendationApi();
    state.detected = response.detected_wines?.length ? response.detected_wines : demoBottles;
    state.recommendations = response.recommendations?.length
      ? response.recommendations
      : demoBottles.slice(0, 2);
    state.error = response.warnings?.length ? response.warnings[0] : "";
    state.screen = "results";
    track("recommendation_received", {
      source: response.source || "unknown",
      recommendation_count: state.recommendations.length,
      warning_count: response.warnings?.length || 0
    });
  } catch (error) {
    state.detected = demoBottles;
    state.recommendations = demoBottles.slice(0, 2);
    state.screen = "results";
    state.error = "Showing starter recommendations because the live scan did not finish. Try another photo or scan again.";
    track("recommendation_failed", { message: error.message || "unknown" });
  } finally {
    state.loading = false;
    render();
  }
}

async function callRecommendationApi() {
  const endpoint = `${API_URL}/api/recommend`;
  const form = new FormData();
  form.append("budget", state.budget);
  form.append("food", state.food);
  form.append("occasion", state.occasion);
  if (state.photo) form.append("photo", state.photo);

  const response = await fetch(endpoint, {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    throw new Error(`Recommendation API failed with ${response.status}`);
  }

  return response.json();
}

function openDetail(index) {
  state.selected = state.recommendations[index];
  track("recommendation_opened", {
    rank: index + 1,
    wine_name: state.selected?.display_name || state.selected?.name || "unknown"
  });
  render();
}

function closeDetail() {
  state.selected = null;
  render();
}

function choiceButton(key, value, soft = false) {
  const active = state[key] === value ? (soft ? "is-soft-active" : "is-active") : "";
  return `<button class="choice ${active}" type="button" onclick="setChoice('${key}', '${value}')">${value}</button>`;
}

function priceText(item) {
  if (item.price) return `$${Number(item.price).toFixed(2)}`;
  if (item.avg_price) return `$${Number(item.avg_price).toFixed(2)} avg`;
  return "Price unknown";
}

function renderStart() {
  return `
    <div class="intro-panel">
      <h2>Find a bottle that fits tonight.</h2>
      <p>Pick your budget, meal, and occasion. Then scan the shelf or upload a bottle photo.</p>
    </div>

    <div class="field-group">
      <div class="field-label"><span aria-hidden="true">$</span> Budget</div>
      <div class="segmented">
        ${options.budget.map((item) => choiceButton("budget", item)).join("")}
      </div>
    </div>

    <div class="field-group">
      <div class="field-label"><span aria-hidden="true">F</span> Food pairing</div>
      <div class="chip-row">
        ${options.food.map((item) => choiceButton("food", item)).join("")}
      </div>
    </div>

    <div class="field-group">
      <div class="field-label"><span aria-hidden="true">O</span> Occasion</div>
      <div class="occasion-grid">
        ${options.occasion.map((item) => choiceButton("occasion", item, true)).join("")}
      </div>
    </div>

    <button class="primary-action" type="button" onclick="goTo('scan')">
      Scan shelf or bottle <span aria-hidden="true">CAM</span>
    </button>
  `;
}

function renderScan() {
  const preview = state.photoPreview
    ? `<img class="photo-preview" src="${state.photoPreview}" alt="Selected wine shelf" />`
    : renderDemoShelf();

  return `
    <div class="scan-stage">
      ${preview}
      <p class="scan-caption">
        <span>${state.photo ? "Photo ready" : "Demo shelf shown"}</span>
        <span>Photo-based inventory</span>
      </p>
    </div>

    <div class="photo-actions">
      <label class="upload-target">
        <input type="file" accept="image/*" capture="environment" onchange="choosePhoto(this, 'camera')" />
        <span>Take a photo</span>
        <small>Open camera</small>
      </label>
      <label class="upload-target">
        <input type="file" accept="image/*" onchange="choosePhoto(this, 'library')" />
        <span>Upload from phone</span>
        <small>Use library</small>
      </label>
    </div>

    <div class="detected-list">
      ${demoBottles
        .map(
          (bottle) => `
            <div class="detected-item">
              <div>
                <strong>${bottle.display_name}</strong>
                <span>${bottle.varietal} · ${priceText(bottle)}</span>
              </div>
              <span class="check" aria-label="Demo bottle">✓</span>
            </div>
          `
        )
        .join("")}
    </div>

    ${state.error ? `<p class="inline-error">${state.error}</p>` : ""}

    <button class="primary-action" type="button" onclick="recommend()" ${state.loading ? "disabled" : ""}>
      ${state.loading ? "Checking the photo..." : "Find the best pick"} <span aria-hidden="true">*</span>
    </button>
  `;
}

function renderDemoShelf() {
  return `
    <div class="shelf" aria-label="Simulated shelf photo">
      ${demoBottles
        .map(
          (bottle, index) => `
            <div class="shelf-slot">
              <div class="price-tag">${priceText(bottle)}</div>
              <div class="bottle" style="height: ${index === 1 ? 238 : 210}px">
                <div class="bottle-label">${bottle.varietal}</div>
              </div>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderResults() {
  return `
    <div class="filters" aria-label="Selected filters">
      <span>Budget ${state.budget}</span>
      <span>${state.food}</span>
      <span>${state.occasion}</span>
    </div>

    ${state.error ? `<p class="inline-error">${state.error}</p>` : ""}

    <h2 class="screen-title">Buy this one</h2>
    <div class="result-list">
      ${state.recommendations
        .slice(0, 2)
        .map(
          (bottle, index) => `
            <button class="result-card ${index === 0 ? "top" : ""}" type="button" onclick="openDetail(${index})">
              <div class="result-head">
                <div>
                  <div class="badge-row">
                    <span class="badge ${index === 0 ? "gold" : ""}">${index === 0 ? "Top pick" : "Backup"}</span>
                    <span class="badge">${bottle.badge || bottle.confidence_label || "Good fit"}</span>
                  </div>
                  <h3>${bottle.display_name || bottle.name}</h3>
                  <div class="subtle">${bottle.varietal || "Wine"} · ${priceText(bottle)}</div>
                </div>
                <div class="match">
                  <strong>${Math.round(bottle.score || bottle.match || 80)}</strong>
                  <span>match</span>
                </div>
              </div>
              <p class="reason">${(bottle.reasons || bottle.why || []).slice(0, 2).join(". ")}.</p>
              <p class="reason">Rated ${bottle.rating_estimate || bottle.rating || "N/A"} estimate · ${bottle.confidence_label || "Photo match"}</p>
            </button>
          `
        )
        .join("")}
    </div>

    <button class="secondary-action" type="button" onclick="goTo('start')">
      Start over <span aria-hidden="true">RESET</span>
    </button>
  `;
}

function renderDetail() {
  if (!state.selected) return "";

  const reasons = state.selected.reasons || state.selected.why || [];
  return `
    <div class="drawer-backdrop" onclick="closeDetail()">
      <section class="drawer" aria-modal="true" role="dialog" onclick="event.stopPropagation()">
        <div class="drawer-head">
          <div>
            <p class="eyebrow">Recommendation detail</p>
            <h2>${state.selected.display_name || state.selected.name}</h2>
            <p class="subtle">${state.selected.style || "Matched from the bottles detected in your photo."}</p>
          </div>
          <button class="close-button" type="button" aria-label="Close detail" onclick="closeDetail()">×</button>
        </div>
        <div class="detail-list">
          ${reasons
            .map(
              (reason) => `
                <div class="detail-item">
                  <span class="check" aria-hidden="true">✓</span>
                  <span>${reason}</span>
                </div>
              `
            )
            .join("")}
        </div>
        <div class="trust-note">
          <span aria-hidden="true">i</span>
          <span>Based on bottles detected in your photo, not claimed full-store inventory.</span>
        </div>
      </section>
    </div>
  `;
}

function render() {
  const screens = {
    start: renderStart,
    scan: renderScan,
    results: renderResults
  };

  screen.innerHTML = screens[state.screen]() + renderDetail();
}

render();

function initAnalytics() {
  const measurementId = window.GA_MEASUREMENT_ID;
  if (!measurementId) return;

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", measurementId);
}

function track(eventName, params = {}) {
  if (typeof window.gtag === "function") {
    window.gtag("event", eventName, params);
  }
}
