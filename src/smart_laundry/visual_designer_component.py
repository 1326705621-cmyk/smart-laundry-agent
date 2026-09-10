"""Streamlit v2 内嵌可视化设计器，不依赖 Node.js 或额外前端服务。"""

from __future__ import annotations

import streamlit as st


VISUAL_DESIGNER_HTML = r"""
<div class="designer-root">
  <div class="designer-toolbar">
    <div>
      <strong>颜色与效果设计</strong>
      <span>固定整齐布局 · 点击区域即时预览样式</span>
    </div>
    <div class="toolbar-actions">
      <button id="resetButton" type="button">恢复默认效果</button>
      <button id="saveButton" class="primary" type="button">保存并应用</button>
    </div>
  </div>
  <div class="designer-workspace">
    <div class="canvas-scroller"><div id="designCanvas" class="design-canvas"></div></div>
    <aside id="inspector" class="inspector"></aside>
  </div>
</div>
"""


VISUAL_DESIGNER_CSS = r"""
:host { color:#17263f; font-family:Arial,"Microsoft YaHei",sans-serif; }
* { box-sizing:border-box; }
button, input, select { font:inherit; }
.designer-root { border:1px solid #dfe4ed; border-radius:20px; overflow:hidden; background:#f6f8fc; }
.designer-toolbar { min-height:64px; display:flex; align-items:center; justify-content:space-between; gap:16px;
  padding:10px 14px; background:rgba(255,255,255,.94); border-bottom:1px solid #e2e6ee; }
.designer-toolbar strong { display:block; font-size:16px; }
.designer-toolbar span { color:#7d899a; font-size:11px; }
.toolbar-actions { display:flex; align-items:center; gap:7px; flex-wrap:wrap; justify-content:flex-end; }
.toolbar-actions button { border:1px solid #d9dfeb; background:#fff; color:#526077; border-radius:9px;
  padding:7px 10px; cursor:pointer; }
.toolbar-actions button:hover { border-color:#8588df; color:#5b5ec8; }
.toolbar-actions .primary { color:#fff; border-color:#696cd2; background:linear-gradient(110deg,#696cd2,#9294e9); }
.grid-toggle { color:#68768a; font-size:12px; display:flex; gap:5px; align-items:center; }
.designer-workspace { display:grid; grid-template-columns:minmax(0,1fr) 310px; min-height:680px; }
.canvas-scroller { padding:18px; overflow:auto; background:#edf1f7; }
.design-canvas { min-width:620px; display:grid; grid-template-columns:repeat(3,minmax(170px,1fr)); gap:12px;
  align-content:start; padding:14px; border:1px solid #d5dbe7; border-radius:16px;
  box-shadow:0 14px 35px rgba(55,66,96,.12); background:#fff; }
.design-element { position:relative; min-height:92px; display:flex; align-items:center; justify-content:center;
  overflow:hidden; cursor:pointer; user-select:none; transition:box-shadow .12s,border-color .12s; }
.design-element.selected { outline:2px solid #676bd6; outline-offset:2px; z-index:999 !important; }
.element-badge { position:absolute; left:7px; top:5px; padding:2px 6px; border-radius:999px;
  background:rgba(23,38,63,.72); color:#fff; font-size:10px; font-weight:600; pointer-events:none; }
.node-content { width:100%; padding:26px 12px 12px; pointer-events:none; line-height:1.25; text-align:center; font-size:14px; font-weight:700; }
.node-subtext { display:block; margin-top:7px; font-size:10px; opacity:.62; font-weight:400; }
.inspector { padding:14px; overflow:auto; max-height:760px; background:#fff; border-left:1px solid #e1e5ed; }
.inspector h3 { margin:0 0 3px; font-size:16px; }
.inspector .hint { margin:0 0 12px; color:#8793a4; font-size:11px; }
.section-title { margin:14px 0 7px; padding-bottom:5px; border-bottom:1px solid #edf0f4;
  color:#59677c; font-size:12px; font-weight:700; }
.field-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.field { min-width:0; }
.field.full { grid-column:1/-1; }
.field label { display:block; margin:0 0 4px; color:#6d798c; font-size:10px; }
.field input,.field select { width:100%; height:32px; border:1px solid #dce2ec; border-radius:8px;
  padding:4px 7px; background:#fafbfc; color:#293950; }
.field input[type="color"] { padding:2px; }
.range-row { display:grid; grid-template-columns:1fr 48px; gap:6px; align-items:center; }
.range-row input[type="range"] { padding:0; }
.safety-note { margin-top:12px; padding:9px; border-radius:9px; background:#f5f7fb;
  color:#69768b; font-size:11px; line-height:1.55; }
.empty-inspector { margin-top:80px; color:#8995a5; text-align:center; font-size:13px; line-height:1.7; }
@media (max-width:950px) {
  .designer-toolbar { align-items:flex-start; flex-direction:column; }
  .designer-workspace { grid-template-columns:1fr; }
  .inspector { border-left:0; border-top:1px solid #e1e5ed; max-height:none; }
}
"""


VISUAL_DESIGNER_JS = r"""
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const root = parentElement.querySelector('.designer-root');
  const canvas = root.querySelector('#designCanvas');
  const inspector = root.querySelector('#inspector');
  const clone = (value) => JSON.parse(JSON.stringify(value));
  let design = clone(data.design);
  const defaultDesign = clone(data.default_design);
  let selectedId = design.elements[0]?.id || null;
  const syncDesign = () => {};

  const byId = (id) => design.elements.find((item) => item.id === id);
  const rgba = (hex, opacity) => {
    const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
    return `rgba(${r},${g},${b},${opacity/100})`;
  };
  const background = (item) => item.fill_type === 'gradient'
    ? `linear-gradient(${item.gradient_angle}deg,${rgba(item.color1,item.opacity)},${rgba(item.color2,item.opacity)})`
    : rgba(item.color1,item.opacity);
  const nodeMarkup = (item) => `<div class="node-content">${item.label}<span class="node-subtext">点击修改颜色与效果</span></div>`;

  function applyNodeStyle(node, item) {
    Object.assign(node.style, {
      background:background(item), border:`${item.border_width}px solid ${item.border_color}`,
      borderRadius:`${item.radius}px`, boxShadow:`0 ${Math.max(2,item.shadow/2)}px ${item.shadow*2}px rgba(39,48,78,${item.shadow/160})`,
      backdropFilter:item.fill_type === 'glass' ? `blur(${item.blur}px)` : 'none',
      color:item.text_color
    });
  }

  function renderCanvas() {
    canvas.innerHTML='';
    design.elements.forEach((item,index)=>{
      const node=document.createElement('div');
      node.className='design-element'+(item.id===selectedId?' selected':'');
      node.dataset.id=item.id; applyNodeStyle(node,item);
      node.innerHTML=`<span class="element-badge">${item.label}</span>${nodeMarkup(item)}`;
      applyNodeStyle(node,item);
      node.addEventListener('click',(event)=>{ event.stopPropagation(); selectedId=item.id; renderAll(); });
      canvas.appendChild(node);
    });
  }

  const field = (label,name,value,type='number',extra='') => `<div class="field"><label>${label}</label><input data-field="${name}" type="${type}" value="${value}" ${extra}></div>`;
  const rangeField = (label,name,value,min,max) => `<div class="field full"><label>${label}</label><div class="range-row"><input data-field="${name}" type="range" min="${min}" max="${max}" value="${value}"><input data-field="${name}" type="number" min="${min}" max="${max}" value="${value}"></div></div>`;
  const selectField = (label,name,value,options) => `<div class="field full"><label>${label}</label><select data-field="${name}">${options.map(([v,t])=>`<option value="${v}" ${v===value?'selected':''}>${t}</option>`).join('')}</select></div>`;

  function renderInspector() {
    const item=byId(selectedId);
    if(!item){ inspector.innerHTML='<div class="empty-inspector">点击画布中的模块<br>即可编辑详细样式</div>'; return; }
    inspector.innerHTML=`
      <h3>${item.label}</h3><p class="hint">只调整颜色与效果，网页位置由整齐布局自动管理</p>
      <div class="section-title">方框与背景</div><div class="field-grid">
        ${selectField('背景效果','fill_type',item.fill_type,[['solid','纯色'],['gradient','渐变'],['glass','毛玻璃']])}
        ${field('颜色一','color1',item.color1,'color')}${field('颜色二','color2',item.color2,'color')}
        ${rangeField('透明度','opacity',item.opacity,0,100)}${rangeField('渐变方向','gradient_angle',item.gradient_angle,0,360)}
        ${rangeField('毛玻璃模糊','blur',item.blur,0,40)}${field('边框颜色','border_color',item.border_color,'color')}
        ${rangeField('边框粗细','border_width',item.border_width,0,8)}${rangeField('圆角','radius',item.radius,0,48)}
        ${rangeField('阴影','shadow',item.shadow,0,40)}
      </div>
      <div class="section-title">文字</div><div class="field-grid">
        ${field('文字颜色','text_color',item.text_color,'color')}
      </div>
      <div class="safety-note">这里统一管理页面大背景、顶部区域、三个标签、筛选框、四类物品卡片、状态小框、按钮以及两个功能内容区。布局与字号固定，不会再被配色设置打乱。</div>`;
    inspector.querySelectorAll('[data-field]').forEach((input)=>{
      const handler=()=>{
        const name=input.dataset.field; const numeric=['gradient_angle','opacity','blur','border_width','radius','shadow'].includes(name);
        if(numeric){ const value=Number(input.value); inspector.querySelectorAll(`[data-field="${name}"]`).forEach(other=>{if(other!==input)other.value=String(value)}); item[name]=value; }
        else item[name]=input.value;
        syncDesign(); renderCanvas();
      };
      input.addEventListener(input.tagName==='SELECT'?'change':'input',handler);
      input.addEventListener('focus',()=>{ input.dataset.before=JSON.stringify(design); });
    });
  }

  function renderAll(){ renderCanvas(); renderInspector(); }
  canvas.addEventListener('pointerdown',(e)=>{ if(e.target===canvas){selectedId=null;renderAll();} });
  root.querySelector('#resetButton').addEventListener('click',()=>{design=clone(defaultDesign);selectedId=design.elements[0].id;syncDesign();renderAll();});
  root.querySelector('#saveButton').addEventListener('click',(event)=>{
    event.currentTarget.textContent='正在保存…';
    setTriggerValue('save_requested',JSON.stringify(design));
  });
  renderAll();
}
"""


visual_designer = st.components.v2.component(
    "smart_laundry_visual_designer",
    html=VISUAL_DESIGNER_HTML,
    css=VISUAL_DESIGNER_CSS,
    js=VISUAL_DESIGNER_JS,
)


def render_visual_designer(
    *, design: dict, default_design: dict, key: str, on_save
):
    """挂载颜色与效果设计器；只有点击保存才触发 Python 重跑。"""

    return visual_designer(
        key=key,
        data={"design": design, "default_design": default_design},
        height=840,
        on_save_requested_change=on_save,
    )
