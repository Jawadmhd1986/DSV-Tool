// static/chatbot.js

// 🚀 Confirm the file is actually loading
console.log('chatbot.js loaded');

// 🔧 Fix for mobile viewport height
window.addEventListener('load', () => {
  let vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
});
window.addEventListener('resize', () => {
  let vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
});

// 🧠 Main chatbot logic, fires once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const chatBox    = document.getElementById('chat-box');
  const chatToggle = document.querySelector('.chat-toggle');
  const chatClose  = document.getElementById('chat-close');
  const sendBtn    = document.getElementById('chat-send');
  const inputEl    = document.getElementById('chat-input');
  const msgsEl     = document.getElementById('chat-messages');

  chatToggle.addEventListener('click', () => chatBox.classList.toggle('open'));
  chatClose .addEventListener('click', () => chatBox.classList.remove('open'));
  sendBtn   .addEventListener('click', sendMessage);
  inputEl   .addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // 🟢 Debugged sendMessage
  async function sendMessage() {
    console.log('🟢 sendMessage() called; input=', inputEl.value);
    const text = inputEl.value.trim();
    if (!text) return;

    appendMessage('user', text);
    inputEl.value = '';

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text })
      });
      const { reply } = await res.json();
      appendMessage('bot', reply, true);
    } catch (err) {
      console.error('Chat request failed', err);
      appendMessage('bot', 'Sorry, something went wrong.');
    }
  }

  // Helper to append a chat bubble
  function appendMessage(sender, text, typewriter = false) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${sender}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    wrapper.appendChild(bubble);
    msgsEl.appendChild(wrapper);
    msgsEl.scrollTop = msgsEl.scrollHeight;

    if (!typewriter) {
      bubble.textContent = text;
    } else {
      let i = 0;
      ;(function typeChar() {
        if (i < text.length) {
          bubble.textContent += text.charAt(i++);
          msgsEl.scrollTop = msgsEl.scrollHeight;
          setTimeout(typeChar, 15);
        }
      })();
    }
  }
});
