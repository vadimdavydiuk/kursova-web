const sizeFactor = { small: 0.85, medium: 1, large: 1.3 };

document.querySelectorAll(".order-form").forEach((form) => {
    const priceNode = form.querySelector("[data-live-price]");
    const base = Number(form.dataset.price);

    const update = () => {
        const size = form.querySelector("[name=size]").value;
        const qty = Number(form.querySelector("[name=quantity]").value) || 1;
        const total = Math.round(base * sizeFactor[size] * qty);
        priceNode.textContent = `${total} грн`;
    };

    form.addEventListener("change", update);
    form.addEventListener("input", update);
});

document.querySelectorAll("[data-phone]").forEach((input) => {
    input.addEventListener("input", () => {
        const digits = input.value.replace(/\D/g, "").slice(0, 12);
        input.value = digits ? `+${digits}` : "";
    });
});

document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
        if (!window.confirm(form.dataset.confirm)) {
            event.preventDefault();
        }
    });
});
