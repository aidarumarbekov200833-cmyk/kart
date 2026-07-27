/**
 * AutoFlow Unified — Shared Application Logic
 * Toast system, multi-theme selector (13 themes), notifications polling, activity log
 */

(function () {
  'use strict';

  /* ================================================================
     Theme Registry (13 themes)
     ================================================================ */
  var THEMES = [
    { id: 'system',            name: 'System',        icon: '🖥', desc: 'Адаптируется к теме системы' },
    { id: 'dark',              name: 'AutoFlow Dark', icon: '🌑', desc: 'Графитовый минимализм' },
    { id: 'light',             name: 'AutoFlow Light',icon: '☀️', desc: 'Светлый минимализм' },
    { id: 'tokyonight',        name: 'Tokyo Night',   icon: '🌃', desc: 'Неоновый Токио' },
    { id: 'everforest',        name: 'Everforest',    icon: '🌲', desc: 'Лесные тона' },
    { id: 'ayu',               name: 'Ayu Dark',      icon: '🎨', desc: 'Тёплый минимализм' },
    { id: 'catppuccin',        name: 'Catppuccin',    icon: '🐱', desc: 'Mocha — лавандовый' },
    { id: 'catppuccin-macchiato', name: 'Catppuccin Macchiato', icon: '☕', desc: 'Macchiato — светлее' },
    { id: 'gruvbox',           name: 'Gruvbox',       icon: '📦', desc: 'Ретро-тёплый' },
    { id: 'kanagawa',          name: 'Kanagawa',      icon: '⛩', desc: 'Японская эстетика' },
    { id: 'nord',              name: 'Nord',          icon: '❄️', desc: 'Северный холод' },
    { id: 'matrix',            name: 'Matrix',        icon: '💚', desc: 'Хакерский зелёный' },
    { id: 'one-dark',          name: 'One Dark',      icon: '⚛️', desc: 'Atom-стиль' }
  ];

  var THEME_STORAGE_KEY = 'autoflow-theme';

  function getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  }

  function setTheme(themeId) {
    localStorage.setItem(THEME_STORAGE_KEY, themeId);
    if (themeId === 'system') {
      var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
      document.documentElement.setAttribute('data-theme-active', 'system');
    } else {
      document.documentElement.setAttribute('data-theme', themeId);
      document.documentElement.removeAttribute('data-theme-active');
    }
    updateThemeBtnIcon();
    updateThemeDropdown();
  }

  function initTheme() {
    var saved = localStorage.getItem(THEME_STORAGE_KEY) || 'dark';
    setTheme(saved);
  }

  function updateThemeBtnIcon() {
    var btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    var active = document.documentElement.getAttribute('data-theme-active') || getTheme();
    var theme = THEMES.find(function (t) { return t.id === active; });
    btn.textContent = theme ? theme.icon : '🎨';
    btn.setAttribute('data-tooltip', (theme ? theme.name : 'Тема') + ' — сменить');
  }

  function updateThemeDropdown() {
    var active = document.documentElement.getAttribute('data-theme-active') || getTheme();
    var items = document.querySelectorAll('.theme-dropdown-item');
    items.forEach(function (el) {
      var id = el.getAttribute('data-theme-id');
      if (id === active) {
        el.classList.add('theme-active');
      } else {
        el.classList.remove('theme-active');
      }
    });
  }

  function buildThemeDropdown() {
    var dd = document.getElementById('theme-dropdown');
    if (!dd) return;

    var active = document.documentElement.getAttribute('data-theme-active') || getTheme();

    dd.innerHTML = THEMES.map(function (t) {
      var sel = t.id === active ? ' theme-active' : '';
      return '<div class="theme-dropdown-item' + sel + '" data-theme-id="' + t.id + '" onclick="AutoFlow.selectTheme(\'' + t.id + '\')">' +
        '<span class="theme-dd-icon">' + t.icon + '</span>' +
        '<div class="theme-dd-info">' +
        '<span class="theme-dd-name">' + t.name + '</span>' +
        '<span class="theme-dd-desc">' + t.desc + '</span>' +
        '</div>' +
        '<span class="theme-dd-check" style="' + (t.id === active ? 'opacity:1;' : '') + '">✓</span>' +
        '</div>';
    }).join('');
  }

  /* ================================================================
     Theme Toggle & Dropdown
     ================================================================ */
  function toggleThemeDropdown() {
    var dd = document.getElementById('theme-dropdown');
    if (!dd) return;
    var isHidden = dd.classList.contains('hidden');
    if (isHidden) {
      buildThemeDropdown();
      dd.classList.remove('hidden');
    } else {
      dd.classList.add('hidden');
    }
  }

  function selectTheme(themeId) {
    setTheme(themeId);
    var dd = document.getElementById('theme-dropdown');
    if (dd) dd.classList.add('hidden');
  }

  /* ================================================================
     Toast Notification System
     ================================================================ */
  var _toastId = 0;

  function showToast(message, type) {
    type = type || 'info';
    var icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };

    var container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    var id = 'toast-' + (++_toastId);
    var el = document.createElement('div');
    el.id = id;
    el.className = 'toast toast-' + type;
    el.innerHTML =
      '<span class="toast-icon">' + (icons[type] || 'ℹ') + '</span>' +
      '<span class="toast-msg">' + escapeHtml(message) + '</span>' +
      '<button class="toast-close" onclick="this.parentElement.remove()">✕</button>';

    container.appendChild(el);

    setTimeout(function () {
      var t = document.getElementById(id);
      if (t) {
        t.classList.add('removing');
        setTimeout(function () { if (t.parentElement) t.remove(); }, 200);
      }
    }, 4000);
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ================================================================
     API Helper
     ================================================================ */
  function api(url, options) {
    options = options || {};
    var headers = options.headers || {};
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    // Attach CSRF token for state-changing requests.
    var method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) !== -1) {
      var meta = document.querySelector('meta[name="csrf-token"]');
      if (meta) headers['X-CSRFToken'] = meta.getAttribute('content');
    }
    return fetch(url, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error(d.error || 'Ошибка сервера');
        return d;
      });
    });
  }

  /* ================================================================
     Activity Log
     ================================================================ */
  function loadActivityLog() {
    var container = document.getElementById('activity-log-list');
    if (!container) return;

    api('/api/activity')
      .then(function (data) {
        if (!data.activities || data.activities.length === 0) {
          container.innerHTML =
            '<div class="activity-log-item" style="justify-content:center;">' +
            '<span style="color:var(--text-tertiary);font-size:0.8125rem;">Нет действий</span></div>';
          return;
        }

        container.innerHTML = data.activities.map(function (a) {
          var dotClass = '';
          var actionText = escapeHtml(a.action || 'action');
          if (actionText.indexOf('parse') !== -1 || actionText.indexOf('парс') !== -1) dotClass = 'parse';
          else if (actionText.indexOf('verif') !== -1 || actionText.indexOf('вериф') !== -1) dotClass = 'verify';
          else if (actionText.indexOf('campaign') !== -1 || actionText.indexOf('рассылк') !== -1) dotClass = 'campaign';
          else if (actionText.indexOf('login') !== -1 || actionText.indexOf('вход') !== -1) dotClass = 'login';
          else if (actionText.indexOf('error') !== -1 || actionText.indexOf('ошибк') !== -1) dotClass = 'error';
          else dotClass = 'system';

          var timeAgo = formatTimeAgo(a.created_at);
          var duration = a.duration ? '<br><span class="activity-duration">⏱ ' + escapeHtml(a.duration) + '</span>' : '';

          return '<div class="activity-log-item">' +
            '<span class="activity-dot ' + dotClass + '"></span>' +
            '<div style="flex:1;min-width:0;">' +
            '<span class="activity-action">' + actionText + duration + '</span>' +
            '</div>' +
            '<span class="activity-time" title="' + escapeHtml(a.created_at || '') + '">' + timeAgo + '</span>' +
            '</div>';
        }).join('');
      })
      .catch(function () {
        container.innerHTML =
          '<div class="activity-log-item" style="justify-content:center;">' +
          '<span style="color:var(--text-tertiary);font-size:0.8125rem;">Не удалось загрузить лог</span></div>';
      });
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return '—';
    var now = new Date();
    var then = new Date(dateStr + 'Z');
    if (isNaN(then.getTime())) then = new Date(dateStr);
    var diffMs = now - then;
    var diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 0) diffSec = 0;
    if (diffSec < 10) return 'сейчас';
    if (diffSec < 60) return diffSec + 'с';
    var diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return diffMin + 'м';
    var diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return diffHr + 'ч';
    var diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return diffDay + 'д';
    return then.toLocaleDateString('ru-RU');
  }

  /* ================================================================
     Notifications
     ================================================================ */
  function loadNotifications() {
    api('/api/notifications').then(function (d) {
      var badge = document.getElementById('notif-badge');
      var list = document.getElementById('notif-list');
      if (!badge || !list) return;

      if (d.unread_count > 0) {
        badge.textContent = d.unread_count > 99 ? '99+' : d.unread_count;
        badge.style.display = 'flex';
        badge.classList.add('pulse-ring');
      } else {
        badge.style.display = 'none';
        badge.classList.remove('pulse-ring');
      }

      if (!d.notifications || d.notifications.length === 0) {
        list.innerHTML = '<p style="color:var(--text-tertiary);font-size:0.8125rem;text-align:center;padding:1rem 0;">Нет уведомлений</p>';
        return;
      }

      list.innerHTML = d.notifications.map(function (n) {
        var borderColor = n.is_read ? 'var(--border-default)' : 'var(--accent)';
        var opacity = n.is_read ? 'opacity:0.6;' : '';
        var readBtn = !n.is_read
          ? '<button onclick="AutoFlow.markNotificationRead(' + n.id + ')" style="font-size:0.6875rem;color:var(--accent);margin-top:0.25rem;background:none;border:none;cursor:pointer;padding:0;">Отметить прочитанным</button>'
          : '';
        var timeAgo = formatTimeAgo(n.created_at);

        return '<div style="background:var(--bg-input);padding:0.75rem;border-radius:var(--radius-sm);border-left:3px solid ' + borderColor + ';margin-bottom:0.5rem;' + opacity + '">' +
          '<div style="display:flex;justify-content:space-between;align-items:flex-start;">' +
          '<span style="font-weight:600;font-size:0.8125rem;color:var(--text-primary);">' + escapeHtml(n.title) + '</span>' +
          '<span style="font-size:0.6875rem;color:var(--text-tertiary);white-space:nowrap;margin-left:0.5rem;">' + timeAgo + '</span>' +
          '</div>' +
          '<p style="color:var(--text-secondary);font-size:0.8125rem;margin-top:0.25rem;">' + escapeHtml(n.message) + '</p>' +
          readBtn +
          '</div>';
      }).join('');
    });
  }

  function markNotificationRead(nid) {
    api('/api/notifications/' + nid + '/read', { method: 'POST' }).then(function () {
      loadNotifications();
    });
  }

  function toggleNotifications() {
    var dd = document.getElementById('notif-dropdown');
    if (!dd) return;
    var isHidden = dd.classList.contains('hidden');
    if (isHidden) {
      dd.classList.remove('hidden');
      loadNotifications();
    } else {
      dd.classList.add('hidden');
    }
  }

  /* ================================================================
     Click outside to close dropdowns
     ================================================================ */
  document.addEventListener('click', function (e) {
    var notifDd = document.getElementById('notif-dropdown');
    var bell = document.getElementById('notif-bell-btn');
    if (notifDd && bell && !notifDd.classList.contains('hidden')) {
      if (!notifDd.contains(e.target) && !bell.contains(e.target)) {
        notifDd.classList.add('hidden');
      }
    }

    var themeDd = document.getElementById('theme-dropdown');
    var themeBtn = document.getElementById('theme-toggle-btn');
    if (themeDd && themeBtn && !themeDd.classList.contains('hidden')) {
      if (!themeDd.contains(e.target) && !themeBtn.contains(e.target)) {
        themeDd.classList.add('hidden');
      }
    }
  });

  /* ================================================================
     System theme listener (for system theme auto-switch)
     ================================================================ */
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
    var active = document.documentElement.getAttribute('data-theme-active');
    if (active === 'system') {
      var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    }
  });

  /* ================================================================
     Exports
     ================================================================ */
  window.AutoFlow = {
    toast: {
      success: function (m) { showToast(m, 'success'); },
      error: function (m) { showToast(m, 'error'); },
      warning: function (m) { showToast(m, 'warning'); },
      info: function (m) { showToast(m, 'info'); }
    },
    api: api,
    selectTheme: selectTheme,
    toggleThemeDropdown: toggleThemeDropdown,
    initTheme: initTheme,
    getTheme: getTheme,
    loadActivityLog: loadActivityLog,
    loadNotifications: loadNotifications,
    markNotificationRead: markNotificationRead,
    toggleNotifications: toggleNotifications,
    formatTimeAgo: formatTimeAgo
  };

  /* ================================================================
     Initialize on DOM ready
     ================================================================ */
  initTheme();

  var themeBtn = document.getElementById('theme-toggle-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      toggleThemeDropdown();
    });
  }

  /* Poll activity log every 8 seconds if on dashboard */
  if (document.getElementById('activity-log-list')) {
    loadActivityLog();
    setInterval(loadActivityLog, 8000);
  }

})();
