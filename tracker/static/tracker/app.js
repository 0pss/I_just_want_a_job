(() => {
  const clock = document.getElementById('clock');
  const tick = () => {
    if (!clock) return;
    const d = new Date();
    clock.textContent = d.toLocaleTimeString('de-DE', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  };
  tick(); setInterval(tick, 1000);
})();
(() => {
  const button=document.getElementById("font-size-toggle");
  if(!button) return;
  const key="ijwaj-font-large";
  const apply=large=>document.documentElement.classList.toggle("font-large",large);
  const large=localStorage.getItem(key)==="1"; apply(large);
  button.textContent=large?"A−":"A+";
  button.addEventListener("click",()=>{const next=!document.documentElement.classList.contains("font-large"); apply(next); localStorage.setItem(key,next?"1":"0"); button.textContent=next?"A−":"A+";});
})();
