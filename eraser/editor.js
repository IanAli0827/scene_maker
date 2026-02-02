// Eraser Tool - 独立页面版本
class EraserTool {
  constructor() {
    this.canvas = document.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.img = null;
    this.currentTool = 'circle';
    this.brushSize = 50;
    this.featherAmount = 0.3;
    
    this.isDrawing = false;
    this.polygonPoints = [];
    this.history = [];
    this.maxHistory = 20;
    
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.panning = false;
    this.panStartX = 0;
    this.panStartY = 0;
    
    this.currentFileName = null;
    this.currentFileHandle = null;
    this.statusTimeout = null;
    this.mouseX = null; // 鼠标X坐标
    this.mouseY = null; // 鼠标Y坐标

    this.statusEl = document.getElementById('status');
    this.infoEl = document.getElementById('info');

    this.init();
  }

  async init() {
    this.bindEvents();
    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());
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
    const undoBtn = document.getElementById('undoBtn');
    const fileInput = document.getElementById('fileInput');
    const circleToolBtn = document.getElementById('circleToolBtn');
    const polygonToolBtn = document.getElementById('polygonToolBtn');
    const sizeSlider = document.getElementById('sizeSlider');
    const featherSlider = document.getElementById('featherSlider');
    const sizeValue = document.getElementById('sizeValue');
    const featherValue = document.getElementById('featherValue');

    loadImgBtn.addEventListener('click', () => fileInput.click());
    saveBtn.addEventListener('click', () => this.saveImage());
    undoBtn.addEventListener('click', () => this.undo());
    fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

    circleToolBtn.addEventListener('click', () => this.setTool('circle'));
    polygonToolBtn.addEventListener('click', () => this.setTool('polygon'));

    sizeSlider.addEventListener('input', (e) => {
      this.brushSize = parseInt(e.target.value);
      sizeValue.textContent = e.target.value;
    });

    featherSlider.addEventListener('input', (e) => {
      this.featherAmount = parseInt(e.target.value) / 100;
      featherValue.textContent = e.target.value + '%';
    });

    this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
    this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
    this.canvas.addEventListener('mouseup', () => this.onMouseUp());
    this.canvas.addEventListener('mouseleave', () => this.onMouseUp());
    this.canvas.addEventListener('wheel', (e) => this.onWheel(e));
    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    this.canvas.addEventListener('dblclick', (e) => this.onDoubleClick(e));

    document.addEventListener('keydown', (e) => this.handleKeyDown(e));
  }

  setTool(tool) {
    this.currentTool = tool;
    this.polygonPoints = [];
    
    const circleBtn = document.getElementById('circleToolBtn');
    const polygonBtn = document.getElementById('polygonToolBtn');
    
    circleBtn.classList.toggle('active', tool === 'circle');
    polygonBtn.classList.toggle('active', tool === 'polygon');
    
    this.showStatus(`已切换到${tool === 'circle' ? '圆形' : '多边形'}工具`);
    this.render();
  }

  showStatus(message, duration = 2000) {
    this.statusEl.textContent = message;
    if (this.statusTimeout) clearTimeout(this.statusTimeout);
    this.statusTimeout = setTimeout(() => {
      this.statusEl.textContent = '';
    }, duration);
  }

  async handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    this.currentFileName = file.name;
    
    // 尝试获取文件句柄用于保存
    try {
      const [fileHandle] = await window.showOpenFilePicker({
        types: [{ description: 'Images', accept: { 'image/*': ['.png', '.jpg', '.jpeg'] } }],
        multiple: false
      });
      this.currentFileHandle = fileHandle;
    } catch (err) {
      this.currentFileHandle = null;
    }

    const reader = new FileReader();
    reader.onload = () => {
      this.img = new Image();
      this.img.onload = () => {
        this.history = [];
        this.polygonPoints = [];
        
        this.showStatus(`已加载 ${this.currentFileName}`);
        
        // 适应视图
        this.scale = Math.min(
          (this.canvas.width - 100) / this.img.width,
          (this.canvas.height - 100) / this.img.height,
          1
        );
        this.offsetX = (this.canvas.width - this.img.width * this.scale) / 2;
        this.offsetY = (this.canvas.height - this.img.height * this.scale) / 2;

        this.infoEl.style.display = 'none';
        this.saveHistory();
        this.render();
      };
      this.img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  saveHistory() {
    if (!this.img) return;
    
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = this.img.width;
    tempCanvas.height = this.img.height;
    const tempCtx = tempCanvas.getContext('2d');
    tempCtx.drawImage(this.img, 0, 0);
    
    this.history.push(tempCanvas.toDataURL());
    if (this.history.length > this.maxHistory) {
      this.history.shift();
    }
  }

  undo() {
    if (this.history.length <= 1) {
      this.showStatus('没有更多历史记录');
      return;
    }
    
    this.history.pop();
    const prevState = this.history[this.history.length - 1];
    
    const newImg = new Image();
    newImg.onload = () => {
      this.img = newImg;
      this.render();
      this.showStatus('已撤销');
    };
    newImg.src = prevState;
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

    if (e.button === 2) {
      this.panning = true;
      this.panStartX = e.clientX - this.offsetX;
      this.panStartY = e.clientY - this.offsetY;
      this.canvas.style.cursor = 'grabbing';
      return;
    }

    if (this.currentTool === 'circle') {
      this.isDrawing = true;
      const pos = this.getMousePos(e);
      this.eraseCircle(pos.x, pos.y);
    }
  }

  onMouseMove(e) {
    if (!this.img) return;

    const pos = this.getMousePos(e);
    this.mouseX = pos.x;
    this.mouseY = pos.y;

    if (this.panning) {
      this.offsetX = e.clientX - this.panStartX;
      this.offsetY = e.clientY - this.panStartY;
      this.render();
      return;
    }

    if (this.isDrawing && this.currentTool === 'circle') {
      this.eraseCircle(pos.x, pos.y);
    }

    // 重新渲染以显示鼠标预览
    this.render();
  }

  onMouseUp() {
    if (this.isDrawing) {
      this.isDrawing = false;
      this.saveHistory();
    }
    this.panning = false;
    this.canvas.style.cursor = 'crosshair';
  }

  onDoubleClick(e) {
    if (!this.img || this.currentTool !== 'polygon') return;
    
    e.preventDefault();
    if (this.polygonPoints.length >= 3) {
      this.erasePolygon();
      this.polygonPoints = [];
      this.saveHistory();
    }
  }

  handleKeyDown(e) {
    if (e.key === 'Escape') {
      this.polygonPoints = [];
      this.render();
      this.showStatus('已取消多边形');
    }
  }

  eraseCircle(centerX, centerY) {
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = this.img.width;
    tempCanvas.height = this.img.height;
    const tempCtx = tempCanvas.getContext('2d');

    tempCtx.drawImage(this.img, 0, 0);
    const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
    const data = imageData.data;

    const radius = this.brushSize / this.scale;
    const softness = this.featherAmount; // 0-1, 柔边程度

    // 计算影响范围
    const minX = Math.max(0, Math.floor(centerX - radius));
    const maxX = Math.min(tempCanvas.width, Math.ceil(centerX + radius));
    const minY = Math.max(0, Math.floor(centerY - radius));
    const maxY = Math.min(tempCanvas.height, Math.ceil(centerY + radius));

    // 遍历圆形区域内的像素
    for (let y = minY; y < maxY; y++) {
      for (let x = minX; x < maxX; x++) {
        const dx = x - centerX;
        const dy = y - centerY;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= radius) {
          const pixelIndex = (y * tempCanvas.width + x) * 4;

          // 计算柔边效果：从中心到边缘的平滑过渡
          let alpha = 1.0;

          if (softness > 0) {
            // 柔边区域从 (1-softness)*radius 到 radius
            const softStart = radius * (1 - softness);
            if (distance > softStart) {
              // 使用平滑的余弦插值创建柔边效果
              const t = (distance - softStart) / (radius - softStart);
              alpha = Math.cos(t * Math.PI / 2); // 从1到0的平滑过渡
            }
          }

          // 擦除：减少 alpha 通道
          data[pixelIndex + 3] *= (1 - alpha);
        }
      }
    }

    tempCtx.putImageData(imageData, 0, 0);

    const newImg = new Image();
    newImg.onload = () => {
      this.img = newImg;
      this.render();
    };
    newImg.src = tempCanvas.toDataURL();
  }

  erasePolygon() {
    if (this.polygonPoints.length < 3) return;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = this.img.width;
    tempCanvas.height = this.img.height;
    const tempCtx = tempCanvas.getContext('2d');

    tempCtx.drawImage(this.img, 0, 0);
    const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
    const data = imageData.data;

    const points = this.polygonPoints;
    const softness = this.featherAmount; // 0-1, 边缘柔和度
    const softDistance = 20 * softness; // 柔边距离（像素）

    // 计算边界框
    const minX = Math.max(0, Math.floor(Math.min(...points.map(p => p.x)) - softDistance - 5));
    const maxX = Math.min(tempCanvas.width, Math.ceil(Math.max(...points.map(p => p.x)) + softDistance + 5));
    const minY = Math.max(0, Math.floor(Math.min(...points.map(p => p.y)) - softDistance - 5));
    const maxY = Math.min(tempCanvas.height, Math.ceil(Math.max(...points.map(p => p.y)) + softDistance + 5));

    // 遍历边界框内的像素
    for (let y = minY; y < maxY; y++) {
      for (let x = minX; x < maxX; x++) {
        const pixelIndex = (y * tempCanvas.width + x) * 4;

        // 检查点是否在多边形内
        const isInside = this.pointInPolygon(x, y, points);

        if (isInside) {
          // 在多边形内部，计算到边缘的距离
          let alpha = 1.0;

          if (softness > 0) {
            // 计算到多边形边缘的最短距离
            const distToEdge = this.distanceToPolygonEdge(x, y, points);

            if (distToEdge < softDistance) {
              // 使用平滑的余弦插值创建柔边效果
              const t = distToEdge / softDistance;
              alpha = 1 - Math.cos(t * Math.PI / 2); // 从0到1的平滑过渡
            }
          }

          // 擦除：减少 alpha 通道
          data[pixelIndex + 3] *= (1 - alpha);
        }
      }
    }

    tempCtx.putImageData(imageData, 0, 0);

    const newImg = new Image();
    newImg.onload = () => {
      this.img = newImg;
      this.render();
    };
    newImg.src = tempCanvas.toDataURL();
  }

  pointInPolygon(x, y, points) {
    let inside = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const xi = points[i].x, yi = points[i].y;
      const xj = points[j].x, yj = points[j].y;
      
      const intersect = ((yi > y) !== (yj > y)) && 
        (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  distanceToPolygonEdge(x, y, points) {
    let minDistance = Infinity;
    
    for (let i = 0; i < points.length; i++) {
      const p1 = points[i];
      const p2 = points[(i + 1) % points.length];
      
      const distance = this.distanceToLineSegment(x, y, p1.x, p1.y, p2.x, p2.y);
      minDistance = Math.min(minDistance, distance);
    }
    
    return minDistance;
  }

  distanceToLineSegment(px, py, x1, y1, x2, y2) {
    const A = px - x1;
    const B = py - y1;
    const C = x2 - x1;
    const D = y2 - y1;
    
    const dot = A * C + B * D;
    const lenSq = C * C + D * D;
    
    let param = -1;
    if (lenSq !== 0) param = dot / lenSq;
    
    let xx, yy;
    
    if (param < 0) {
      xx = x1;
      yy = y1;
    } else if (param > 1) {
      xx = x2;
      yy = y2;
    } else {
      xx = x1 + param * C;
      yy = y1 + param * D;
    }
    
    const dx = px - xx;
    const dy = py - yy;
    return Math.sqrt(dx * dx + dy * dy);
  }

  async saveImage() {
    if (!this.img) {
      this.showStatus('请先加载图片');
      return;
    }

    try {
      const tempCanvas = document.createElement('canvas');
      tempCanvas.width = this.img.width;
      tempCanvas.height = this.img.height;
      const tempCtx = tempCanvas.getContext('2d');
      tempCtx.drawImage(this.img, 0, 0);

      const blob = await new Promise(resolve => tempCanvas.toBlob(resolve, 'image/png'));
      
      // 生成默认文件名（使用加载的文件路径）
      let suggestedName = this.currentFileName || 'erased.png';
      
      const fileHandle = await window.showSaveFilePicker({
        suggestedName: suggestedName,
        types: [{
          description: 'PNG Images',
          accept: { 'image/png': ['.png'] }
        }]
      });

      const writable = await fileHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      
      this.showStatus(`✓ 已保存到 ${fileHandle.name}`);
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('保存失败:', err);
        this.showStatus('保存失败: ' + err.message);
      }
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

    // 绘制多边形点
    if (this.currentTool === 'polygon' && this.polygonPoints.length > 0) {
      ctx.strokeStyle = '#9B8CBA';
      ctx.lineWidth = 2 / this.scale;
      ctx.setLineDash([5 / this.scale, 5 / this.scale]);

      ctx.beginPath();
      ctx.moveTo(this.polygonPoints[0].x, this.polygonPoints[0].y);
      for (let i = 1; i < this.polygonPoints.length; i++) {
        ctx.lineTo(this.polygonPoints[i].x, this.polygonPoints[i].y);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = '#9B8CBA';
      this.polygonPoints.forEach(point => {
        ctx.beginPath();
        ctx.arc(point.x, point.y, 5 / this.scale, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // 绘制鼠标预览圆圈（圆形工具）
    if (this.currentTool === 'circle' && this.mouseX !== null && this.mouseY !== null && !this.panning) {
      const radius = this.brushSize / this.scale;

      // 外圈（白色）
      ctx.beginPath();
      ctx.arc(this.mouseX, this.mouseY, radius, 0, Math.PI * 2);
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 2 / this.scale;
      ctx.stroke();

      // 内圈（黑色）
      ctx.beginPath();
      ctx.arc(this.mouseX, this.mouseY, radius, 0, Math.PI * 2);
      ctx.strokeStyle = 'black';
      ctx.lineWidth = 1 / this.scale;
      ctx.stroke();

      // 如果有柔边，显示柔边范围
      if (this.featherAmount > 0) {
        const softStart = radius * (1 - this.featherAmount);
        ctx.beginPath();
        ctx.arc(this.mouseX, this.mouseY, softStart, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 1 / this.scale;
        ctx.setLineDash([3 / this.scale, 3 / this.scale]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    ctx.restore();

    // 绘制右下角工具预览
    this.drawToolPreview();
  }

  drawToolPreview() {
    const ctx = this.ctx;
    const previewSize = 80;
    const margin = 20;
    const x = this.canvas.width - previewSize - margin;
    const y = this.canvas.height - previewSize - margin;

    // 背景
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(x, y, previewSize, previewSize);
    ctx.strokeStyle = '#444';
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, previewSize, previewSize);

    // 绘制工具预览
    const centerX = x + previewSize / 2;
    const centerY = y + previewSize / 2;
    const previewRadius = Math.min(30, this.brushSize * 0.5);

    if (this.currentTool === 'circle') {
      // 圆形工具预览
      ctx.beginPath();
      ctx.arc(centerX, centerY, previewRadius, 0, Math.PI * 2);
      ctx.strokeStyle = 'white';
      ctx.lineWidth = 2;
      ctx.stroke();

      // 柔边指示
      if (this.featherAmount > 0) {
        const softStart = previewRadius * (1 - this.featherAmount);
        ctx.beginPath();
        ctx.arc(centerX, centerY, softStart, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // 显示大小
      ctx.fillStyle = 'white';
      ctx.font = '10px Arial';
      ctx.textAlign = 'center';
      ctx.fillText(`${this.brushSize}px`, centerX, y + previewSize - 5);
    } else {
      // 多边形工具预览
      ctx.fillStyle = 'white';
      ctx.font = '12px Arial';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('多边形', centerX, centerY);
    }
  }
}

// 初始化
const eraserTool = new EraserTool();

// 添加点击事件（用于多边形工具）
const canvas = document.getElementById('canvas');
canvas.addEventListener('click', function(e) {
  if (eraserTool.currentTool === 'polygon' && eraserTool.img && !eraserTool.panning) {
    const pos = eraserTool.getMousePos(e);
    eraserTool.polygonPoints.push({ x: pos.x, y: pos.y });
    eraserTool.render();
  }
});