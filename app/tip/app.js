// Tip page logic — external file so the page can run under a strict CSP
// (script-src 'self', no inline). No third-party JS (D2, D6).
'use strict';

const MIN_SATANG = 2000;  // ฿20

let currentChargeId = null;
let pollInterval = null;
let pollCount = 0;
const MAX_POLLS = 180;  // ~7.5 min at 2.5s

function show(screenId) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  document.getElementById(screenId).classList.remove('hidden');
}

function resetForm() {
  if (pollInterval) clearInterval(pollInterval);
  currentChargeId = null;
  pollCount = 0;
  document.getElementById('tip-form').reset();
  document.getElementById('char-count').textContent = '0 / 200';
  show('form-screen');
}

function showError(msg) {
  document.getElementById('error-msg').textContent = msg;
  show('error-screen');
}

// Live gate check on load
async function checkLive() {
  try {
    const resp = await fetch('/api/live-status');
    const data = await resp.json();
    if (data.live) {
      show('form-screen');
    } else {
      show('offline');
    }
  } catch {
    show('offline');
  }
}

// Reset buttons (CSP-safe: addEventListener instead of inline onclick)
document.getElementById('send-another').addEventListener('click', resetForm);
document.getElementById('retry-btn').addEventListener('click', resetForm);

// Character counter for message
document.getElementById('message').addEventListener('input', function() {
  const len = this.value.length;
  document.getElementById('char-count').textContent = `${len} / 200`;
});

// Form submit
document.getElementById('tip-form').addEventListener('submit', async function(e) {
  e.preventDefault();

  const amountBaht = parseInt(document.getElementById('amount').value, 10);
  const amountSatang = amountBaht * 100;
  const supporterName = document.getElementById('supporter_name').value.trim().slice(0, 50);
  const message = document.getElementById('message').value.trim().slice(0, 200);

  // Client-side validation (server also validates)
  if (!amountBaht || amountSatang < MIN_SATANG) {
    const errEl = document.getElementById('amount-error');
    errEl.textContent = 'ขั้นต่ำ ฿20';
    errEl.classList.remove('hidden');
    return;
  }
  document.getElementById('amount-error').classList.add('hidden');

  const submitBtn = document.getElementById('submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'กำลังสร้าง QR...';

  try {
    const resp = await fetch('/api/charge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        amount: amountSatang,
        currency: 'thb',
        supporter_name: supporterName,
        message: message,
      }),
    });

    if (resp.status === 403) {
      show('offline');
      return;
    }

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      showError(err.detail || 'ไม่สามารถสร้าง QR ได้ กรุณาลองใหม่');
      return;
    }

    const data = await resp.json();
    currentChargeId = data.charge_id;

    // Show QR screen
    document.getElementById('qr-img').src = data.qr_url;
    document.getElementById('qr-amount').textContent =
      `฿${(data.amount / 100).toLocaleString('th-TH')}`;
    show('qr-screen');

    // Start polling for payment confirmation
    pollCount = 0;
    pollInterval = setInterval(pollStatus, 2500);

  } catch {
    showError('เกิดข้อผิดพลาด กรุณาลองใหม่');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'ส่ง Tip ด้วย PromptPay →';
  }
});

async function pollStatus() {
  if (!currentChargeId) return;
  pollCount++;

  if (pollCount > MAX_POLLS) {
    clearInterval(pollInterval);
    showError('QR หมดอายุแล้ว กรุณาสร้าง QR ใหม่');
    return;
  }

  try {
    const resp = await fetch(`/api/charge/${currentChargeId}/status`);
    if (!resp.ok) return;

    const data = await resp.json();
    if (data.status === 'successful') {
      clearInterval(pollInterval);
      show('success-screen');
    } else if (data.status === 'failed' || data.status === 'expired') {
      clearInterval(pollInterval);
      showError('การชำระเงินไม่สำเร็จ กรุณาลองใหม่');
    }
    // pending → keep polling
  } catch {
    // network hiccup — keep polling
  }
}

// Start
checkLive();
