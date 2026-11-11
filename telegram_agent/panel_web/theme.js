'use strict';
(() => {
  let preference;
  try { preference=localStorage.getItem('agent.theme'); } catch {}
  const system=matchMedia('(prefers-color-scheme: dark)');
  function apply(theme) {
    const dark=theme==='dark';
    document.documentElement.classList.toggle('dark',dark);
    document.documentElement.dataset.theme=theme;
    document.querySelectorAll('[data-theme-toggle]').forEach(button=>{
      button.textContent=dark?'☀':'☾';
      button.setAttribute('aria-label',dark?'Kunduzgi rejim':'Tungi rejim');
      button.setAttribute('title',dark?'Kunduzgi rejim':'Tungi rejim');
    });
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#11131e':'#5338ce');
  }
  function initial(){apply(preference==='dark'||preference==='light'?preference:(system.matches?'dark':'light'));}
  document.addEventListener('click',event=>{
    if(!event.target.closest('[data-theme-toggle]'))return;
    preference=document.documentElement.classList.contains('dark')?'light':'dark';
    try {localStorage.setItem('agent.theme',preference);}catch{}
    apply(preference);
  });
  system.addEventListener('change',()=>{if(!preference)initial();});
  document.addEventListener('DOMContentLoaded',initial);
  initial();
})();
