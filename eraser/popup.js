document.addEventListener('DOMContentLoaded', function() {
  const toolButtons = document.querySelectorAll('.tool-btn');
  const sizeSlider = document.getElementById('sizeSlider');
  const featherSlider = document.getElementById('featherSlider');
  const sizeValue = document.getElementById('sizeValue');
  const featherValue = document.getElementById('featherValue');
  const activateBtn = document.getElementById('activateBtn');
  const resetBtn = document.getElementById('resetBtn');
  const saveBtn = document.getElementById('saveBtn');
  const autoSaveBtn = document.getElementById('autoSaveBtn');
  const status = document.getElementById('status');

  let currentTool = 'circle';

  toolButtons.forEach(btn => {
    btn.addEventListener('click', function() {
      toolButtons.forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      currentTool = this.dataset.tool;
    });
  });

  sizeSlider.addEventListener('input', function() {
    sizeValue.textContent = this.value;
  });

  featherSlider.addEventListener('input', function() {
    featherValue.textContent = this.value + '%';
  });

  activateBtn.addEventListener('click', async function() {
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});

      await chrome.scripting.executeScript({
        target: {tabId: tab.id},
        files: ['content.js']
      });

      await chrome.tabs.sendMessage(tab.id, {
        action: 'init',
        tool: currentTool,
        size: parseInt(sizeSlider.value),
        feather: parseInt(featherSlider.value) / 100
      });
      
      status.textContent = '工具已激活！请在页面上操作图像';
      status.className = 'status success';

    } catch (error) {
      status.textContent = '激活失败，请确保在正确的页面';
      status.className = 'status info';
    }
  });

  resetBtn.addEventListener('click', async function() {
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      await chrome.tabs.sendMessage(tab.id, {action: 'reset'});
      status.textContent = '已重置工具';
      status.className = 'status info';
    } catch (error) {
    }
  });

  saveBtn.addEventListener('click', async function() {
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      await chrome.tabs.sendMessage(tab.id, {action: 'save'});
      status.textContent = '图像已保存';
      status.className = 'status success';
    } catch (error) {
      status.textContent = '保存失败';
      status.className = 'status info';
    }
  });

  autoSaveBtn.addEventListener('click', async function() {
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      await chrome.tabs.sendMessage(tab.id, {action: 'autoSave'});
      status.textContent = '已自动保存并覆盖原图';
      status.className = 'status success';
    } catch (error) {
      status.textContent = '自动保存失败';
      status.className = 'status info';
    }
  });
});