(function(){
  async function renderUsage(){
    const container = document.getElementById('usage-summary');
    if(!container) return;
    container.innerText = 'Loading usage...';
    try{
      const res = await fetch('/api/v1/usage');
      if(!res.ok){ container.innerText = 'Failed to load usage'; return; }
      const data = await res.json();
      const calls = data.calls || [];
      let totalInput = 0, totalOutput = 0, totalCost = 0;
      calls.forEach(c => { totalInput += c.input_tokens || 0; totalOutput += c.output_tokens || 0; totalCost += (c.cost_usd||0); });
      const html = `
        <div style="font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace; color:#cbd5e1; background:#0f172a; padding:12px; border-radius:8px;">
          <div style="font-weight:700;color:#34d399;">LLM Call Usage Summary</div>
          <div style="margin-top:6px">Calls: <strong>${calls.length}</strong></div>
          <div>Input tokens: <strong>${totalInput.toLocaleString()}</strong></div>
          <div>Output tokens: <strong>${totalOutput.toLocaleString()}</strong></div>
          <div style="color:#86efac">Estimated cost (USD): <strong>$${totalCost.toFixed(4)}</strong></div>
          <div style="margin-top:8px; font-size:12px; color:#94a3b8">Data sourced from /api/v1/usage</div>
        </div>
      `;
      container.innerHTML = html;
    }catch(e){ container.innerText = 'Error loading usage'; console.error(e); }
  }
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', renderUsage);
  } else renderUsage();
})();
