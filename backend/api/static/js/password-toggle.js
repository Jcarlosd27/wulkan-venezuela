document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-password-toggle]");
  if (!button) {
    return;
  }

  const group = button.closest(".input-group") || button.parentElement;
  const input = group ? group.querySelector('input[type="password"], input[type="text"]') : null;
  if (!input) {
    return;
  }

  const shouldShow = input.type === "password";
  input.type = shouldShow ? "text" : "password";

  const label = shouldShow ? "Ocultar contrasena" : "Mostrar contrasena";
  button.setAttribute("aria-label", label);
  button.setAttribute("title", label);

  const icon = button.querySelector("i");
  if (icon) {
    icon.className = shouldShow ? "bi bi-eye-slash" : "bi bi-eye";
  }
});
