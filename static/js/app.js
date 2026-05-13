/**
 * app.js — Global utilities: sidebar toggle, active nav, toasts.
 */
(function () {
  'use strict';

  // ── Sidebar Toggle ────────────────────────────────────────────────────────
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const toggle  = document.getElementById('sidebar-toggle');

  if (toggle && sidebar) {
    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('sidebar-open');
      if (overlay) overlay.classList.toggle('active');
    });
  }

  if (overlay) {
    overlay.addEventListener('click', function () {
      sidebar.classList.remove('sidebar-open');
      overlay.classList.remove('active');
    });
  }

  // ── Active Nav Link ───────────────────────────────────────────────────────
  var currentPath = window.location.pathname;
  document.querySelectorAll('.sidebar-nav .nav-item').forEach(function (link) {
    var path = link.getAttribute('data-path');
    if (path && currentPath === path) {
      link.classList.add('active');
    } else if (path && path !== '/dashboard' && currentPath.startsWith(path)) {
      link.classList.add('active');
    }
  });

  // ── Toast Utility (global) ────────────────────────────────────────────────
  window.AppToast = {
    show: function (message, type) {
      type = type || 'info';
      var container = document.getElementById('toast-container');
      if (!container) return;

      var id = 'toast-' + Date.now();
      var bgClass = {
        success: 'text-bg-success',
        danger:  'text-bg-danger',
        warning: 'text-bg-warning',
        info:    'text-bg-info',
        primary: 'text-bg-primary',
      }[type] || 'text-bg-secondary';

      var icons = {
        success: 'fa-circle-check',
        danger:  'fa-circle-xmark',
        warning: 'fa-triangle-exclamation',
        info:    'fa-circle-info',
        primary: 'fa-circle-info',
      };
      var icon = icons[type] || 'fa-circle-info';

      var html =
        '<div id="' + id + '" class="toast align-items-center ' + bgClass +
        ' border-0 shadow" role="alert" aria-live="assertive" aria-atomic="true">' +
        '<div class="d-flex">' +
        '<div class="toast-body"><i class="fas ' + icon + ' me-2"></i>' + message + '</div>' +
        '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Cerrar"></button>' +
        '</div></div>';

      container.insertAdjacentHTML('beforeend', html);
      var el = document.getElementById(id);
      var toast = new bootstrap.Toast(el, { delay: 5000 });
      toast.show();
      el.addEventListener('hidden.bs.toast', function () { el.remove(); });
    }
  };
})();
