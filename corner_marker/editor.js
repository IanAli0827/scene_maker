// 标注工具 - 独立页面版本
class CornerMarker {
  constructor() {
    this.canvas = document.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.img = null;
    this.points = [];
    this.dragging = -1;
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.panning = false;
    this.panStartX = 0;
    this.panStartY = 0;
    this.currentSceneName = null;
    this.statusTimeout = null;
    this.hoverRadius = 20;
    this.outputFileHandle = null;
    this.outputFormat = 'yaml'; // 默认使用 yaml 格式
    this.originalYamlContent = null; // 保存原始 yaml 内容
    this.selectedRugSize = '8x10'; // 默认地毯尺寸
    this.imageFileHandle = null; // 保存图片文件句柄
    this.directoryHandle = null; // 保存目录句柄
    this.dashOffset = 0; // 虚线动画偏移

    this.coordInputs = document.querySelectorAll('.coord-input');
    this.statusEl = document.getElementById('status');
    this.infoEl = document.getElementById('info');

    this.init();
  }

  async init() {
    this.bindEvents();
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());

    // 启动虚线动画
    this.startDashAnimation();
  }

  startDashAnimation() {
    const animate = () => {
      this.dashOffset -= 0.5;
      if (this.img && this.points.length === 4) {
        this.render();
      }
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }

  resizeCanvas() {
    const container = document.querySelector('.canvas-container');
    this.canvas.width = container.clientWidth - 40;
    this.canvas.height = container.clientHeight - 40;
    this.render();
  }

  bindEvents() {
    const loadImgBtn = document.getElementById('loadImgBtn');
    const saveBtn = document.getElementById('saveBtn');
    const resetBtn = document.getElementById('resetBtn');
    const sizeSelect = document.getElementById('sizeSelect');

    loadImgBtn.addEventListener('click', () => this.loadImageWithPicker());
    saveBtn.addEventListener('click', () => this.savePoints());
    resetBtn.addEventListener('click', () => this.resetPoints());
    sizeSelect.addEventListener('change', (e) => this.handleSizeChange(e));

    this.coordInputs.forEach(input => {
      input.addEventListener('input', (e) => this.handleCoordInput(e));
    });

    this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
    this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
    this.canvas.addEventListener('mouseup', () => this.onMouseUp());
    this.canvas.addEventListener('mouseleave', () => this.onMouseUp());
    this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  showStatus(message, duration = 2000) {
    this.statusEl.textContent = message;
    if (this.statusTimeout) clearTimeout(this.statusTimeout);
    this.statusTimeout = setTimeout(() => {
      this.statusEl.textContent = '';
    }, duration);
  }

  updateCoordInputs() {
    this.coordInputs.forEach(input => {
      const pointIndex = parseInt(input.dataset.point);
      const axis = input.dataset.axis;
      if (this.points[pointIndex]) {
        input.value = Math.round(this.points[pointIndex][axis]);
      } else {
        input.value = '';
      }
    });
  }

  handleCoordInput(e) {
    const pointIndex = parseInt(e.target.dataset.point);
    const axis = e.target.dataset.axis;
    const value = parseInt(e.target.value);

    if (!isNaN(value) && this.points[pointIndex]) {
      this.points[pointIndex][axis] = value;
      this.render();
    }
  }

  handleSizeChange(e) {
    this.selectedRugSize = e.target.value;
    this.showStatus(`已选择尺寸: ${this.selectedRugSize}`);
  }

  async loadImageWithPicker() {
    try {
      // 使用 File System Access API 选择图片文件
      const [fileHandle] = await window.showOpenFilePicker({
        types: [
          {
            description: 'Images',
            accept: { 'image/*': ['.png', '.jpg', '.jpeg', '.webp'] }
          }
        ],
        multiple: false
      });

      this.imageFileHandle = fileHandle;
      this.currentSceneName = fileHandle.name;
      this.outputFileHandle = null;
      this.originalYamlContent = null;

      // 读取图片文件
      const file = await fileHandle.getFile();
      const reader = new FileReader();

      reader.onload = async () => {
        this.img = new Image();
        this.img.onload = async () => {
          // 尝试加载同名 yaml 文件
          await this.tryLoadYamlPoints();

          // 如果没有加载到点位，使用默认位置
          if (this.points.length !== 4) {
            const margin = 50;
            this.points = [
              { x: margin, y: margin },
              { x: this.img.width - margin, y: margin },
              { x: this.img.width - margin, y: this.img.height - margin },
              { x: margin, y: this.img.height - margin }
            ];
          }

          this.showStatus(`已加载 ${this.currentSceneName}`);

          // 适应视图
          this.scale = Math.min(
            (this.canvas.width - 100) / this.img.width,
            (this.canvas.height - 100) / this.img.height,
            1
          );
          this.offsetX = (this.canvas.width - this.img.width * this.scale) / 2;
          this.offsetY = (this.canvas.height - this.img.height * this.scale) / 2;

          this.infoEl.style.display = 'none';
          this.render();
          this.updateCoordInputs();
        };
        this.img.src = reader.result;
      };

      reader.readAsDataURL(file);
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('加载图片失败:', err);
        this.showStatus('加载图片失败');
      }
    }
  }

  handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    this.currentSceneName = file.name;
    this.outputFileHandle = null;
    this.originalYamlContent = null;
    this.imageFileHandle = null;
    this.directoryHandle = null;

    const reader = new FileReader();
    reader.onload = async () => {
      this.img = new Image();
      this.img.onload = async () => {
        // 尝试通过 File System Access API 获取文件句柄和目录
        await this.tryGetFileHandles();

        // 尝试加载同名 yaml 文件中的点位
        await this.tryLoadYamlPoints();

        // 如果没有加载到点位，使用默认位置
        if (this.points.length !== 4) {
          const margin = 50;
          this.points = [
            { x: margin, y: margin },
            { x: this.img.width - margin, y: margin },
            { x: this.img.width - margin, y: this.img.height - margin },
            { x: margin, y: this.img.height - margin }
          ];
        }
        this.showStatus(`已加载 ${this.currentSceneName}`);

        // 适应视图
        this.scale = Math.min(
          (this.canvas.width - 100) / this.img.width,
          (this.canvas.height - 100) / this.img.height,
          1
        );
        this.offsetX = (this.canvas.width - this.img.width * this.scale) / 2;
        this.offsetY = (this.canvas.height - this.img.height * this.scale) / 2;

        this.infoEl.style.display = 'none';
        this.render();
        this.updateCoordInputs();
      };
      this.img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  async tryGetFileHandles() {
    try {
      // 尝试获取文件句柄（需要用户授权）
      const [fileHandle] = await window.showOpenFilePicker({
        types: [
          {
            description: 'Images',
            accept: { 'image/*': ['.png', '.jpg', '.jpeg'] }
          }
        ],
        multiple: false
      });

      this.imageFileHandle = fileHandle;

      // 尝试获取父目录句柄
      // 注意：这需要用户授权目录访问
      const dirHandle = await window.showDirectoryPicker({
        mode: 'readwrite'
      });

      this.directoryHandle = dirHandle;
      this.showStatus('✓ 已获取目录访问权限');
    } catch (err) {
      // 用户取消或不支持，继续使用普通文件选择
      console.log('未获取文件句柄:', err.message);
    }
  }

  async tryLoadYamlPoints() {
    if (!this.imageFileHandle) {
      console.log('没有图片文件句柄，无法自动加载 YAML');
      return;
    }

    try {
      // 获取图片文件的基础名称（不含扩展名）
      const baseName = this.currentSceneName.replace(/\.[^.]+$/, '');
      const yamlFileName = baseName + '.yaml';

      // 请求用户选择包含图片的目录（只需要一次）
      if (!this.directoryHandle) {
        this.directoryHandle = await window.showDirectoryPicker({
          mode: 'readwrite'
        });
      }

      // 尝试从目录中获取同名 YAML 文件
      try {
        const yamlFileHandle = await this.directoryHandle.getFileHandle(yamlFileName);
        this.outputFileHandle = yamlFileHandle;

        const file = await yamlFileHandle.getFile();
        const text = await file.text();

        // 保存原始 yaml 内容
        this.originalYamlContent = text;

        // 解析 YAML（简单解析，只提取四个角点）
        const topLeft = this.parseYamlArray(text, 'top_left');
        const topRight = this.parseYamlArray(text, 'top_right');
        const bottomRight = this.parseYamlArray(text, 'bottom_right');
        const bottomLeft = this.parseYamlArray(text, 'bottom_left');

        if (topLeft && topRight && bottomRight && bottomLeft) {
          this.points = [
            { x: topLeft[0], y: topLeft[1] },
            { x: topRight[0], y: topRight[1] },
            { x: bottomRight[0], y: bottomRight[1] },
            { x: bottomLeft[0], y: bottomLeft[1] }
          ];
          this.showStatus(`✓ 已从 ${yamlFileName} 加载点位`);
        }

        // 加载 suitable_rug_size
        const sizeMatch = text.match(/suitable_rug_size:\s*([\dx]+)/);
        if (sizeMatch) {
          this.selectedRugSize = sizeMatch[1];
          document.getElementById('sizeSelect').value = this.selectedRugSize;
        }
      } catch (err) {
        // YAML 文件不存在，这是正常的
        console.log(`未找到 ${yamlFileName}，将使用默认点位`);
      }
    } catch (err) {
      // 用户取消目录选择或其他错误
      console.log('未加载 yaml 点位:', err.message);
      this.originalYamlContent = null;
      this.outputFileHandle = null;
      this.directoryHandle = null;
    }
  }

  parseYamlArray(text, key) {
    // 简单的 YAML 数组解析：匹配 "key: [x, y]" 格式
    const regex = new RegExp(`${key}:\\s*\\[\\s*(\\d+)\\s*,\\s*(\\d+)\\s*\\]`);
    const match = text.match(regex);
    if (match) {
      return [parseInt(match[1]), parseInt(match[2])];
    }
    return null;
  }

  async savePoints() {
    if (!this.img || this.points.length !== 4) {
      this.showStatus('请先加载图片并调整点位');
      return;
    }
    if (!this.currentSceneName) {
      this.showStatus('没有场景名称');
      return;
    }

    // 如果没有指定输出文件，直接保存为同名 yaml
    if (!this.outputFileHandle) {
      await this.saveAsYaml();
      return;
    }

    // 根据输出格式保存
    if (this.outputFormat === 'yaml') {
      await this.saveAsYaml();
    } else {
      await this.saveAsJsonl();
    }
  }

  async saveAsYaml() {
    const baseName = this.currentSceneName.replace(/\.[^.]+$/, '');
    const yamlFileName = baseName + '.yaml';
    const yamlContent = this.generateYamlContent();

    // 如果有目录句柄，尝试保存到同目录
    if (this.directoryHandle) {
      try {
        // 获取或创建 YAML 文件
        const yamlFileHandle = await this.directoryHandle.getFileHandle(yamlFileName, { create: true });
        this.outputFileHandle = yamlFileHandle;

        // 写入内容
        const writable = await yamlFileHandle.createWritable();
        await writable.write(yamlContent);
        await writable.close();

        this.originalYamlContent = yamlContent;
        this.showStatus(`✓ 已保存到 ${yamlFileName}`);
        return;
      } catch (err) {
        console.error('保存到目录失败:', err);
        // 如果失败，继续使用下载方式
      }
    }

    // 如果没有目录句柄或保存失败，使用下载方式
    const blob = new Blob([yamlContent], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = yamlFileName;
    a.click();
    URL.revokeObjectURL(url);
    this.showStatus(`✓ 已下载 ${yamlFileName}`);
  }

  generateYamlContent() {
    const p = this.points.map(pt => [Math.round(pt.x), Math.round(pt.y)]);

    // 如果有原始 yaml 内容，只更新角点坐标和尺寸
    if (this.originalYamlContent) {
      let content = this.originalYamlContent;

      // 更新四个角点（使用正则表达式替换）
      content = content.replace(
        /top_left:\s*\[.*?\]/,
        `top_left: [${p[0][0]}, ${p[0][1]}]`
      );
      content = content.replace(
        /top_right:\s*\[.*?\]/,
        `top_right: [${p[1][0]}, ${p[1][1]}]`
      );
      content = content.replace(
        /bottom_right:\s*\[.*?\]/,
        `bottom_right: [${p[2][0]}, ${p[2][1]}]`
      );
      content = content.replace(
        /bottom_left:\s*\[.*?\]/,
        `bottom_left: [${p[3][0]}, ${p[3][1]}]`
      );
      
      // 更新 suitable_rug_size
      content = content.replace(
        /suitable_rug_size:\s*[\dx]+/,
        `suitable_rug_size: ${this.selectedRugSize}`
      );

      return content;
    }

    // 如果没有原始内容，生成新的 YAML
    return `room_type: unknown
styles: ['modern']
images:
  original: ${this.currentSceneName}
  fg: ${this.currentSceneName.replace(/\.[^.]+$/, '_fg.png')}
top_left: [${p[0][0]}, ${p[0][1]}]
top_right: [${p[1][0]}, ${p[1][1]}]
bottom_right: [${p[2][0]}, ${p[2][1]}]
bottom_left: [${p[3][0]}, ${p[3][1]}]
suitable_rug_size: ${this.selectedRugSize}
`;
  }

  async saveAsJsonl() {
    const entry = {
      scene: this.currentSceneName,
      points: this.points.map(p => [Math.round(p.x), Math.round(p.y)])
    };
    const line = JSON.stringify(entry) + '\n';

    // 如果没有指定输出文件，使用下载方式
    if (!this.outputFileHandle) {
      const blob = new Blob([line], { type: 'application/jsonl' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${this.currentSceneName}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
      this.showStatus('✓ 已下载（建议指定导出文件以追加）');
      return;
    }

    // 追加到指定文件
    try {
      // 先读取现有内容
      let existingContent = '';
      try {
        const existingFile = await this.outputFileHandle.getFile();
        existingContent = await existingFile.text();
      } catch {
        // 文件不存在或为空，忽略
      }

      // 追加新内容并写入
      const writable = await this.outputFileHandle.createWritable();
      await writable.write(existingContent + line);
      await writable.close();
      this.showStatus(`✓ 已保存到 ${this.outputFileHandle.name}`);
    } catch (err) {
      console.error('保存失败:', err);
      this.showStatus('保存失败: ' + err.message);
    }
  }

  resetPoints() {
    if (!this.img) return;

    const margin = 50;
    this.points = [
      { x: margin, y: margin },
      { x: this.img.width - margin, y: margin },
      { x: this.img.width - margin, y: this.img.height - margin },
      { x: margin, y: this.img.height - margin }
    ];
    this.render();
    this.updateCoordInputs();
    this.showStatus('已重置');
  }

  render() {
    const ctx = this.ctx;
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    if (!this.img) {
      ctx.fillStyle = '#666';
      ctx.font = '20px Arial';
      ctx.textAlign = 'center';
      ctx.fillText('请先加载图片', this.canvas.width / 2, this.canvas.height / 2);
      return;
    }

    ctx.save();
    ctx.translate(this.offsetX, this.offsetY);
    ctx.scale(this.scale, this.scale);

    // 绘制图片
    ctx.drawImage(this.img, 0, 0);

    // 绘制连接线（黑白蚂蚁线动画）
    if (this.points.length === 4) {
      ctx.save();

      // 先绘制白色虚线
      ctx.beginPath();
      ctx.moveTo(this.points[0].x, this.points[0].y);
      for (let i = 1; i < 4; i++) {
        ctx.lineTo(this.points[i].x, this.points[i].y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 1 / this.scale;
      ctx.setLineDash([6 / this.scale, 6 / this.scale]);
      ctx.lineDashOffset = this.dashOffset / this.scale;
      ctx.stroke();

      // 再绘制黑色虚线（偏移）
      ctx.beginPath();
      ctx.moveTo(this.points[0].x, this.points[0].y);
      for (let i = 1; i < 4; i++) {
        ctx.lineTo(this.points[i].x, this.points[i].y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'black';
      ctx.lineWidth = 1 / this.scale;
      ctx.setLineDash([6 / this.scale, 6 / this.scale]);
      ctx.lineDashOffset = (this.dashOffset + 6) / this.scale;
      ctx.stroke();

      ctx.restore();
    }

    // 绘制角点和数字标签
    const labels = ['TL', 'TR', 'BR', 'BL']; // 角点标签

    this.points.forEach((point, i) => {
      // 绘制小圆点标记角点位置
      ctx.beginPath();
      ctx.arc(point.x, point.y, 4 / this.scale, 0, Math.PI * 2);
      ctx.fillStyle = 'white';
      ctx.fill();
      ctx.strokeStyle = 'black';
      ctx.lineWidth = 1 / this.scale;
      ctx.stroke();

      // 计算标签位置（在角点外侧）
      const textOffset = 20 / this.scale;
      let textOffsetX = 0, textOffsetY = 0;

      // 根据角点位置调整标签偏移
      if (i === 0) { // 左上
        textOffsetX = -textOffset;
        textOffsetY = -textOffset;
      } else if (i === 1) { // 右上
        textOffsetX = textOffset;
        textOffsetY = -textOffset;
      } else if (i === 2) { // 右下
        textOffsetX = textOffset;
        textOffsetY = textOffset;
      } else { // 左下
        textOffsetX = -textOffset;
        textOffsetY = textOffset;
      }

      // 绘制标签文字（白色文字+黑色描边）
      ctx.font = `bold ${14 / this.scale}px Arial`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      const textX = point.x + textOffsetX;
      const textY = point.y + textOffsetY;

      // 黑色描边
      ctx.strokeStyle = 'black';
      ctx.lineWidth = 3 / this.scale;
      ctx.strokeText(labels[i], textX, textY);

      // 白色填充
      ctx.fillStyle = 'white';
      ctx.fillText(labels[i], textX, textY);
    });

    ctx.restore();
  }

  getMousePos(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left - this.offsetX) / this.scale,
      y: (e.clientY - rect.top - this.offsetY) / this.scale
    };
  }

  onMouseDown(e) {
    if (!this.img) return;

    const pos = this.getMousePos(e);

    if (e.button === 2) {
      this.panning = true;
      this.panStartX = e.clientX - this.offsetX;
      this.panStartY = e.clientY - this.offsetY;
      this.canvas.style.cursor = 'grabbing';
      return;
    }

    for (let i = 0; i < this.points.length; i++) {
      const dist = Math.sqrt(
        Math.pow(pos.x - this.points[i].x, 2) +
        Math.pow(pos.y - this.points[i].y, 2)
      );
      if (dist < this.hoverRadius / this.scale) {
        this.dragging = i;
        return;
      }
    }
  }

  onMouseMove(e) {
    if (!this.img) return;

    const pos = this.getMousePos(e);

    if (this.panning) {
      this.offsetX = e.clientX - this.panStartX;
      this.offsetY = e.clientY - this.panStartY;
      this.render();
      return;
    }

    if (this.dragging >= 0) {
      this.points[this.dragging].x = pos.x;
      this.points[this.dragging].y = pos.y;
      this.render();
      this.updateCoordInputs();
      return;
    }

    let hovering = false;
    for (let i = 0; i < this.points.length; i++) {
      const dist = Math.sqrt(
        Math.pow(pos.x - this.points[i].x, 2) +
        Math.pow(pos.y - this.points[i].y, 2)
      );
      if (dist < this.hoverRadius / this.scale) {
        hovering = true;
        break;
      }
    }
    this.canvas.style.cursor = hovering ? 'pointer' : 'crosshair';
  }

  onMouseUp() {
    this.dragging = -1;
    this.panning = false;
    if (this.canvas) {
      this.canvas.style.cursor = 'crosshair';
    }
  }

  onWheel(e) {
    e.preventDefault();
    if (!this.img) return;

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoom = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.1, Math.min(5, this.scale * zoom));

    this.offsetX = mouseX - (mouseX - this.offsetX) * (newScale / this.scale);
    this.offsetY = mouseY - (mouseY - this.offsetY) * (newScale / this.scale);
    this.scale = newScale;

    this.render();
  }
}

// 初始化
new CornerMarker();
