(function () {
  function $id(id) { return document.getElementById(id); }

  function getCSRFToken() {
    const m = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return m ? m[2] : null;
  }

  // ── Markdown renderer ────────────────────────────────────────────────────
  function renderMarkdown(text) {
    if (!text) return '';
    let s = String(text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
    s = s.replace(/^# (.+)$/gm,   '<h1>$1</h1>');
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    s = s.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>[\s\S]+?<\/li>)(?!\s*<li>)/g, '<ul>$1</ul>');
    s = s.replace(/\n/g, '<br>');
    s = s.replace(/<pre>([\s\S]*?)<\/pre>/g, (m, c) => `<pre>${c.replace(/<br>/g, '\n')}</pre>`);
    return s;
  }

  // ── Thinking parser ──────────────────────────────────────────────────────
  function parseThinking(raw, streamComplete) {
    const OPEN  = '<pensando>';
    const CLOSE = '</pensando>';
    const openIdx = raw.indexOf(OPEN);

    if (openIdx === -1) {
      return { thinking: null, response: raw, inThinking: false };
    }

    const afterOpen = raw.slice(openIdx + OPEN.length);
    const closeIdx  = afterOpen.indexOf(CLOSE);

    if (closeIdx === -1) {
      if (streamComplete) {
        return { thinking: afterOpen, response: afterOpen, inThinking: false };
      }
      return { thinking: afterOpen, response: raw.slice(0, openIdx), inThinking: true };
    }

    const thinking  = afterOpen.slice(0, closeIdx);
    const response  = raw.slice(0, openIdx) + afterOpen.slice(closeIdx + CLOSE.length);
    return { thinking, response, inThinking: false };
  }

  // ── Copy buttons for code blocks ─────────────────────────────────────────
  function addCodeCopyButtons(el) {
    el.querySelectorAll('pre').forEach(pre => {
      if (pre.closest('.code-block-wrapper')) return;
      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);
      const btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'code-copy-btn'; btn.title = 'Copiar código'; btn.textContent = '⎘';
      btn.addEventListener('click', () => {
        const code = pre.querySelector('code') || pre;
        copyText(code.innerText).then(() => { btn.textContent = '✓'; setTimeout(() => btn.textContent = '⎘', 1500); });
      });
      wrapper.prepend(btn);
    });
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
    }
    fallbackCopy(text);
    return Promise.resolve();
  }
  
  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;pointer-events:none';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    try { document.execCommand('copy'); } catch (e) { console.warn('Copy failed', e); }
    document.body.removeChild(ta);
  }

  function extractNoteAction(text) {
    const m = text.match(/\[CRIAR_NOTA:(\{[\s\S]*?\})\]/);
    if (!m) return null;
    try { return JSON.parse(m[1]); } catch { return null; }
  }

  // ── Typewriter ───────────────────────────────────────────────────────
  // Recebe chunks do stream e os REVELA caractere a caractere, chamando
  // onReveal(textoRevelado) a cada avanço. Se o buffer estiver muito
  // adiantado, acelera automaticamente para não atrasar demais.
  //
  // opts:
  //   speedMs: intervalo base entre avanços (ms). Default 22.
  //   maxBehindBeforeSkip: se o buffer ultrapassar este tamanho, flushes
  //     aceleram drasticamente. Default 600.
  //   onFinish: chamado quando buffer é totalmente revelado E end() foi
  //     sinalizado.
  function createTypewriter(onReveal, opts) {
    opts = opts || {};
    const speedMs = Math.max(5, opts.speedMs || window.__AI_TYPEWRITER_SPEED || 22);
    const maxBehind = opts.maxBehindBeforeSkip || 600;
    let buffer      = '';
    let shown       = 0;
    let ticker      = null;
    let streamDone  = false;
    let finished    = false;
    const onFinish  = opts.onFinish || null;

    function emit() {
      try { onReveal(buffer.slice(0, shown)); } catch (_) {}
    }

    function tick() {
      const behind = buffer.length - shown;
      if (behind <= 0) {
        if (streamDone && !finished) {
          finished = true;
          clearInterval(ticker); ticker = null;
          if (onFinish) onFinish();
        }
        return;
      }
      // Aceleração adaptativa — evita atraso absurdo em respostas longas.
      let step;
      if (behind > maxBehind)       step = Math.max(16, Math.ceil(behind / 40));
      else if (behind > 200)        step = 6;
      else if (behind > 80)         step = 3;
      else                          step = 1;
      shown = Math.min(buffer.length, shown + step);
      emit();
      if (shown >= buffer.length && streamDone && !finished) {
        finished = true;
        clearInterval(ticker); ticker = null;
        if (onFinish) onFinish();
      }
    }

    function ensureRunning() {
      if (!ticker) ticker = setInterval(tick, speedMs);
    }

    return {
      push(chunk) {
        if (finished) return;
        if (!chunk) return;
        buffer += chunk;
        ensureRunning();
      },
      end() {
        streamDone = true;
        if (buffer.length === 0) {
          // Nada a revelar — termina de imediato.
          finished = true;
          if (ticker) { clearInterval(ticker); ticker = null; }
          if (onFinish) onFinish();
        } else {
          ensureRunning();
        }
      },
      // Revela tudo instantaneamente (usado quando o usuário aborta).
      flush() {
        if (finished) return;
        shown = buffer.length;
        emit();
        finished = true;
        streamDone = true;
        if (ticker) { clearInterval(ticker); ticker = null; }
        if (onFinish) onFinish();
      },
      // Texto revelado até agora (para uso no evento de abort p/ copiar).
      revealed() { return buffer.slice(0, shown); },
      // Texto total bruto (revelado + pendente).
      raw()      { return buffer; },
      isDone()   { return finished; },
    };
  }

  function initWidget(username, isAuthenticated) {
    if ($id('ai-chatbot')) return;

    const container = document.createElement('div');
    container.id = 'ai-chatbot';
    container.innerHTML = `
      <div id="chat-toggle" title="Abrir assistente IA">💬</div>

      <div id="chat-box" aria-hidden="true" role="dialog" aria-label="Assistente IA">
        <div id="chat-header">
          <div id="chat-title">
            Assistente • <span id="chat-user">${username || 'Convidado'}</span>
            <small id="chat-model-label"></small>
          </div>
          <div class="chat-controls">
            <button id="chat-history-toggle"  class="icon-btn" title="Histórico">📜</button>
            <button id="chat-end-convo"        class="icon-btn" title="Nova conversa">🔄</button>
            <button id="chat-terminal-toggle"  class="icon-btn" title="Modo Terminal (Ollama direto)">🖥️</button>
            <button id="chat-fullscreen"       class="icon-btn" title="Tela cheia">⛶</button>
            <button id="chat-close"            class="icon-btn" title="Fechar">✕</button>
          </div>
        </div>

        <div id="chat-messages" class="scrollable-area" role="log" aria-live="polite"></div>

        <div id="chat-history-panel" style="display:none;">
          <div id="chat-history-header">
            <span>Conversas anteriores</span>
            <button id="chat-history-close" class="icon-btn" title="Fechar histórico">✕</button>
          </div>
          <div id="chat-history-list" class="scrollable-area"></div>
        </div>

        <div id="ai-attachments-bar" style="display:none;"></div>

        <form id="ai-form" autocomplete="off">
          <textarea id="ai-input" placeholder="Digite sua pergunta… (Enter envia, Shift+Enter nova linha)" rows="1" aria-label="Pergunta"></textarea>
          <button id="ai-stop" type="button" class="icon-btn ai-stop-btn" title="Parar resposta" style="display:none">⏹</button>
          <button type="button" id="ai-attach-btn" class="icon-btn ai-attach-btn" title="Anexar arquivo de texto">📎</button>
          <input type="file" id="ai-attach-input" multiple
            accept=".txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.csv,.html,.css,.xml,.yaml,.yml,.log,.sh,.bat,.sql,.c,.cpp,.h,.java,.php,.rb,.go,.rs,.toml,.ini,.cfg,.conf"
            style="display:none">
          <button id="ai-send" type="submit" aria-label="Enviar">➤</button>
        </form>

        <!-- ══════════════ MODO TERMINAL ══════════════ -->
        <div id="chat-terminal" aria-hidden="true">
          <div class="term-toolbar">
            <button type="button" id="term-history-btn" class="term-tool-btn" title="Histórico de conversas do terminal">📜 histórico</button>
            <button type="button" id="term-new-btn"     class="term-tool-btn" title="Nova conversa de terminal">＋ nova</button>
            <button type="button" id="term-attach-btn"  class="term-tool-btn" title="Anexar arquivo ao terminal">📎 anexar</button>
            <button type="button" id="term-clear-btn"   class="term-tool-btn" title="Limpar tela (clear)">clear</button>
            <button type="button" id="term-help-btn"    class="term-tool-btn" title="Ajuda">?</button>
            <input type="file" id="term-attach-input"
              accept=".txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.csv,.html,.css,.xml,.yaml,.yml,.log,.sh,.bat,.sql,.c,.cpp,.h,.java,.php,.rb,.go,.rs,.toml,.ini,.cfg,.conf"
              style="display:none">
            <span class="term-file-info empty" id="term-file-info">[nenhum arquivo anexado]</span>
          </div>
          <div id="term-history-panel" class="term-history-panel" style="display:none;">
            <div class="term-history-header">
              <span>Conversas anteriores do terminal</span>
              <button type="button" id="term-history-close" class="term-tool-btn" title="Fechar histórico">✕</button>
            </div>
            <div id="term-history-list" class="term-history-list"></div>
          </div>
          <div class="term-output" id="term-output" role="log" aria-live="polite"></div>
          <div class="term-input-row">
            <span class="term-prompt" id="term-prompt-label">user@ollama:~$</span>
            <input type="text" id="term-input" class="term-input" autocomplete="off"
              spellcheck="false" placeholder="digite um comando ou pergunta…" aria-label="Terminal">
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(container);

    const toggle      = $id('chat-toggle');
    const box         = $id('chat-box');
    const header      = $id('chat-header');
    const form        = $id('ai-form');
    const input       = $id('ai-input');
    const msgs        = $id('chat-messages');
    const histBtn     = $id('chat-history-toggle');
    const histPanel   = $id('chat-history-panel');
    const histList    = $id('chat-history-list');
    const histClose   = $id('chat-history-close');
    const endBtn      = $id('chat-end-convo');
    const fullBtn     = $id('chat-fullscreen');
    const closeBtn    = $id('chat-close');
    const modelLbl    = $id('chat-model-label');
    const attachBtn   = $id('ai-attach-btn');
    const attachInput = $id('ai-attach-input');
    const attachBar   = $id('ai-attachments-bar');
    const stopBtn     = $id('ai-stop');
    const sendBtn     = $id('ai-send');

    // ── Terminal mode elements ───────────────────────────────────────────
    const termToggle     = $id('chat-terminal-toggle');
    const termPanel      = $id('chat-terminal');
    const termOutput     = $id('term-output');
    const termInput      = $id('term-input');
    const termAttachBtn  = $id('term-attach-btn');
    const termAttachIn   = $id('term-attach-input');
    const termClearBtn   = $id('term-clear-btn');
    const termHelpBtn    = $id('term-help-btn');
    const termHistoryBtn   = $id('term-history-btn');
    const termNewBtn       = $id('term-new-btn');
    const termHistoryPanel = $id('term-history-panel');
    const termHistoryList  = $id('term-history-list');
    const termHistoryClose = $id('term-history-close');
    const termFileInfo   = $id('term-file-info');
    const termPromptLbl  = $id('term-prompt-label');
    if (termPromptLbl && username) termPromptLbl.textContent = `${username}@ollama:~$`;

    if (modelLbl && window.__AI_OLLAMA_MODEL) modelLbl.textContent = window.__AI_OLLAMA_MODEL;

    // ── Active conversation tracking ──────────────────────────────────────
    let activeConversationId = null;
    let forceNewConversation = false;

    // ── Abrir / fechar ────────────────────────────────────────────────────
    function openChat() {
      box.classList.add('open');
      box.setAttribute('aria-hidden', 'false');
      document.body.classList.add('chat-open');
      input.focus();
    }
    function closeChat() {
      box.classList.remove('open', 'fullscreen');
      box.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('chat-open');
    }

    toggle.addEventListener('click', () => box.classList.contains('open') ? closeChat() : openChat());
    closeBtn.addEventListener('click', closeChat);
    fullBtn.addEventListener('click', () => {
      box.classList.toggle('fullscreen');
      if (box.classList.contains('fullscreen')) {
        box.style.left = box.style.top = box.style.right = box.style.bottom = '';
      }
      setTimeout(() => msgs.scrollTop = msgs.scrollHeight, 120);
    });

    // ── Draggable widget ──────────────────────────────────────────────────
    let isDragging = false, dragOffX = 0, dragOffY = 0;

    function startDrag(clientX, clientY) {
      if (box.classList.contains('fullscreen')) return;
      isDragging = true;
      const rect = box.getBoundingClientRect();
      dragOffX = clientX - rect.left;
      dragOffY = clientY - rect.top;
      box.style.transition = 'none';
      header.style.cursor = 'grabbing';
    }
    function moveDrag(clientX, clientY) {
      if (!isDragging) return;
      let x = clientX - dragOffX;
      let y = clientY - dragOffY;
      x = Math.max(0, Math.min(x, window.innerWidth  - box.offsetWidth));
      y = Math.max(0, Math.min(y, window.innerHeight - box.offsetHeight));
      box.style.left   = x + 'px';
      box.style.top    = y + 'px';
      box.style.right  = 'auto';
      box.style.bottom = 'auto';
    }
    function endDrag() {
      if (!isDragging) return;
      isDragging = false;
      box.style.transition = '';
      header.style.cursor = 'grab';
      if (box.style.left) {
        localStorage.setItem('ai_chat_pos', JSON.stringify({ left: box.style.left, top: box.style.top }));
      }
    }

    header.style.cursor = 'grab';
    header.addEventListener('mousedown', e => { if (!e.target.closest('.icon-btn')) { startDrag(e.clientX, e.clientY); e.preventDefault(); } });
    document.addEventListener('mousemove', e => moveDrag(e.clientX, e.clientY));
    document.addEventListener('mouseup', endDrag);

    header.addEventListener('touchstart', e => {
      if (!e.target.closest('.icon-btn')) { startDrag(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault(); }
    }, { passive: false });
    document.addEventListener('touchmove', e => {
      if (isDragging) { moveDrag(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault(); }
    }, { passive: false });
    document.addEventListener('touchend', endDrag);

    try {
      const pos = JSON.parse(localStorage.getItem('ai_chat_pos') || 'null');
      if (pos && pos.left) { box.style.left = pos.left; box.style.top = pos.top; box.style.right = 'auto'; box.style.bottom = 'auto'; }
    } catch {}

    // ── Auto-resize textarea ──────────────────────────────────────────────
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); }
    });
    input.addEventListener('focus', () => {
      if (window.innerWidth <= 768) setTimeout(() => input.scrollIntoView({ behavior: 'smooth', block: 'center' }), 300);
    });

    // ── Anexos ───────────────────────────────────────────────────────────
    const MAX_FILE_BYTES = 200 * 1024 * 1024;
    const MAX_TOTAL_BYTES = 200 * 1024 * 1024;
    let attachedFiles = [];

    attachBtn.addEventListener('click', () => attachInput.click());
    attachInput.addEventListener('change', () => {
      const files = Array.from(attachInput.files);
      let totalUsed = attachedFiles.reduce((s, f) => s + f.content.length, 0);
      files.forEach(file => {
        if (file.size > MAX_FILE_BYTES) { alert(`"${file.name}" muito grande (máx 200 MB).`); return; }
        if (totalUsed + file.size > MAX_TOTAL_BYTES) { alert('Total excede 200 MB.'); return; }
        totalUsed += file.size;
        const reader = new FileReader();
        reader.onload = ev => { attachedFiles.push({ name: file.name, content: ev.target.result }); renderAttachments(); };
        reader.onerror = () => alert(`Erro ao ler "${file.name}".`);
        reader.readAsText(file, 'UTF-8');
      });
      attachInput.value = '';
    });

    function renderAttachments() {
      if (!attachedFiles.length) { attachBar.style.display = 'none'; attachBar.innerHTML = ''; return; }
      attachBar.style.display = 'flex'; attachBar.innerHTML = '';
      attachedFiles.forEach((f, i) => {
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';
        chip.innerHTML = `<span class="chip-icon">📄</span><span class="chip-name" title="${f.name}">${f.name}</span><button type="button" class="chip-remove">✕</button>`;
        chip.querySelector('.chip-remove').addEventListener('click', () => { attachedFiles.splice(i, 1); renderAttachments(); });
        attachBar.appendChild(chip);
      });
    }
    function clearAttachments() { attachedFiles = []; renderAttachments(); }

    // ── Stop ─────────────────────────────────────────────────────────────
    let currentController = null;
    stopBtn.addEventListener('click', () => { if (currentController) { currentController.abort(); currentController = null; } });
    function setStreaming(active) { stopBtn.style.display = active ? 'flex' : 'none'; sendBtn.disabled = active; }

    // ── Conversation banner ───────────────────────────────────────────────
    let convBanner = null;
    function showConvBanner(title) {
      if (convBanner) convBanner.remove();
      convBanner = document.createElement('div');
      convBanner.className = 'conv-banner';
      convBanner.innerHTML = `<span>💬 Continuando: <strong>${title}</strong></span><button type="button" class="conv-banner-new" title="Nova conversa">+ Nova</button>`;
      convBanner.querySelector('.conv-banner-new').addEventListener('click', () => {
        activeConversationId = null;
        forceNewConversation = true;
        convBanner.remove(); convBanner = null;
        msgs.innerHTML = ''; showWelcome();
      });
      msgs.parentNode.insertBefore(convBanner, msgs);
    }

    // ── Append message ────────────────────────────────────────────────────
    function appendMessage(sender, text, skipNote) {
      const parsed = parseThinking(text);
      let displayText = parsed.response;
      let noteData = null;

      if (!skipNote) {
        noteData = extractNoteAction(displayText);
        if (noteData) displayText = displayText.replace(/\[CRIAR_NOTA:\{[\s\S]*?\}\]/g, '').trimEnd();
      }

      const wrapper = document.createElement('div');
      wrapper.className = 'msg-wrapper ' + (sender === 'user' ? 'user-wrapper' : 'bot-wrapper');

      if (sender !== 'user' && parsed.thinking) {
        wrapper.appendChild(buildThinkingPanel(parsed.thinking, false));
      }

      const el = document.createElement('div');
      el.classList.add('message', sender === 'user' ? 'user-msg' : 'bot-msg');
      el.innerHTML = renderMarkdown(displayText);

      if (sender === 'bot') {
        const copy = document.createElement('button');
        copy.className = 'msg-copy-btn'; copy.title = 'Copiar'; copy.textContent = '⎘';
        copy.addEventListener('click', () => copyText(el.dataset.raw || el.innerText).then(() => { copy.textContent = '✓'; setTimeout(() => copy.textContent = '⎘', 1500); }));
        el.dataset.raw = displayText;
        el.appendChild(copy);
        if (noteData) el.appendChild(buildNoteConfirm(noteData));
      }

      wrapper.appendChild(el);
      msgs.appendChild(wrapper);
      msgs.scrollTop = msgs.scrollHeight;
      return el;
    }

    // ── Thinking panel builder ────────────────────────────────────────────
    function buildThinkingPanel(thinkText, isStreaming) {
      const panel = document.createElement('div');
      panel.className = 'thinking-panel' + (isStreaming ? ' thinking-active' : ' thinking-done');

      const toggle = document.createElement('button');
      toggle.className = 'thinking-toggle';
      toggle.type = 'button';
      toggle.innerHTML = isStreaming
        ? '<span class="thinking-spinner"></span> <span class="thinking-label">Pensando…</span> <span class="thinking-chevron">▾</span>'
        : '🧠 <span class="thinking-label">Raciocínio</span> <span class="thinking-chevron">▾</span>';

      const content = document.createElement('div');
      content.className = 'thinking-content';
      content.textContent = thinkText || '';

      let collapsed = false;
      toggle.addEventListener('click', () => {
        collapsed = !collapsed;
        content.style.display = collapsed ? 'none' : '';
        toggle.querySelector('.thinking-chevron').textContent = collapsed ? '▸' : '▾';
      });

      panel.appendChild(toggle);
      panel.appendChild(content);
      return panel;
    }

    function buildNoteConfirm(noteData) {
      const bar = document.createElement('div');
      bar.className = 'note-confirm-bar';
      bar.innerHTML = `<span>📝 Criar: <strong>${noteData.title}</strong>${noteData.folder_name ? ` em <em>${noteData.folder_name}</em>` : ''}</span><button class="note-confirm-btn" type="button">✓ Salvar</button><button class="note-cancel-btn" type="button">✕</button>`;
      bar.querySelector('.note-confirm-btn').addEventListener('click', async () => {
        bar.innerHTML = '<span style="color:var(--ai-cyan)">Salvando…</span>';
        try {
          const r = await fetch('/ai_assistant/api/create_note/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() || '' }, body: JSON.stringify(noteData) });
          const d = await r.json();
          bar.innerHTML = d.success ? `✅ Nota "<strong>${d.title}</strong>" salva! <a href="${d.url}" target="_blank">Abrir</a>` : '❌ Erro ao salvar.';
        } catch { bar.innerHTML = '❌ Erro ao salvar.'; }
      });
      bar.querySelector('.note-cancel-btn').addEventListener('click', () => bar.remove());
      return bar;
    }

    function appendTyping() {
      const el = document.createElement('div');
      el.className = 'message bot-msg typing-indicator';
      el.innerHTML = '<span></span><span></span><span></span>';
      msgs.appendChild(el); msgs.scrollTop = msgs.scrollHeight;
      return el;
    }

    // ── Welcome + suggestions ─────────────────────────────────────────────
    function showWelcome() {
      appendMessage('bot', `Olá, **${username || 'usuário'}**! 🤖 Em que posso te ajudar hoje?`, true);
      const suggestions = [
        "Quais são os últimos CVEs que adicionei?", "Me mostre os dorks Shodan mais recentes.",
        "Você pode listar minhas ferramentas de pentest?", "Qual é o status do meu armazenamento?",
        "Quais foram minhas últimas notas salvas?", "Liste os arquivos que subi recentemente.",
        "Você consegue me mostrar os links que adicionei?", "Me mostra meus projetos e seus itens.",
        "Tem algum canal do YouTube salvo?", "Como funciona o sistema GDriver?",
      ];
      const sugBox = document.createElement('div'); sugBox.className = 'chat-suggestions';
      suggestions.forEach(s => {
        const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'suggestion-btn'; btn.textContent = s;
        btn.addEventListener('click', () => { input.value = s; form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
        sugBox.appendChild(btn);
      });
      msgs.appendChild(sugBox); msgs.scrollTop = msgs.scrollHeight;
    }

    // ── Restore active conversation on init ───────────────────────────────
    if (isAuthenticated) {
      fetch('/ai_assistant/api/current_messages/')
        .then(r => r.json())
        .then(data => {
          if (data.messages && data.messages.length > 0) {
            msgs.innerHTML = '';
            data.messages.forEach(m => appendMessage(m.sender === 'user' ? 'user' : 'bot', m.content, true));
          } else { showWelcome(); }
        })
        .catch(() => showWelcome());
    } else { showWelcome(); }

    // ── Stream request ────────────────────────────────────────────────────
    async function streamRequest(body, onChunk, signal) {
      if (!isAuthenticated) throw new Error('Login necessário');
      const resp = await fetch('/ai_assistant/chat/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), signal,
      });
      if (!resp.ok) throw new Error('Erro do servidor: ' + resp.status);
      const reader = resp.body.getReader(), dec = new TextDecoder('utf-8');
      let first = true;
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        onChunk(dec.decode(value, { stream: true }), first); first = false;
      }
    }

    // ── Submit ────────────────────────────────────────────────────────────
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text && !attachedFiles.length) return;

      let displayText = text;
      if (attachedFiles.length) {
        const names = attachedFiles.map(f => `📄 ${f.name}`).join(', ');
        displayText = (text ? text + '\n' : '') + `_Anexos: ${names}_`;
      }
      appendMessage('user', displayText || `_Enviando ${attachedFiles.length} arquivo(s)…_`, true);

      const combinedAttachment = attachedFiles.length
        ? attachedFiles.map(f => `=== ${f.name} ===\n${f.content}`).join('\n\n') : undefined;

      input.value = ''; input.style.height = 'auto';
      clearAttachments(); setStreaming(true);

      const isForceNew = forceNewConversation;
      forceNewConversation = false;

      currentController = new AbortController();
      const signal = currentController.signal;
      const typing = appendTyping();

      let wrapperEl    = null;
      let thinkingEl   = null;
      let thinkContent = null;
      let responseEl   = null;
      let copyBtn      = null;

      // Função chamada pelo typewriter a cada caractere/bloco revelado.
      // `revealedRaw` é o texto acumulado até aqui (subset do total já streamado).
      function renderRevealed(revealedRaw) {
        const parsed = parseThinking(revealedRaw);

        if (!wrapperEl) {
          typing.remove();
          wrapperEl = document.createElement('div');
          wrapperEl.className = 'msg-wrapper bot-wrapper';
          msgs.appendChild(wrapperEl);
        }
        if (!responseEl) {
          responseEl = document.createElement('div');
          responseEl.className = 'message bot-msg';
          responseEl.dataset.raw = '';
          copyBtn = document.createElement('button');
          copyBtn.className = 'msg-copy-btn';
          copyBtn.title = 'Copiar';
          copyBtn.textContent = '⎘';
          copyBtn.addEventListener('click', () =>
            copyText(responseEl.dataset.raw || responseEl.innerText).then(() => {
              copyBtn.textContent = '✓';
              setTimeout(() => copyBtn.textContent = '⎘', 1500);
            })
          );
          wrapperEl.appendChild(responseEl);
        }
        if (parsed.thinking !== null) {
          if (!thinkingEl) {
            thinkingEl = buildThinkingPanel('', true);
            thinkContent = thinkingEl.querySelector('.thinking-content');
            wrapperEl.insertBefore(thinkingEl, responseEl);
          }
          thinkContent.textContent = parsed.thinking;
          if (!parsed.inThinking) {
            thinkingEl.classList.remove('thinking-active');
            thinkingEl.classList.add('thinking-done');
            const lbl = thinkingEl.querySelector('.thinking-label');
            const spn = thinkingEl.querySelector('.thinking-spinner');
            if (lbl) lbl.textContent = 'Raciocínio';
            if (spn) spn.remove();
            const ico = document.createElement('span');
            ico.textContent = '🧠 ';
            thinkingEl.querySelector('.thinking-toggle').prepend(ico);
          }
        }
        const cleanResp = parsed.response
          .replace(/\[CRIAR_NOTA:\{[\s\S]*?\}\]/g, '')
          .trimStart();
        responseEl.dataset.raw = cleanResp || '(aguardando resposta…)';
        responseEl.innerHTML = renderMarkdown(cleanResp || '*— aguardando resposta —*');
        if (copyBtn && !responseEl.contains(copyBtn)) {
          responseEl.appendChild(copyBtn);
        }
        msgs.scrollTop = msgs.scrollHeight;
      }

      // Typewriter: revela os chunks caractere a caractere (efeito "digitando").
      let writerResolve;
      const writerDone = new Promise(res => { writerResolve = res; });
      const writer = createTypewriter(renderRevealed, {
        onFinish: () => writerResolve && writerResolve(),
      });

      try {
        await streamRequest(
          {
            prompt: text || '(sem texto)',
            attachment_text: combinedAttachment,
            conversation_id: isForceNew ? null : activeConversationId,
            force_new: isForceNew || undefined,
          },
          (chunk) => { writer.push(chunk); },
          signal
        );

        // Sinaliza fim do stream e aguarda typewriter terminar de "digitar".
        writer.end();
        await writerDone;

        if (responseEl && (!responseEl.dataset.raw || responseEl.dataset.raw === '(aguardando resposta…)')) {
          responseEl.dataset.raw = '(sem resposta)';
          responseEl.innerHTML = renderMarkdown('*— sem resposta —*');
        }

        if (responseEl) {
          const noteData = extractNoteAction(writer.raw());
          if (noteData) responseEl.appendChild(buildNoteConfirm(noteData));
        }

      } catch (err) {
        typing.remove();
        // Em qualquer erro, revela imediatamente o que já tinha sido streamado.
        try { writer.flush(); } catch (_) {}
        if (err.name === 'AbortError') {
          if (responseEl && responseEl.dataset) {
            responseEl.dataset.raw += '\n\n_— resposta interrompida —_';
            responseEl.innerHTML = renderMarkdown(responseEl.dataset.raw.replace(/\[CRIAR_NOTA:\{[\s\S]*?\}\]/g, ''));
            if (copyBtn && !responseEl.contains(copyBtn)) responseEl.appendChild(copyBtn);
          } else {
            appendMessage('bot', '_— resposta interrompida —_', true);
          }
        } else {
          appendMessage('bot', `❌ **Erro:** ${err.message || err}`, true);
        }
      } finally {
        currentController = null;
        setStreaming(false);
        input.focus();
      }
    });

    // ── Histórico ─────────────────────────────────────────────────────────
    histBtn.addEventListener('click', () => {
      const visible = histPanel.style.display !== 'none';
      if (visible) { histPanel.style.display = 'none'; msgs.style.display = ''; return; }
      msgs.style.display = 'none'; histPanel.style.display = 'flex';
      histList.innerHTML = '<div class="hist-loading">Carregando…</div>';
      fetch('/ai_assistant/api/conversations/')
        .then(r => r.json())
        .then(data => {
          histList.innerHTML = '';
          if (!data.conversations || !data.conversations.length) {
            histList.innerHTML = '<div class="hist-empty">Nenhuma conversa ainda.</div>'; return;
          }
          data.conversations.forEach(conv => {
            const card = document.createElement('div');
            card.className = 'history-card';
            card.innerHTML = `
              <div class="hcard-title">${conv.title}</div>
              <div class="hcard-meta">${conv.updated_at} &middot; ${conv.message_count} msgs</div>
              ${conv.preview ? `<div class="hcard-preview">${conv.preview}</div>` : ''}
            `;
            card.addEventListener('click', async () => {
              card.style.opacity = '.5';
              try {
                const r = await fetch(`/ai_assistant/api/conversation/${conv.id}/messages/`);
                const d = await r.json();
                histPanel.style.display = 'none'; msgs.style.display = '';
                msgs.innerHTML = '';
                activeConversationId = conv.id;
                d.messages.forEach(m => appendMessage(m.sender === 'user' ? 'user' : 'bot', m.content, true));
                showConvBanner(conv.title);
                msgs.scrollTop = msgs.scrollHeight;
                input.focus();
              } catch { card.style.opacity = '1'; alert('Erro ao carregar conversa.'); }
            });
            histList.appendChild(card);
          });
        })
        .catch(() => { histList.innerHTML = '<div class="hist-empty" style="color:#f88">Erro ao carregar.</div>'; });
    });

    histClose.addEventListener('click', () => { histPanel.style.display = 'none'; msgs.style.display = ''; });

    // ── Nova conversa ─────────────────────────────────────────────────────
    endBtn.addEventListener('click', () => {
      if (!confirm('Iniciar uma nova conversa? A conversa atual será salva no histórico.')) return;
      activeConversationId = null;
      forceNewConversation = true;
      msgs.innerHTML = '';
      if (convBanner) { convBanner.remove(); convBanner = null; }
      showWelcome();
      input.focus();
    });

    // ── Modal de conversa ─────────────────────────────────────────────────
    function openConversationModal(url) {
      const modalEl = $id('conversationModal'), body = $id('conversationModalBody');
      if (!modalEl) return;
      body.innerHTML = '<div style="text-align:center;padding:32px;"><div style="width:28px;height:28px;border-radius:50%;border:3px solid rgba(0,255,200,.15);border-top-color:#00ffc8;animation:spin 1s linear infinite;display:inline-block;"></div></div>';
      const bsModal = window.bootstrap && bootstrap.Modal ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;
      if (bsModal) bsModal.show(); else { modalEl.style.display = 'block'; modalEl.classList.add('show'); }
      fetch(url).then(r => r.text()).then(html => { body.innerHTML = html; }).catch(() => { body.innerHTML = '<p style="color:#f88;padding:20px;">Erro ao carregar.</p>'; });
    }

    document.body.addEventListener('click', e => {
      const btn = e.target.closest('.open-conversation');
      if (btn) { e.preventDefault(); openConversationModal(btn.dataset.url); }
      const modal = $id('conversationModal');
      if (modal && e.target === modal) { modal.style.display = 'none'; modal.classList.remove('show'); }
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        const modalEl = $id('conversationModal');
        if (modalEl) {
          const bsM = window.bootstrap && bootstrap.Modal.getInstance(modalEl);
          if (bsM) bsM.hide(); else { modalEl.style.display = 'none'; modalEl.classList.remove('show'); }
        }
        closeChat();
      }
    });

    // ════════════════════════════════════════════════════════════════════
    // ── MODO TERMINAL ───────────────────────────────────────────────────
    // Interface CLI que usa Ollama diretamente (sem pipeline RAG).
    // Mais rápido. Anexo de arquivo é feito pelo botão da toolbar e o
    // arquivo passa a ser contexto automático das próximas perguntas.
    // ════════════════════════════════════════════════════════════════════
    const MAX_TERM_FILE_BYTES = 200 * 1024 * 1024;
    let termMode = false;
    let termAttachedFile = null;          // { name, content }
    let termController   = null;
    let termBusy         = false;
    let termHistory      = [];
    let termHistoryIdx   = -1;
    // Modelo ativo no terminal (pode ser trocado com /model <nome>)
    let termActiveModel  = window.__AI_OLLAMA_MODEL || null;
    // Conversa ativa do terminal (id da Conversation persistida no servidor)
    let termActiveConversationId = null;
    let termForceNewConversation = false;

    function termAppendLine(cls, text) {
      const line = document.createElement('div');
      line.className = 'term-line ' + cls;
      line.textContent = text;
      termOutput.appendChild(line);
      termOutput.scrollTop = termOutput.scrollHeight;
      return line;
    }

    function termAppendHTML(cls, html) {
      const line = document.createElement('div');
      line.className = 'term-line ' + cls;
      line.innerHTML = html;
      termOutput.appendChild(line);
      termOutput.scrollTop = termOutput.scrollHeight;
      return line;
    }

    function termShowBanner() {
      termOutput.innerHTML = '';
      termAppendLine('term-line-info', '╔══════════════════════════════════════════════════╗');
      termAppendLine('term-line-info', '║      MODO TERMINAL — Ollama direto (fast)         ║');
      termAppendLine('term-line-info', '╚══════════════════════════════════════════════════╝');
      termAppendLine('term-line-sys',  `Modelo ativo: ${termActiveModel || '(padrão do servidor)'}`);
      termAppendLine('term-line-sys',  'Comandos: /help  /clear  /attach  /detach  /models  /model <nome>  /exit');
      termAppendLine('term-line-sys',  'Dica: Setas ↑/↓ navegam no histórico. ESC cancela resposta.');
      termAppendLine('term-line-sys',  '');
    }

    async function termListModels() {
      termAppendLine('term-line-sys', '[sistema] buscando modelos no Ollama…');
      try {
        const r = await fetch('/ai_assistant/api/ollama_tags/');
        const d = await r.json();
        if (!d.models || !d.models.length) {
          termAppendLine('term-line-err',
            `[erro] nenhum modelo instalado${d.error ? ' ('+d.error+')' : ''}. ` +
            'Use `ollama pull <nome>` para baixar um.');
          return;
        }
        termAppendLine('term-line-info', `Modelos disponíveis (${d.models.length}):`);
        d.models.forEach(m => {
          const marker = (termActiveModel === m) ? '▸ ' : '  ';
          termAppendLine('term-line-bot', `${marker}${m}`);
        });
        termAppendLine('term-line-sys', 'Use `/model <nome>` para trocar.');
        termAppendLine('term-line-sys', '');
      } catch (e) {
        termAppendLine('term-line-err', `[erro] ${e.message || e}`);
      }
    }

    function termSetModel(name) {
      name = (name || '').trim();
      if (!name) {
        termAppendLine('term-line-info', `Modelo ativo: ${termActiveModel || '(padrão do servidor)'}`);
        termAppendLine('term-line-sys', 'Uso: /model <nome>  (ou /model default para voltar ao padrão)');
        return;
      }
      if (name === 'default' || name === 'padrão') {
        termActiveModel = null;
        termAppendLine('term-line-info', '[sistema] voltando ao modelo padrão do servidor.');
        return;
      }
      termActiveModel = name;
      termAppendLine('term-line-info', `[sistema] modelo ativo agora: ${name}`);
    }

    function termUpdateFileInfo() {
      if (!termFileInfo) return;
      if (termAttachedFile) {
        termFileInfo.classList.remove('empty');
        termFileInfo.textContent = `📄 ${termAttachedFile.name} (${termAttachedFile.content.length.toLocaleString()} chars)`;
        termFileInfo.title = termAttachedFile.name;
      } else {
        termFileInfo.classList.add('empty');
        termFileInfo.textContent = '[nenhum arquivo anexado]';
        termFileInfo.title = '';
      }
    }

    let termFirstEnter = true;

    async function termRestoreActive() {
      try {
        const r = await fetch('/ai_assistant/api/current_messages/?mode=terminal');
        const d = await r.json();
        if (d && d.id && d.messages && d.messages.length) {
          termActiveConversationId = d.id;
          termHistoryRestoreMessages(d.messages, d.title);
          return true;
        }
      } catch (_) {}
      return false;
    }

    function enterTerminalMode() {
      termMode = true;
      box.classList.add('terminal-mode');
      termToggle.classList.add('active');
      termToggle.title = 'Sair do Modo Terminal';
      termPanel.setAttribute('aria-hidden', 'false');
      if (!termOutput.children.length) termShowBanner();
      termUpdateFileInfo();
      // Na primeira abertura, tenta restaurar a conversa ativa do terminal (últimas 24h).
      if (termFirstEnter && isAuthenticated) {
        termFirstEnter = false;
        termRestoreActive();
      }
      setTimeout(() => termInput && termInput.focus(), 50);
    }
    function exitTerminalMode() {
      termMode = false;
      if (termController) { try { termController.abort(); } catch(_){} termController = null; }
      termBusy = false;
      box.classList.remove('terminal-mode');
      termToggle.classList.remove('active');
      termToggle.title = 'Modo Terminal (Ollama direto)';
      termPanel.setAttribute('aria-hidden', 'true');
      setTimeout(() => input && input.focus(), 50);
    }
    termToggle.addEventListener('click', () => {
      if (termMode) exitTerminalMode();
      else {
        if (!box.classList.contains('open')) openChat();
        enterTerminalMode();
      }
    });

    // Limpar tela
    termClearBtn.addEventListener('click', () => { termOutput.innerHTML = ''; termInput.focus(); });

    // Histórico
    if (termHistoryBtn) termHistoryBtn.addEventListener('click', () => {
      const visible = termHistoryPanel && termHistoryPanel.style.display !== 'none';
      if (visible) termHistoryClosePanel();
      else termOpenHistoryPanel();
    });
    if (termHistoryClose) termHistoryClose.addEventListener('click', termHistoryClosePanel);
    if (termNewBtn) termNewBtn.addEventListener('click', () => termNewConversation(false));

    // Ajuda
    termHelpBtn.addEventListener('click', () => {
      termAppendLine('term-line-sys', '── Ajuda ─────────────────────────────────');
      termAppendLine('term-line-sys', '/help            → mostra esta ajuda');
      termAppendLine('term-line-sys', '/clear           → limpa a tela');
      termAppendLine('term-line-sys', '/attach          → abre diálogo para anexar arquivo');
      termAppendLine('term-line-sys', '/detach          → remove o arquivo anexado');
      termAppendLine('term-line-sys', '/models          → lista modelos instalados no Ollama');
      termAppendLine('term-line-sys', '/model <nome>    → troca o modelo ativo (ex: /model phi3.5)');
      termAppendLine('term-line-sys', '/model default   → volta para o modelo padrão do servidor');
      termAppendLine('term-line-sys', '/history         → lista conversas anteriores do terminal');
      termAppendLine('term-line-sys', '/load <id>       → retoma uma conversa pelo id');
      termAppendLine('term-line-sys', '/new             → inicia uma nova conversa de terminal');
      termAppendLine('term-line-sys', '/exit            → fecha o modo terminal');
      termAppendLine('term-line-sys', 'ESC              → interrompe resposta em andamento');
      termAppendLine('term-line-sys', `Modelo ativo: ${termActiveModel || '(padrão do servidor)'}`);
      termAppendLine('term-line-sys', `Conversa ativa: ${termActiveConversationId ? '#' + termActiveConversationId : '(nova ao próximo envio)'}`);
      termAppendLine('term-line-sys', 'Qualquer outro texto é enviado como pergunta.');
      termAppendLine('term-line-sys', '');
      termInput.focus();
    });

    // Anexo dedicado do terminal
    termAttachBtn.addEventListener('click', () => termAttachIn.click());
    termAttachIn.addEventListener('change', () => {
      const f = termAttachIn.files && termAttachIn.files[0];
      if (!f) return;
      if (f.size > MAX_TERM_FILE_BYTES) {
        termAppendLine('term-line-err', `[erro] "${f.name}" excede o limite de 200 MB.`);
        termAttachIn.value = '';
        return;
      }
      termAppendLine('term-line-sys', `[sistema] lendo ${f.name}…`);
      const reader = new FileReader();
      reader.onload = ev => {
        termAttachedFile = { name: f.name, content: ev.target.result };
        termUpdateFileInfo();
        termAppendLine('term-line-info',
          `[sistema] arquivo carregado: ${f.name} (${termAttachedFile.content.length.toLocaleString()} chars). ` +
          `As próximas perguntas usarão este arquivo como contexto. Use /detach para remover.`);
        termAppendLine('term-line-sys', '');
        termInput.focus();
      };
      reader.onerror = () => termAppendLine('term-line-err', `[erro] falha ao ler "${f.name}".`);
      reader.readAsText(f, 'UTF-8');
      termAttachIn.value = '';
    });

    function termDetach() {
      if (!termAttachedFile) {
        termAppendLine('term-line-sys', '[sistema] nenhum arquivo anexado.');
        return;
      }
      const n = termAttachedFile.name;
      termAttachedFile = null;
      termUpdateFileInfo();
      termAppendLine('term-line-info', `[sistema] arquivo "${n}" removido do contexto.`);
    }

    // Stream para o endpoint /terminal/ (sem RAG)
    async function termStreamRequest(body, onChunk, signal) {
      if (!isAuthenticated) throw new Error('Login necessário');
      const resp = await fetch('/ai_assistant/terminal/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken() || '',
        },
        body: JSON.stringify(body),
        signal,
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      // Server devolve o id da conversa via header — guardamos para o próximo turno.
      const cid = resp.headers.get('X-Conversation-Id');
      if (cid) termActiveConversationId = parseInt(cid, 10) || termActiveConversationId;
      const reader = resp.body.getReader();
      const dec = new TextDecoder('utf-8');
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        onChunk(dec.decode(value, { stream: true }));
      }
    }

    // ── Histórico do terminal ────────────────────────────────────────────
    function termHistoryClosePanel() {
      if (!termHistoryPanel) return;
      termHistoryPanel.style.display = 'none';
      termOutput.style.display = '';
    }

    function termHistoryRestoreMessages(messages, title) {
      termOutput.innerHTML = '';
      termAppendLine('term-line-info', `── retomando: ${title || '(sem título)'} ──`);
      const promptTxt = termPromptLbl.textContent || 'user@ollama:~$';
      (messages || []).forEach(m => {
        if (m.sender === 'user') {
          termAppendHTML('term-line-user',
            `<span class="term-line-prompt">${promptTxt}</span> ${escapeHTML(m.content)}`);
        } else {
          termAppendLine('term-line-bot', m.content || '');
        }
      });
      termAppendLine('term-line-sys', '');
      termOutput.scrollTop = termOutput.scrollHeight;
    }

    async function termLoadConversation(convId) {
      try {
        const r = await fetch(`/ai_assistant/api/conversation/${convId}/messages/`);
        const d = await r.json();
        termHistoryClosePanel();
        termActiveConversationId = convId;
        termForceNewConversation = false;
        termHistoryRestoreMessages(d.messages || [], d.title);
        termInput.focus();
      } catch (e) {
        termAppendLine('term-line-err', `[erro] ao carregar conversa: ${e.message || e}`);
      }
    }

    async function termOpenHistoryPanel() {
      if (!termHistoryPanel) return;
      termOutput.style.display = 'none';
      termHistoryPanel.style.display = 'flex';
      termHistoryList.innerHTML = '<div class="hist-loading">Carregando…</div>';
      try {
        const r = await fetch('/ai_assistant/api/conversations/?mode=terminal');
        const d = await r.json();
        termHistoryList.innerHTML = '';
        if (!d.conversations || !d.conversations.length) {
          termHistoryList.innerHTML = '<div class="hist-empty">Nenhuma conversa de terminal ainda.</div>';
          return;
        }
        d.conversations.forEach(conv => {
          const card = document.createElement('div');
          card.className = 'history-card term-history-card';
          card.innerHTML = `
            <div class="hcard-title">${escapeHTML(conv.title || '(sem título)')}</div>
            <div class="hcard-meta">${escapeHTML(conv.updated_at || '')} · ${conv.message_count} msgs</div>
            ${conv.preview ? `<div class="hcard-preview">${escapeHTML(conv.preview)}</div>` : ''}
          `;
          card.addEventListener('click', () => {
            card.style.opacity = '.5';
            termLoadConversation(conv.id);
          });
          termHistoryList.appendChild(card);
        });
      } catch (e) {
        termHistoryList.innerHTML = '<div class="hist-empty" style="color:#f88">Erro ao carregar.</div>';
      }
    }

    async function termListHistoryInline() {
      termAppendLine('term-line-sys', '[sistema] buscando histórico do terminal…');
      try {
        const r = await fetch('/ai_assistant/api/conversations/?mode=terminal');
        const d = await r.json();
        if (!d.conversations || !d.conversations.length) {
          termAppendLine('term-line-info', 'Nenhuma conversa anterior. Comece a digitar para criar uma.');
          return;
        }
        termAppendLine('term-line-info', `Conversas anteriores (${d.conversations.length}):`);
        d.conversations.forEach((conv, idx) => {
          const marker = (termActiveConversationId === conv.id) ? '▸ ' : '  ';
          termAppendLine('term-line-bot',
            `${marker}[${idx + 1}] #${conv.id} · ${conv.updated_at} · ${conv.message_count}msg · ${conv.title || '(sem título)'}`);
        });
        termAppendLine('term-line-sys', 'Use /load <id> para retomar uma conversa, /new para começar outra.');
        termAppendLine('term-line-sys', '');
      } catch (e) {
        termAppendLine('term-line-err', `[erro] ${e.message || e}`);
      }
    }

    function termNewConversation(silent) {
      termActiveConversationId = null;
      termForceNewConversation = true;
      if (!silent) {
        termAppendLine('term-line-info', '[sistema] nova conversa de terminal iniciada.');
        termAppendLine('term-line-sys', '');
      }
    }

    async function termSubmit(raw) {
      if (termBusy) return;
      const text = (raw || '').trim();
      if (!text) return;

      // registrar no histórico
      termHistory.push(text);
      if (termHistory.length > 200) termHistory.shift();
      termHistoryIdx = termHistory.length;

      // Eco no terminal
      const promptTxt = termPromptLbl.textContent || 'user@ollama:~$';
      termAppendHTML('term-line-user',
        `<span class="term-line-prompt">${promptTxt}</span> ${escapeHTML(text)}`);

      // Comandos locais
      if (text === '/help' || text === 'help') {
        termHelpBtn.click();
        return;
      }
      if (text === '/clear' || text === 'clear' || text === 'cls') {
        termOutput.innerHTML = '';
        return;
      }
      if (text === '/exit' || text === 'exit' || text === 'quit') {
        termAppendLine('term-line-sys', '[sistema] saindo do modo terminal…');
        setTimeout(exitTerminalMode, 120);
        return;
      }
      if (text === '/attach') {
        termAttachIn.click();
        return;
      }
      if (text === '/detach') {
        termDetach();
        return;
      }
      if (text === '/models') {
        termListModels();
        return;
      }
      if (text.startsWith('/model ') || text === '/model') {
        termSetModel(text.slice(7));
        return;
      }
      if (text === '/history' || text === 'history') {
        termListHistoryInline();
        return;
      }
      if (text === '/new' || text === 'new') {
        termNewConversation(false);
        return;
      }
      if (text.startsWith('/load ') || text === '/load') {
        const arg = text.slice(6).trim();
        if (!arg) {
          termAppendLine('term-line-sys', 'Uso: /load <id>   (use /history para ver os ids)');
          return;
        }
        const cid = parseInt(arg.replace(/^#/, ''), 10);
        if (!cid) {
          termAppendLine('term-line-err', '[erro] id inválido.');
          return;
        }
        termLoadConversation(cid);
        return;
      }

      // Envia ao backend
      termBusy = true;
      termInput.disabled = true;
      const thinking = termAppendLine('term-line-bot term-thinking', 'processando');

      let botLine = null;

      // Typewriter: revela caractere a caractere como se estivesse digitando.
      // O terminal usa uma velocidade um pouco mais ágil (18ms) pra manter o
      // "ritmo de CLI" e não parecer preguiçoso.
      let termWriterResolve;
      const termWriterDone = new Promise(res => { termWriterResolve = res; });
      const termWriter = createTypewriter(
        (revealed) => {
          if (!botLine) {
            try { thinking.remove(); } catch(_){}
            botLine = document.createElement('div');
            botLine.className = 'term-line term-line-bot';
            termOutput.appendChild(botLine);
          }
          botLine.textContent = revealed;
          termOutput.scrollTop = termOutput.scrollHeight;
        },
        { speedMs: 18, onFinish: () => termWriterResolve && termWriterResolve() }
      );

      termController = new AbortController();
      const isForceNew = termForceNewConversation;
      termForceNewConversation = false;
      try {
        await termStreamRequest(
          {
            prompt: text,
            attachment_text: termAttachedFile ? termAttachedFile.content : undefined,
            attachment_name: termAttachedFile ? termAttachedFile.name : undefined,
            model: termActiveModel || undefined,
            conversation_id: isForceNew ? null : termActiveConversationId,
            force_new: isForceNew || undefined,
          },
          (chunk) => { termWriter.push(chunk); },
          termController.signal
        );
        termWriter.end();
        await termWriterDone;

        if (!termWriter.raw()) {
          try { thinking.remove(); } catch(_){}
          termAppendLine('term-line-err', '[sem resposta]');
        } else {
          termAppendLine('term-line-sys', '');
        }
      } catch (err) {
        // Em erro/abort: revela imediatamente tudo que já havia chegado.
        try { termWriter.flush(); } catch (_) {}
        try { thinking.remove(); } catch(_){}
        if (err && err.name === 'AbortError') {
          termAppendLine('term-line-err', '[interrompido]');
        } else {
          termAppendLine('term-line-err', `[erro] ${err && err.message || err}`);
        }
      } finally {
        termController = null;
        termBusy = false;
        termInput.disabled = false;
        termInput.focus();
      }
    }

    function escapeHTML(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // Enviar com Enter, setas navegam histórico, ESC cancela
    termInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const v = termInput.value;
        termInput.value = '';
        termSubmit(v);
      } else if (e.key === 'ArrowUp') {
        if (!termHistory.length) return;
        e.preventDefault();
        termHistoryIdx = Math.max(0, termHistoryIdx - 1);
        termInput.value = termHistory[termHistoryIdx] || '';
        setTimeout(() => termInput.setSelectionRange(termInput.value.length, termInput.value.length), 0);
      } else if (e.key === 'ArrowDown') {
        if (!termHistory.length) return;
        e.preventDefault();
        termHistoryIdx = Math.min(termHistory.length, termHistoryIdx + 1);
        termInput.value = termHistory[termHistoryIdx] || '';
      } else if (e.key === 'Escape') {
        if (termController) {
          e.preventDefault();
          try { termController.abort(); } catch(_){}
        }
      }
    });

    // Expor controle do terminal
    window.__ai_assistant_terminal = {
      enter: enterTerminalMode,
      exit:  exitTerminalMode,
      isActive: () => termMode,
    };

    window.__ai_assistant = { open: openChat, close: closeChat };
  }

  document.addEventListener('DOMContentLoaded', () => {
    initWidget(window.__AI_ASSISTANT_USERNAME || null, !!window.__AI_ASSISTANT_AUTH);
  });
})();