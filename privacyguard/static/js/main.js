/* main.js — PrivacyGuard frontend v2 */

// ── Role toggle on register ───────────────────────────────────────────────
function toggleStudentFields(role) {
  const el = document.getElementById('student-fields');
  if (!el) return;
  el.style.display = role === 'student' ? 'block' : 'none';
  el.querySelectorAll('input, select').forEach(inp => {
    inp.required = role === 'student' && ['name', 'email'].includes(inp.name);
  });
}

// ── Auto-dismiss alerts ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.alert').forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity .5s';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 500);
    }, 4500);
  });

  // Active nav link highlight
  const path = window.location.pathname;
  document.querySelectorAll('.nav-links a').forEach(link => {
    if (link.getAttribute('href') === path) link.classList.add('active');
  });
});
