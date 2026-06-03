// Tip Overlay — SSE subscriber + safe renderer
// CSP enforced by nginx: script-src 'self', no inline, no eval
// All donor content rendered via textContent (NEVER innerHTML) — SPEC §4.5

(function () {
  'use strict';

  const CONTAINER = document.getElementById('overlay-container');
  const ALERT_SOUND = document.getElementById('alert-sound');
  const DISPLAY_DURATION_MS = 8000;
  const SSE_RETRY_MS = 3000;

  // Extract token from URL query string
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token') || '';

  let eventSource = null;

  function connect() {
    if (eventSource) {
      eventSource.close();
    }

    const url = `/api/events/overlay?token=${encodeURIComponent(token)}`;
    eventSource = new EventSource(url);

    eventSource.onmessage = function (e) {
      try {
        const data = JSON.parse(e.data);
        showTip(data);
      } catch {
        // Malformed event — ignore
      }
    };

    eventSource.onerror = function () {
      // Browser auto-reconnects with Last-Event-ID (WHATWG SSE spec)
      // No manual reconnect needed — browser handles it with retry: field
    };
  }

  function showTip(data) {
    const amountBaht = (data.amount / 100).toLocaleString('th-TH', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });

    const card = document.createElement('div');
    card.className = 'tip-card entering';

    const header = document.createElement('div');
    header.className = 'tip-header';

    const nameEl = document.createElement('span');
    nameEl.className = 'tip-name';
    nameEl.textContent = data.donor_name || 'ไม่ระบุชื่อ'; // textContent — SPEC §4.5

    const amountEl = document.createElement('span');
    amountEl.className = 'tip-amount';
    amountEl.textContent = `฿${amountBaht}`;  // textContent — SPEC §4.5

    header.appendChild(nameEl);
    header.appendChild(amountEl);
    card.appendChild(header);

    if (data.message) {
      const msgEl = document.createElement('p');
      msgEl.className = 'tip-message';
      msgEl.textContent = data.message;  // textContent — SPEC §4.5
      card.appendChild(msgEl);
    }

    CONTAINER.appendChild(card);

    // Play alert sound
    if (ALERT_SOUND) {
      ALERT_SOUND.currentTime = 0;
      ALERT_SOUND.play().catch(function () {
        // Autoplay blocked by browser — OBS browser source usually allows it
      });
    }

    // Animate in
    requestAnimationFrame(function () {
      card.classList.remove('entering');
      card.classList.add('visible');
    });

    // Remove after duration
    setTimeout(function () {
      card.classList.remove('visible');
      card.classList.add('leaving');
      card.addEventListener('animationend', function () {
        if (card.parentNode === CONTAINER) {
          CONTAINER.removeChild(card);
        }
      }, { once: true });
    }, DISPLAY_DURATION_MS);
  }

  connect();
})();
