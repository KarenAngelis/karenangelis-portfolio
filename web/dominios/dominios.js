const $ = (selector) => document.querySelector(selector);
const money = (cents) => new Intl.NumberFormat('pt-BR', {style: 'currency', currency: 'BRL'}).format(cents / 100);
const state = {config: null, user: null, selected: null, items: [], requestKey: null, resetToken: null};
const statuses = {creating_checkout:'Preparando pagamento', awaiting_payment:'Aguardando pagamento', paid:'Pagamento recebido', registering:'Registrando domínio', registration_pending:'Aguardando confirmação do registro', active:'Domínio registrado', review_required:'Pedido em conferência', refund_pending:'Reembolso solicitado', refunded:'Reembolso confirmado', expired:'Pagamento expirado', checkout_failed:'Pagamento não iniciado', cancelled:'Pedido cancelado'};

async function api(path, options = {}) {
  const response = await fetch('/api/domains' + path, {credentials: 'same-origin', ...options,
    headers: {'Content-Type': 'application/json', ...options.headers}});
  let data;
  try { data = await response.json(); } catch { throw new Error('A loja está temporariamente indisponível. Tente novamente ou fale com Karen.'); }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Confira os dados e tente novamente.');
    error.status = response.status;
    throw error;
  }
  return data;
}
const post = (path, data = {}, headers = {}) => api(path, {method:'POST', body:JSON.stringify(data), headers});
function feedback(selector, message, error = false) {
  const node = $(selector); node.textContent = message; node.classList.toggle('error', error); node.classList.toggle('success', !error);
}
function element(tag, text, className) {
  const node = document.createElement(tag); if (text) node.textContent = text; if (className) node.className = className; return node;
}
function busy(form, value) { form.querySelectorAll('button').forEach(button => { button.disabled = value; }); }
function openAccount() {
  if (state.user) { $('#my-domains').scrollIntoView({behavior:'smooth'}); return; }
  $('#auth-dialog').showModal();
}
function updateSelection() {
  const item = state.selected;
  $('#summary-empty').hidden = Boolean(item); $('#summary-selected').hidden = !item;
  $('#registrant-section').hidden = !(item && state.user && state.config?.sales_ready);
  if (!item) return;
  $('#chosen-domain').textContent = item.domain;
  $('#chosen-price').textContent = money(item.annual_cents);
  $('#renewal-price').textContent = `Renovação: ${money(item.renewal_cents)}/ano no preço atual.`;
  $('#continue-button').disabled = !state.config.sales_ready;
  $('#continue-button').textContent = state.config.sales_ready ? (state.user ? 'Preencher dados do titular' : 'Continuar com este domínio') : 'Compras disponíveis em breve';
  $('#buyer-email').textContent = state.user ? `E-mail da conta e do registro: ${state.user.email}` : '';
}
function renderResults() {
  const results = $('#results'); results.replaceChildren(element('h2', 'Escolha seu endereço'));
  for (const item of state.items) {
    const row = element('article', '', 'result-row' + (state.selected?.domain === item.domain ? ' selected' : ''));
    const identity = element('div'); identity.append(element('strong', item.domain, 'result-name'));
    const labels = {unknown:'Não foi possível confirmar. Tente novamente.',special:'Este nome precisa de uma consulta especial.',regthroughus:'Já registrado',regthroughothers:'Já registrado'};
    identity.append(element('p', item.available ? 'Disponível nesta consulta' : (labels[item.status] || 'Indisponível'), 'result-status'));
    row.append(identity);
    if (item.available) {
      const price = element('div', '', 'result-price');
      price.append(element('strong', money(item.annual_cents)), element('small', 'por 1 ano'), element('small', `Renova por ${money(item.renewal_cents)}/ano*`));
      const button = element('button', state.selected?.domain === item.domain ? 'Selecionado' : 'Escolher', 'button lime');
      button.type = 'button'; button.setAttribute('aria-label', `Escolher ${item.domain}`);
      button.addEventListener('click', () => { state.selected = item; state.requestKey = crypto.randomUUID(); feedback('#checkout-status', ''); updateSelection(); renderResults(); $('#summary').scrollIntoView({behavior:'smooth', block:'nearest'}); });
      price.append(button); row.append(price);
    }
    results.append(row);
  }
  results.append(element('p', '*Preço atual de renovação. A consulta vale por 10 minutos e não reserva o domínio.', 'hint'));
}
$('#search-form').addEventListener('submit', async (event) => {
  event.preventDefault(); busy(event.currentTarget, true); state.selected = null; updateSelection();
  $('#results').replaceChildren(element('p', 'Consultando os nomes disponíveis…', 'hint'));
  try {
    const data = await api('/search?q=' + encodeURIComponent($('#domain-query').value.trim()));
    state.items = data.results; state.config.sales_ready = data.sales_ready; renderResults();
  } catch (error) { $('#results').replaceChildren(element('p', error.message, 'feedback error')); }
  finally { busy($('#search-form'), false); }
});
$('#continue-button').addEventListener('click', () => {
  if (!state.user) { openAccount(); return; }
  $('#registrant-section').scrollIntoView({behavior:'smooth'}); $('#registrant-form input').focus({preventScroll:true});
});
$('#account-button').addEventListener('click', openAccount);
$('#close-auth').addEventListener('click', () => $('#auth-dialog').close());
async function signedIn(user) {
  state.user = user; $('#account-button').textContent = 'Meus domínios'; $('#auth-dialog').close();
  $('#my-domains').hidden = false; $('#account-email').textContent = user.email; updateSelection(); await loadOrders();
  if (state.selected) $('#registrant-section').scrollIntoView({behavior:'smooth'});
}
$('#auth-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; const action = event.submitter?.value || 'login';
  const values = Object.fromEntries(new FormData(form)); busy(form, true); feedback('#auth-status', 'Aguarde…');
  try {
    const data = await post('/auth/' + action, values);
    if (action === 'login') { form.reset(); await signedIn(data); } else feedback('#auth-status', data.message);
  } catch (error) { feedback('#auth-status', error.message, true); }
  finally { busy(form, false); }
});
async function sendEmail(kind) {
  const email = $('#auth-form input[name=email]');
  if (!email.reportValidity()) return;
  try { const data = await post('/auth/email?kind=' + kind, {email:email.value}); feedback('#auth-status', data.message); }
  catch (error) { feedback('#auth-status', error.message, true); }
}
$('#forgot-password').addEventListener('click', () => sendEmail('reset'));
$('#resend-verification').addEventListener('click', () => sendEmail('verify'));
$('#reset-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; busy(form, true);
  try {
    const data = await post('/auth/reset', {token: state.resetToken, password: new FormData(form).get('password')});
    feedback('#auth-status', data.message); state.resetToken = null; form.reset(); form.hidden = true; $('#auth-form').hidden = false;
  } catch (error) { feedback('#auth-status', error.message, true); }
  finally { busy(form, false); }
});
$('#registrant-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; busy(form, true); feedback('#checkout-status', 'Conferindo o domínio e preparando o pagamento…');
  const values = Object.fromEntries(new FormData(form)); const accepted = values.accepted_terms === 'on'; delete values.accepted_terms;
  for (const key of ['document','phone','zipcode']) values[key] = values[key].replace(/\D/g, '');
  try {
    if (!state.selected || state.selected.quote_expires * 1000 <= Date.now()) throw new Error('A consulta expirou. Busque o nome novamente antes de continuar.');
    const data = await post('/checkout', {quote_id: state.selected.quote_id, registrant:values, accepted_terms:accepted}, {'Idempotency-Key':state.requestKey});
    const target = new URL(data.checkout_url);
    if (target.protocol !== 'https:' || !['www.mercadopago.com.br','sandbox.mercadopago.com.br'].includes(target.hostname)) throw new Error('Endereço de pagamento inválido. Fale com Karen.');
    window.location.assign(target.href);
  } catch (error) { feedback('#checkout-status', error.message, true); if (error.status === 401) { state.user = null; openAccount(); } }
  finally { busy(form, false); }
});
async function loadOrders() {
  if (!state.user) return;
  try {
    const data = await api('/orders'); $('#orders-list').replaceChildren();
    $('#orders-status').textContent = data.orders.length ? 'O registro só está concluído quando aparecer “Domínio registrado”.' : 'Você ainda não tem pedidos. Encontre seu primeiro domínio na busca acima.';
    for (const order of data.orders) {
      const card = element('article', '', 'order-card'); card.append(element('h3', order.domain), element('span', statuses[order.status] || 'Em acompanhamento', 'order-state'));
      card.append(element('p', `Registro de 1 ano: ${money(order.amount)} · Renovação de referência: ${money(order.renewal)}/ano`));
      if (order.note) card.append(element('p', order.note));
      if (order.expires) card.append(element('p', 'Válido até ' + new Date(order.expires * 1000).toLocaleDateString('pt-BR', {timeZone:'UTC'})));
      if (order.status === 'awaiting_payment' && order.checkout_url) {
        const target = new URL(order.checkout_url);
        if (target.protocol === 'https:' && ['www.mercadopago.com.br','sandbox.mercadopago.com.br'].includes(target.hostname)) {
          const link = element('a', 'Continuar pagamento', 'button lime'); link.href = target.href; card.append(link);
        }
      }
      if (order.status === 'active') {
        const details = element('details'); details.append(element('summary', 'Conectar ao site'));
        details.append(element('p', 'Servidores DNS configurados para este domínio:'), element('pre', order.nameservers.join('\n')));
        details.append(element('p', 'Os registros A, CNAME, MX e TXT dependem da sua hospedagem. Peça ajuda para conectar sem alterar o e-mail da sua empresa.'));
        const copy = element('button', 'Copiar servidores DNS', 'button'); copy.type = 'button';
        copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(order.nameservers.join('\n')); copy.textContent = 'Copiado'; } catch { copy.textContent = 'Selecione o texto acima para copiar'; } });
        details.append(copy); card.append(details);
      }
      const support = element('a', order.status === 'active' ? 'Pedir ajuda ou renovar' : 'Falar sobre este pedido', 'support-link');
      support.href = 'https://wa.me/5547997336808?text=' + encodeURIComponent(`Olá, Karen! Preciso de ajuda com ${order.domain}. Pedido ${order.id}.`);
      support.target = '_blank'; support.rel = 'noopener noreferrer'; card.append(support); $('#orders-list').append(card);
    }
  } catch (error) { $('#orders-status').textContent = error.message; }
}
$('#refresh-orders').addEventListener('click', loadOrders);
$('#logout').addEventListener('click', async () => {
  try { await post('/auth/logout'); state.user = null; $('#my-domains').hidden = true; $('#orders-list').replaceChildren(); $('#account-button').textContent = 'Minha conta'; $('#registrant-form').reset(); updateSelection(); }
  catch (error) { $('#orders-status').textContent = error.message; }
});
async function googleSetup() {
  if (!state.config.google_client_id) { $('#google-status').textContent = 'Acesso Google disponível após ativação da loja.'; return; }
  try {
    const {nonce} = await post('/auth/google/nonce');
    await new Promise((resolve, reject) => { const script = document.createElement('script'); script.src = 'https://accounts.google.com/gsi/client'; script.async = true; script.onload = resolve; script.onerror = reject; document.head.append(script); });
    google.accounts.id.initialize({client_id:state.config.google_client_id, nonce, callback: async ({credential}) => {
      try { await signedIn(await post('/auth/google', {credential})); }
      catch (error) { feedback('#auth-status', error.message + ' Atualize a página para tentar Google novamente.', true); }
    }});
    google.accounts.id.renderButton($('#google-button'), {theme:'outline', size:'large', text:'continue_with', locale:'pt-BR'});
  } catch { $('#google-status').textContent = 'Não foi possível carregar Google. Você pode entrar com e-mail e senha.'; }
}
async function start() {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const verifyToken = fragment.get('verify'); state.resetToken = fragment.get('reset');
  // Remove bearer tokens from the address bar before loading any third-party script.
  if (verifyToken || state.resetToken) history.replaceState(null, '', location.pathname + location.search);
  try {
    state.config = await api('/config');
    $('#search-button').disabled = !state.config.search_ready;
    $('#store-status').textContent = !state.config.search_ready ? 'Estamos preparando a compra de domínios. Por enquanto, fale com Karen para escolher seu endereço; nenhuma cobrança está disponível aqui.' : !state.config.sales_ready ? 'Você já pode consultar nomes. As compras estarão disponíveis em breve.' : state.config.test_mode ? 'Ambiente de testes: não use dados reais nem faça compras para uso definitivo.' : 'Escolha seu endereço. O preço anual e a renovação aparecem antes do pagamento.';
    if (!state.config.email_ready) {
      $('#auth-form').hidden = true; $('#auth-status').textContent = 'O acesso por e-mail está em preparação. Fale com Karen se precisar de ajuda.';
    }
    try { await signedIn(await api('/me')); } catch { /* Signed out is expected. */ }
    if (verifyToken) {
      $('#auth-dialog').showModal();
      try { feedback('#auth-status', (await post('/auth/verify', {token:verifyToken})).message); }
      catch (error) { feedback('#auth-status', error.message, true); }
    } else if (state.resetToken) {
      $('#auth-form').hidden = true; $('#reset-form').hidden = false; $('#auth-dialog').showModal();
    }
    if (new URLSearchParams(location.search).has('pedido')) {
      if (state.user) $('#my-domains').scrollIntoView({behavior:'smooth'});
      else { openAccount(); feedback('#auth-status', 'Entre na sua conta para acompanhar a confirmação do pagamento e do registro.'); }
    }
    await googleSetup();
  } catch (error) { $('#store-status').textContent = error.message; }
}
start();
setInterval(() => { if (state.user && !document.hidden) loadOrders(); }, 30000);
