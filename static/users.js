'use strict';
const role = document.getElementById('role');
const roleDefaults = {
  admin: ['calls:read', 'calls:sensitive', 'metrics:read', 'mcp:use'],
  analyst: ['calls:read', 'metrics:read', 'mcp:use'],
  reader: ['calls:read'],
  metrics: ['metrics:read']
};

// Keep MCP grants consistent while visibly showing what the administrator
// is enabling. No hidden server-side privilege escalation: invalid POST
// combinations are independently rejected by the auth backend.
for (const form of document.querySelectorAll(
  'form[action="/dashboard/users"], form.user-edit-form'
)) {
  const grants = new Map(
    [...form.querySelectorAll('input[name="grants"]')]
      .map(input => [input.value, input])
  );
  const mcp = grants.get('mcp:use');
  const calls = grants.get('calls:read');
  const metrics = grants.get('metrics:read');
  if (!mcp || !calls || !metrics) continue;

  mcp.addEventListener('change', () => {
    if (mcp.checked) {
      calls.checked = true;
      metrics.checked = true;
    }
  });
  for (const required of [calls, metrics]) {
    required.addEventListener('change', () => {
      if (!required.checked) mcp.checked = false;
    });
  }
}

if (role) {
  role.addEventListener('change', () => {
    for (const checkbox of document.querySelectorAll(
      'form[action="/dashboard/users"] input[name="grants"]'
    )) {
      checkbox.checked = roleDefaults[role.value]?.includes(checkbox.value) ?? false;
      checkbox.disabled = role.value === 'admin';
    }
  });
}
