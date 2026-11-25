'use strict';
for(const button of document.querySelectorAll('[data-guide-copy]')){
 button.addEventListener('click',async()=>{
  const status=button.closest('.panel')?.querySelector('.guide-copy-status');
  try{await navigator.clipboard.writeText(button.dataset.guideCopy);if(status)status.textContent='آدرس کپی شد.';}
  catch{if(status)status.textContent='کپی خودکار ممکن نیست؛ آدرس را انتخاب و دستی کپی کنید.';}
 });
}
