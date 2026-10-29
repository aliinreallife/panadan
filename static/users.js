'use strict';
const role = document.getElementById('role');
const roleDefaults = {
  admin:['calls:read','calls:sensitive','metrics:read','mcp:use'],
  analyst:['calls:read','metrics:read','mcp:use'],
  reader:['calls:read'],
  metrics:['metrics:read']
};
if(role){role.addEventListener('change',()=>{
  for(const checkbox of document.querySelectorAll('form[action="/dashboard/users"] input[name="grants"]')){
    checkbox.checked=roleDefaults[role.value].includes(checkbox.value);
    checkbox.disabled=role.value==='admin';
  }
})}
