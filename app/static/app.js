document.documentElement.classList.add("js");

function captureUiState() {
  const wahlDetails = document.querySelector(".wahl-card .wahl-details");
  return {
    wahlDetailsOpen: wahlDetails instanceof HTMLElement ? !wahlDetails.hidden : false,
  };
}

function restoreUiState(state) {
  if (!state?.wahlDetailsOpen) {
    return;
  }

  const card = document.querySelector(".wahl-card");
  const details = card ? card.querySelector(".wahl-details") : null;
  const toggle = card ? card.querySelector("[data-toggle-wahl-details]") : null;
  if (!(details instanceof HTMLElement) || !(toggle instanceof HTMLButtonElement)) {
    return;
  }

  details.hidden = false;
  toggle.setAttribute("aria-expanded", "true");
  toggle.textContent = "Hide details";
}

async function replaceMainFromResponse(response, scrollY) {
  const uiState = captureUiState();
  const html = await response.text();
  const parser = new DOMParser();
  const nextDocument = parser.parseFromString(html, "text/html");
  const nextMain = nextDocument.querySelector("main.page-shell");
  const currentMain = document.querySelector("main.page-shell");

  if (!nextMain || !currentMain) {
    return false;
  }

  currentMain.innerHTML = nextMain.innerHTML;
  restoreUiState(uiState);
  document.title = nextDocument.title;
  if (response.url) {
    window.history.replaceState({}, "", response.url);
  }
  window.requestAnimationFrame(() => {
    window.scrollTo(0, scrollY);
  });
  return true;
}

function applyImmediateButtonFeedback(form) {
  const button = form.querySelector("button");
  if (!(button instanceof HTMLButtonElement)) {
    return () => {};
  }

  button.dataset.originalText = button.textContent || "";
  button.classList.add("is-pending");

  const action = form.action;
  if (action.includes("/toggle-wanted")) {
    const willBeActive = !button.classList.contains("active");
    button.classList.toggle("active", willBeActive);
    button.textContent = willBeActive ? "Wanted" : "Mark";
  } else if (action.includes("/toggle-passed")) {
    const willBeActive = !button.classList.contains("active");
    button.classList.toggle("active", willBeActive);
    button.textContent = willBeActive ? "Passed" : "Mark";
  }

  return () => {
    button.classList.remove("is-pending");
    if (!document.contains(button)) {
      return;
    }
    if (!action.includes("/toggle-wanted") && !action.includes("/toggle-passed")) {
      button.textContent = button.dataset.originalText || button.textContent;
    }
  };
}

async function submitInlineForm(form) {
  const clearFeedback = applyImmediateButtonFeedback(form);
  const formData = new FormData(form);
  const response = await fetch(form.action, {
    method: form.method || "POST",
    body: formData,
    headers: {
      "X-Requested-With": "fetch",
    },
    redirect: "follow",
  });

  if (!response.ok) {
    clearFeedback();
    window.location.href = formData.get("next_url") || window.location.href;
    return;
  }

  const scrollY = window.scrollY;
  const replaced = await replaceMainFromResponse(response, scrollY);
  clearFeedback();
  if (!replaced) {
    clearFeedback();
    window.location.href = response.url || (formData.get("next_url") || window.location.href);
    return;
  }
}

async function submitGetFilterForm(form) {
  const action = form.action || window.location.pathname;
  const params = new URLSearchParams();
  for (const [key, value] of new FormData(form).entries()) {
    if (typeof value !== "string" || value === "") {
      continue;
    }
    params.append(key, value);
  }

  const url = new URL(action, window.location.origin);
  url.search = params.toString();
  const scrollY = window.scrollY;
  const response = await fetch(url.toString(), {
    headers: {
      "X-Requested-With": "fetch",
    },
  });

  if (!response.ok) {
    window.location.href = url.toString();
    return;
  }

  const replaced = await replaceMainFromResponse(response, scrollY);
  if (!replaced) {
    window.location.href = url.toString();
  }
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const nextUrlInput = form.querySelector('input[name="next_url"]');
  const isInlineAction = form.method.toLowerCase() === "post" && nextUrlInput instanceof HTMLInputElement;
  if (isInlineAction) {
    event.preventDefault();
    submitInlineForm(form).catch(() => {
      window.location.href = nextUrlInput.value || window.location.href;
    });
    return;
  }

  const isGetFilterForm = form.method.toLowerCase() === "get" && form.classList.contains("filters");
  if (!isGetFilterForm) {
    return;
  }

  event.preventDefault();
  submitGetFilterForm(form).catch(() => {
    form.submit();
  });
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }

  const inlineAutoSubmitForm = target.closest("form.auto-submit-form");
  if (inlineAutoSubmitForm instanceof HTMLFormElement && inlineAutoSubmitForm.method.toLowerCase() === "post") {
    submitInlineForm(inlineAutoSubmitForm).catch(() => {
      const nextUrlInput = inlineAutoSubmitForm.querySelector('input[name="next_url"]');
      window.location.href = nextUrlInput instanceof HTMLInputElement ? nextUrlInput.value || window.location.href : window.location.href;
    });
    return;
  }

  const form = target.closest("form.filters");
  if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== "get") {
    return;
  }
  submitGetFilterForm(form).catch(() => {
    form.submit();
  });
});

document.addEventListener("click", (event) => {
  const detailsToggle = event.target instanceof Element ? event.target.closest("[data-toggle-wahl-details]") : null;
  if (detailsToggle instanceof HTMLButtonElement) {
    const card = detailsToggle.closest(".wahl-card");
    const details = card ? card.querySelector(".wahl-details") : null;
    if (details instanceof HTMLElement) {
      const willExpand = details.hidden;
      details.hidden = !willExpand;
      detailsToggle.setAttribute("aria-expanded", String(willExpand));
      detailsToggle.textContent = willExpand ? "Hide details" : "Show details";
      if (willExpand) {
        details.classList.remove("is-opening");
        void details.offsetWidth;
        details.classList.add("is-opening");
        window.setTimeout(() => details.classList.remove("is-opening"), 220);
      }
    }
    return;
  }

  const clickableCard = event.target instanceof Element ? event.target.closest(".clickable-card[data-href]") : null;
  if (clickableCard instanceof HTMLElement) {
    const interactiveTarget = event.target instanceof Element
      ? event.target.closest("a, button, form, input, select, textarea, label")
      : null;
    if (!interactiveTarget) {
      const href = clickableCard.dataset.href;
      if (href) {
        window.location.href = href;
        return;
      }
    }
  }

  const link = event.target instanceof Element ? event.target.closest("a.wahl-tab") : null;
  if (!(link instanceof HTMLAnchorElement) || !link.href) {
    return;
  }

  const url = new URL(link.href, window.location.origin);
  if (url.origin !== window.location.origin) {
    return;
  }

  event.preventDefault();
  const scrollY = window.scrollY;
  fetch(url.toString(), {
    headers: {
      "X-Requested-With": "fetch",
    },
  })
    .then((response) => {
      if (!response.ok) {
        window.location.href = link.href;
        return null;
      }
      return replaceMainFromResponse(response, scrollY);
    })
    .then((replaced) => {
      if (replaced === false) {
        window.location.href = link.href;
      }
    })
    .catch(() => {
      window.location.href = link.href;
    });
});
