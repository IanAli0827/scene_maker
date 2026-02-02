(function() {
  'use strict';
  
  let config = {
    tool: 'circle',
    size: 50,
    feather: 0.3
  };
  
  let isDrawing = false;
  let points = [];
  let canvas = null;
  let ctx = null;
  let originalImage = null;
  let imageData = null;
  let targetImageElement = null;

  function createOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'eraser-overlay';
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      z-index: 10000;
      cursor: crosshair;
      pointer-events: none;
    `;
    document.body.appendChild(overlay);
    return overlay;
  }

  function createCanvas(img) {
    const rect = img.getBoundingClientRect();
    canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    canvas.style.cssText = `
      position: absolute;
      top: ${rect.top + window.scrollY}px;
      left: ${rect.left + window.scrollX}px;
      width: ${rect.width}px;
      height: ${rect.height}px;
      z-index: 10001;
      cursor: crosshair;
      pointer-events: auto;
    `;

    ctx = canvas.getContext('2d');

    ctx.drawImage(img, 0, 0);
    imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);

    document.body.appendChild(canvas);
    return canvas;
  }

  function getCanvasCoords(e, canvas) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY
    };
  }

  function eraseCircle(centerX, centerY, radius, feather) {
    const imageDataCopy = ctx.createImageData(imageData);
    const data = imageDataCopy.data;
    
    for (let y = 0; y < canvas.height; y++) {
      for (let x = 0; x < canvas.width; x++) {
        const dx = x - centerX;
        const dy = y - centerY;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= radius) {
          const pixelIndex = (y * canvas.width + x) * 4;

          if (distance > radius * (1 - feather)) {
            const alphaFactor = 1 - ((distance - radius * (1 - feather)) / (radius * feather));
            data[pixelIndex + 3] *= alphaFactor;
          } else {
            data[pixelIndex + 3] = 0;
          }
        }
      }
    }

    ctx.putImageData(imageDataCopy, 0, 0);
  }

  function erasePolygon(points, feather) {
    if (points.length < 3) return;

    const imageDataCopy = ctx.createImageData(imageData);
    const data = imageDataCopy.data;

    let minX = Math.min(...points.map(p => p.x));
    let maxX = Math.max(...points.map(p => p.x));
    let minY = Math.min(...points.map(p => p.y));
    let maxY = Math.max(...points.map(p => p.y));

    const featherRadius = Math.max(
      ...points.map((p, i) => {
        const next = points[(i + 1) % points.length];
        return Math.sqrt(Math.pow(next.x - p.x, 2) + Math.pow(next.y - p.y, 2)) * feather;
      })
    );

    minX -= featherRadius;
    maxX += featherRadius;
    minY -= featherRadius;
    maxY += featherRadius;

    minX = Math.max(0, minX);
    maxX = Math.min(canvas.width, maxX);
    minY = Math.max(0, minY);
    maxY = Math.min(canvas.height, maxY);

    for (let y = minY; y < maxY; y++) {
      for (let x = minX; x < maxX; x++) {
        if (pointInPolygon(x, y, points)) {
          const pixelIndex = (y * canvas.width + x) * 4;

          const distanceToEdge = distanceToPolygonEdge(x, y, points);

          if (distanceToEdge <= featherRadius) {
            const alphaFactor = distanceToEdge / featherRadius;
            data[pixelIndex + 3] *= alphaFactor;
          } else {
            data[pixelIndex + 3] = 0;
          }
        }
      }
    }

    ctx.putImageData(imageDataCopy, 0, 0);
  }

  function pointInPolygon(x, y, points) {
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

  function distanceToPolygonEdge(x, y, points) {
    let minDistance = Infinity;

    for (let i = 0; i < points.length; i++) {
      const p1 = points[i];
      const p2 = points[(i + 1) % points.length];

      const distance = distanceToLineSegment(x, y, p1.x, p1.y, p2.x, p2.y);
      minDistance = Math.min(minDistance, distance);
    }

    return minDistance;
  }

  function distanceToLineSegment(px, py, x1, y1, x2, y2) {
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

  function initTool(toolConfig) {
    config = toolConfig;

    const images = document.querySelectorAll('img[src$=".png"]');
    let targetImg = null;

    for (let img of images) {
      if (img.src.includes('fg.png') || img.src.includes('_fg.png')) {
        targetImg = img;
        break;
      }
    }

    if (!targetImg && images.length > 0) {
      targetImg = images[0];
    }

    if (!targetImg) {
      alert('未找到PNG图像！');
      return;
    }

    targetImageElement = targetImg;

    createCanvas(targetImg);

    addEventListeners();
  }

  function addEventListeners() {
    if (config.tool === 'circle') {
      canvas.addEventListener('mousedown', startCircleErase);
      canvas.addEventListener('mousemove', circleErase);
      canvas.addEventListener('mouseup', stopErase);
      canvas.addEventListener('mouseleave', stopErase);
    } else {
      canvas.addEventListener('click', addPolygonPoint);
      canvas.addEventListener('dblclick', finishPolygon);
    }

    document.addEventListener('keydown', handleKeyDown);
  }

  function removeEventListeners() {
    if (canvas) {
      canvas.removeEventListener('mousedown', startCircleErase);
      canvas.removeEventListener('mousemove', circleErase);
      canvas.removeEventListener('mouseup', stopErase);
      canvas.removeEventListener('mouseleave', stopErase);
      canvas.removeEventListener('click', addPolygonPoint);
      canvas.removeEventListener('dblclick', finishPolygon);
    }
    document.removeEventListener('keydown', handleKeyDown);
  }

  function startCircleErase(e) {
    isDrawing = true;
    const coords = getCanvasCoords(e, canvas);
    eraseCircle(coords.x, coords.y, config.size, config.feather);
  }

  function circleErase(e) {
    if (!isDrawing) return;
    const coords = getCanvasCoords(e, canvas);
    eraseCircle(coords.x, coords.y, config.size, config.feather);
  }

  function stopErase() {
    isDrawing = false;
  }

  function addPolygonPoint(e) {
    const coords = getCanvasCoords(e, canvas);
    points.push({x: coords.x, y: coords.y});

    drawPolygonFeedback();
  }

  function finishPolygon() {
    if (points.length >= 3) {
      erasePolygon(points, config.feather);
      points = [];
      clearPolygonFeedback();
    }
  }

  function drawPolygonFeedback() {
    if (points.length === 0) return;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = canvas.width;
    tempCanvas.height = canvas.height;
    const tempCtx = tempCanvas.getContext('2d');

    tempCtx.drawImage(canvas, 0, 0);

    tempCtx.strokeStyle = '#ff0000';
    tempCtx.lineWidth = 2;
    tempCtx.setLineDash([5, 5]);
    
    tempCtx.beginPath();
    tempCtx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      tempCtx.lineTo(points[i].x, points[i].y);
    }
    tempCtx.stroke();

    tempCtx.fillStyle = '#ff0000';
    points.forEach(point => {
      tempCtx.beginPath();
      tempCtx.arc(point.x, point.y, 4, 0, Math.PI * 2);
      tempCtx.fill();
    });

    const imageData = tempCtx.getImageData(0, 0, canvas.width, canvas.height);
    ctx.putImageData(imageData, 0, 0);
  }

  function clearPolygonFeedback() {
    if (!originalImage) return;
    ctx.drawImage(originalImage, 0, 0);
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      points = [];
      isDrawing = false;
      clearPolygonFeedback();
    }
  }

  function saveImage() {
    if (!canvas) return;

    canvas.toBlob(function(blob) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;

      let filename = 'erased_image.png';
      if (targetImageElement && targetImageElement.src) {
        const urlParts = targetImageElement.src.split('/');
        const originalFilename = urlParts[urlParts.length - 1];
        const nameWithoutExt = originalFilename.replace('.png', '');
        filename = nameWithoutExt + '_erased.png';
      }

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 'image/png');
  }

  function autoSave() {
    if (!canvas || !targetImageElement) return;

    canvas.toBlob(function(blob) {
      const reader = new FileReader();
      reader.onload = function() {
        const newImg = document.createElement('img');
        newImg.src = reader.result;
        newImg.alt = targetImageElement.alt;
        newImg.style.cssText = targetImageElement.style.cssText;

        targetImageElement.parentNode.replaceChild(newImg, targetImageElement);
        targetImageElement = newImg;

        resetTool();
        initTool(config);
      };
      reader.readAsDataURL(blob);
    }, 'image/png');
  }

  function resetTool() {
    removeEventListeners();

    if (canvas) {
      canvas.remove();
      canvas = null;
      ctx = null;
    }

    points = [];
    isDrawing = false;
  }

  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'init') {
      resetTool();
      initTool(request);
      sendResponse({success: true});
    } else if (request.action === 'reset') {
      resetTool();
      sendResponse({success: true});
    } else if (request.action === 'save') {
      saveImage();
      sendResponse({success: true});
    } else if (request.action === 'autoSave') {
      autoSave();
      sendResponse({success: true});
    }
  });
  
})();