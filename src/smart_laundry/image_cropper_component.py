"""Streamlit v2 图片构图预览器：拖动、缩放并返回归一化裁剪框。"""

from __future__ import annotations

import base64

import streamlit as st


IMAGE_CROPPER_HTML = r"""
<div class="cropper-root">
  <div class="crop-stage">
    <canvas id="cropCanvas" width="1160" height="1000" aria-label="图片构图预览"></canvas>
    <div class="crop-grid" aria-hidden="true"></div>
  </div>
  <div class="crop-controls">
    <label for="zoomRange">缩放</label>
    <input id="zoomRange" type="range" min="1" max="3" value="1" step="0.01">
    <span id="zoomValue">100%</span>
    <button id="resetButton" type="button">重置</button>
    <button id="confirmButton" class="primary" type="button">确认使用这个构图</button>
  </div>
  <p class="crop-hint">在预览框内拖动图片调整位置，也可以用滑块放大。保存后卡片会显示这个构图。</p>
</div>
"""


IMAGE_CROPPER_CSS = r"""
:host { color:#17263f; font-family:Arial,"Microsoft YaHei",sans-serif; }
* { box-sizing:border-box; }
.cropper-root { width:100%; padding:12px; border:1px solid #dce2ec; border-radius:18px;
  background:linear-gradient(145deg,#f6f7ff,#fff 58%,#fff4f7); }
.crop-stage { position:relative; width:100%; aspect-ratio:1.16/1; overflow:hidden;
  border:1px solid #cfd7e4; border-radius:15px; background:#eef1f6; cursor:grab;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.6); touch-action:none; }
.crop-stage.dragging { cursor:grabbing; }
#cropCanvas { display:block; width:100%; height:100%; }
.crop-grid { position:absolute; inset:0; pointer-events:none; opacity:.38;
  background:linear-gradient(to right,transparent 33.1%,rgba(255,255,255,.95) 33.2%,rgba(255,255,255,.95) 33.6%,transparent 33.7%,transparent 66.3%,rgba(255,255,255,.95) 66.4%,rgba(255,255,255,.95) 66.8%,transparent 66.9%),
    linear-gradient(to bottom,transparent 33.1%,rgba(255,255,255,.95) 33.2%,rgba(255,255,255,.95) 33.6%,transparent 33.7%,transparent 66.3%,rgba(255,255,255,.95) 66.4%,rgba(255,255,255,.95) 66.8%,transparent 66.9%); }
.crop-controls { display:grid; grid-template-columns:auto minmax(120px,1fr) 48px auto auto;
  gap:9px; align-items:center; margin-top:11px; }
.crop-controls label,.crop-controls span { color:#65748a; font-size:12px; }
.crop-controls input { width:100%; accent-color:#777bd8; }
.crop-controls button { min-height:36px; padding:7px 11px; border:1px solid #d7deea;
  border-radius:10px; color:#536177; background:#fff; font:inherit; cursor:pointer; }
.crop-controls button:hover { border-color:#8588df; color:#5b5ec8; }
.crop-controls .primary { color:#fff; border-color:#6b6ed2;
  background:linear-gradient(110deg,#686bd0,#9294e8); }
.crop-hint { margin:9px 2px 0; color:#7c899a; font-size:11px; line-height:1.55; }
@media (max-width:640px) {
  .crop-controls { grid-template-columns:auto 1fr 44px; }
  .crop-controls button { grid-column:span 3; }
}
"""


IMAGE_CROPPER_JS = r"""
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const root = parentElement.querySelector('.cropper-root');
  const stage = root.querySelector('.crop-stage');
  const canvas = root.querySelector('#cropCanvas');
  const context = canvas.getContext('2d');
  const zoomRange = root.querySelector('#zoomRange');
  const zoomValue = root.querySelector('#zoomValue');
  const image = new Image();
  let zoom = 1;
  let offsetX = 0;
  let offsetY = 0;
  let dragging = false;
  let pointerId = null;
  let lastX = 0;
  let lastY = 0;

  const baseScale = () => Math.max(canvas.width / image.naturalWidth, canvas.height / image.naturalHeight);
  const currentScale = () => baseScale() * zoom;

  function clampOffset() {
    const scale = currentScale();
    const maxX = Math.max(0, (image.naturalWidth * scale - canvas.width) / 2);
    const maxY = Math.max(0, (image.naturalHeight * scale - canvas.height) / 2);
    offsetX = Math.max(-maxX, Math.min(maxX, offsetX));
    offsetY = Math.max(-maxY, Math.min(maxY, offsetY));
  }

  function draw() {
    if (!image.complete || !image.naturalWidth) return;
    clampOffset();
    const scale = currentScale();
    const width = image.naturalWidth * scale;
    const height = image.naturalHeight * scale;
    const x = (canvas.width - width) / 2 + offsetX;
    const y = (canvas.height - height) / 2 + offsetY;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, x, y, width, height);
  }

  function resetView() {
    zoom = 1;
    offsetX = 0;
    offsetY = 0;
    zoomRange.value = '1';
    zoomValue.textContent = '100%';
    draw();
  }

  stage.addEventListener('pointerdown', (event) => {
    dragging = true;
    pointerId = event.pointerId;
    lastX = event.clientX;
    lastY = event.clientY;
    stage.classList.add('dragging');
    stage.setPointerCapture(pointerId);
  });
  stage.addEventListener('pointermove', (event) => {
    if (!dragging || event.pointerId !== pointerId) return;
    const rect = canvas.getBoundingClientRect();
    offsetX += (event.clientX - lastX) * canvas.width / rect.width;
    offsetY += (event.clientY - lastY) * canvas.height / rect.height;
    lastX = event.clientX;
    lastY = event.clientY;
    draw();
  });
  const stopDragging = (event) => {
    if (event.pointerId !== pointerId) return;
    dragging = false;
    pointerId = null;
    stage.classList.remove('dragging');
  };
  stage.addEventListener('pointerup', stopDragging);
  stage.addEventListener('pointercancel', stopDragging);

  zoomRange.addEventListener('input', () => {
    zoom = Number(zoomRange.value);
    zoomValue.textContent = `${Math.round(zoom * 100)}%`;
    draw();
  });
  root.querySelector('#resetButton').addEventListener('click', resetView);
  root.querySelector('#confirmButton').addEventListener('click', (event) => {
    const scale = currentScale();
    const renderedWidth = image.naturalWidth * scale;
    const renderedHeight = image.naturalHeight * scale;
    const renderedX = (canvas.width - renderedWidth) / 2 + offsetX;
    const renderedY = (canvas.height - renderedHeight) / 2 + offsetY;
    const crop = {
      left: Math.max(0, -renderedX / scale / image.naturalWidth),
      top: Math.max(0, -renderedY / scale / image.naturalHeight),
      width: Math.min(1, canvas.width / scale / image.naturalWidth),
      height: Math.min(1, canvas.height / scale / image.naturalHeight)
    };
    event.currentTarget.textContent = '已确认';
    setTriggerValue('crop_confirmed', JSON.stringify(crop));
  });

  image.onload = resetView;
  image.src = data.image_url;
}
"""


image_cropper = st.components.v2.component(
    "smart_laundry_image_cropper",
    html=IMAGE_CROPPER_HTML,
    css=IMAGE_CROPPER_CSS,
    js=IMAGE_CROPPER_JS,
)


def render_image_cropper(
    *, content: bytes, mime_type: str, key: str, on_confirm
):
    """挂载图片构图组件；确认后把归一化裁剪框交回 Python。"""

    encoded = base64.b64encode(content).decode("ascii")
    image_url = f"data:{mime_type};base64,{encoded}"
    return image_cropper(
        key=key,
        data={"image_url": image_url},
        height=650,
        on_crop_confirmed_change=on_confirm,
    )
