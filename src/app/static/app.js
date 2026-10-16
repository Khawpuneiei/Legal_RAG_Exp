// Show the structured fields for the selected agreement type (no inline scripts: CSP script-src 'self').
(function () {
  const sel = document.getElementById("agreement_type");
  if (sel) {
    const sync = () => {
      document.querySelectorAll(".typefields").forEach((el) => {
        const on = el.dataset.type === sel.value;
        el.classList.toggle("on", on);
        el.querySelectorAll("input,select").forEach((i) => { i.disabled = !on; });
      });
    };
    sel.addEventListener("change", sync);
    sync();
  }
  document.querySelectorAll("form[data-confirm]").forEach((f) => {
    f.addEventListener("submit", (e) => {
      const d = f.querySelector("[name=decision]:checked") || f.querySelector("[name=decision]");
      if (d && d.value === "approve" && !window.confirm(f.dataset.confirm)) e.preventDefault();
    });
  });
  document.querySelectorAll("select[data-autosubmit]").forEach((s) => s.addEventListener("change", () => s.form.submit()));
})();
