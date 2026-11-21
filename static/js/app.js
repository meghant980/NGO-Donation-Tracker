function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open')}
document.addEventListener('click',e=>{const s=document.getElementById('sidebar');if(window.innerWidth<=760&&s.classList.contains('open')&&!s.contains(e.target)&&!e.target.closest('.mobile-toggle'))s.classList.remove('open')});
setTimeout(()=>document.querySelectorAll('.flash').forEach(x=>{if(x.parentElement)x.remove()}),6000);
