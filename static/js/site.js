'use strict';
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-password-toggle]').forEach(button => {
    const input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input) return;
    const label = button.getAttribute('aria-label').replace('Показать пароль: ', '');
    button.hidden = false;
    button.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.textContent = show ? 'Скрыть' : 'Показать';
      button.setAttribute('aria-pressed', String(show));
      button.setAttribute('aria-label', `${show ? 'Скрыть' : 'Показать'} пароль: ${label}`);
    });
  });
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
    });
  }
  document.querySelectorAll('[data-dismiss]').forEach(button => {
    button.addEventListener('click', () => button.closest('.message')?.remove());
  });
  // This prevents accidental double clicks; server transactions remain authoritative.
  document.querySelectorAll('form[data-submit-once]').forEach(form => {
    form.addEventListener('submit', event => {
      if (form.dataset.submitting === 'true') {
        event.preventDefault();
        return;
      }
      if (!form.checkValidity()) return;
      form.dataset.submitting = 'true';
      form.setAttribute('aria-busy', 'true');
      // Keep the clicked action button enabled until the browser serializes it.
      setTimeout(() => form.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = true; }), 0);
    });
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-submit-once]').forEach(form => {
      delete form.dataset.submitting;
      form.removeAttribute('aria-busy');
      form.querySelectorAll('button[type="submit"]').forEach(b => { b.disabled = false; });
    });
  });
  const input = document.querySelector('input[type="file"][name="photo"]');
  const preview = document.querySelector('.photo-preview');
  let previewUrl;
  if (input && preview) input.addEventListener('change', () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const file = input.files?.[0];
    preview.hidden = !file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type);
    if (!preview.hidden) {
      previewUrl = URL.createObjectURL(file);
      preview.querySelector('img').src = previewUrl;
    }
  });
});
