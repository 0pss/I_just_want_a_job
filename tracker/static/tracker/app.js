(() => {
  const clock = document.getElementById('clock');
  const tick = () => {
    if (!clock) return;
    const d = new Date();
    clock.textContent = d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  };
  tick(); setInterval(tick, 1000);
})();