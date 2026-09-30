const { chromium } = require('playwright');
const fs = require('node:fs');
const mdi = require('@mdi/js');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless:true});
  const page = await browser.newPage({viewport:{width:1440,height:1400}});
  await page.setContent(`<style>body{font-family:Roboto,Arial,sans-serif;margin:0;background:#252a32;--primary-color:#92c7c1;--primary-text-color:#e5e8ed;--secondary-text-color:#a3adb9;--card-background-color:#343b49;--secondary-background-color:#292f3a;--divider-color:#475060;--text-primary-color:#162423}ha-card{display:block}ha-icon{display:inline-block;width:20px;height:20px}</style>`);
  await page.evaluate(paths => {
    customElements.define('ha-icon', class extends HTMLElement {
      static get observedAttributes(){return ['icon'];}
      connectedCallback(){this.draw();}
      attributeChangedCallback(){this.draw();}
      draw(){const key='mdi'+(this.getAttribute('icon')||'').replace('mdi:','').split('-').map(s=>s.charAt(0).toUpperCase()+s.slice(1)).join('');this.innerHTML=`<svg viewBox="0 0 24 24" style="width:var(--mdc-icon-size,20px);height:var(--mdc-icon-size,20px);fill:currentColor"><path d="${paths[key]||''}"/></svg>`;}
    });
  },mdi);
  for (const file of ['gwm-vehicle-remote-card.js','gwm-vehicle-remote-horizontal-card.js','gwm-vehicle-remote-modern-card.js']) {
    await page.addScriptTag({content:fs.readFileSync(`custom_components/gwm_ru/frontend/${file}`,'utf8')});
  }
  const tags = ['gwm-vehicle-remote-card','gwm-vehicle-remote-horizontal-card','gwm-vehicle-remote-modern-card','gwm-vehicle-remote-modern-horizontal-card'];
  for (const tag of tags) for (const width of [280,390,720,1300]) {
    const result = await page.evaluate(({tag,width}) => {
      document.querySelectorAll('body > [data-test]').forEach(el => el.remove());
      const card = document.createElement(tag); card.dataset.test='true'; card.style.width=`${width}px`;
      document.body.append(card);
      card.setConfig({type:`custom:${tag}`, title:'Haval H3', controls:['engine','lock','climate','trunk','refresh','seat_heating','steering','sunroof','rear_defrost'], info:['tires','range']});
      card._resolvedKey='|'; card._entryId='test-entry';
      const values={engine:'off',unlocked:'off',tbox:'on',doors:'off',windows:'off',trunk:'off',fuel:'37',mileage:'10904',range:'302',signal:'4',seatDriver:'0',seatPassenger:'0',tireFlP:'2.5',tireFrP:'2.5',tireRlP:'2.4',tireRrP:'2.4'};
      const states={};
      for(const [key,state] of Object.entries(values)){card._entities[key]=`sensor.${key}`;states[`sensor.${key}`]={state,attributes:{}};}
      card.hass={states,themes:{darkMode:true},callService:async()=>{},callWS:async()=>[]};
      const root=card.shadowRoot;
      const tiles=[...root.querySelectorAll('.status-tile')];
      const rows=new Map();
      for(const tile of tiles){const rect=tile.getBoundingClientRect();const row=rows.get(rect.top)||{top:rect.top,bottom:0};row.bottom=Math.max(row.bottom,rect.bottom);rows.set(rect.top,row);}
      const sorted=[...rows.values()].sort((a,b)=>a.top-b.top);
      const gaps=sorted.slice(1).map((row,index)=>row.top-sorted[index].bottom);
      const box=root.querySelector('ha-card').getBoundingClientRect();
      const overflowing=[...root.querySelectorAll('.remote-action,.status-tile,.info-tile,.hero')].filter(el=>el.getBoundingClientRect().right>box.right+.5 || el.getBoundingClientRect().left<box.left-.5).length;
      return {gap:Math.min(...gaps),tiles:tiles.length,overflowing,cardWidth:box.width,actions:root.querySelectorAll('[data-action]').length,registered:window.customCards.filter(c=>c.type===tag).length};
    },{tag,width});
    assert.ok(result.gap>=5, `${tag} ${width}: telemetry rows touch (${result.gap}px)`);
    assert.equal(result.overflowing,0,`${tag} ${width}: horizontal overflow`);
    assert.equal(result.registered,1);
    assert.equal(result.actions,9);
    assert.equal(result.tiles,10);
    await page.evaluate(() => {
      const card=document.querySelector('[data-test]');
      const button=card.shadowRoot.querySelector('[data-action="lock"]');button.focus();card._render();
      if(card.shadowRoot.activeElement!==button)throw Error('Keyboard focus lost on telemetry update');
      if(card.shadowRoot.querySelectorAll('style').length>2)throw Error('Duplicate styles after render');
    });
    console.log(tag,width,result);
    if(width===1300 || width===390) await page.screenshot({path:`/tmp/${tag}-${width}.png`,fullPage:true});
  }
  for(const tag of tags) await page.evaluate(tag => {
    const card=document.createElement(tag);document.body.append(card);
    card.setConfig({statuses:['climate','fuel','mileage','climate'],info:['fuel','climate','mileage','gsm','range']});
    card._resolvedKey='|';card.hass={states:{},themes:{}};
    const root=card.shadowRoot;
    if(root.querySelectorAll('.status-tile').length!==5)throw Error('Legacy fields were not deduplicated');
    if(root.querySelector('[data-status="gsm"]')===null)throw Error('Selected GSM is hidden');
    if(root.querySelector('.info-grid'))throw Error('Split information grid still rendered');
    if(root.querySelector('h2,.vehicle-name'))throw Error('Empty title rendered');
    if(root.textContent.includes('GWM / Remote Studio'))throw Error('Studio branding still rendered');
    card.setConfig({title:'   ',telemetry:['gps','gps'],statuses:['gsm'],info:['gsm']});card._resolvedKey='|';card._render();
    if(root.querySelector('[data-status="gsm"]')||root.textContent.includes('GSM'))throw Error('Unselected GSM still visible');
    if(root.querySelectorAll('.status-tile').length!==1)throw Error('Unified selection did not override legacy lists');
    if(root.querySelector('h2,.vehicle-name'))throw Error('Whitespace title rendered');
    const editor=card.constructor.getConfigElement();editor.setConfig({statuses:['climate','fuel'],info:['climate','fuel','gsm']});
    const checks=editor.shadowRoot.querySelectorAll('[data-list="telemetry"]');
    if(!checks.length||editor.shadowRoot.querySelector('[data-list="statuses"],[data-list="info"]'))throw Error('Editor not unified');
    if([...checks].filter(el=>el.checked).length!==3)throw Error('Editor lost legacy selections');
    card.remove();
  },tag);
  await page.evaluate(async () => {
    const card=document.querySelector('[data-test]');let calls=0;
    window.confirm=()=>false;card._hass.callService=async()=>{calls++;};
    await card._handleAction('engine');if(calls)throw Error('Cancelled confirmation sent a command');
    card._hass.callService=async(domain,service,data)=>{if(domain!=='gwm_ru'||service!=='engine_start'||data.operation_time!==15)throw Error('Unexpected command');calls++;};
    window.confirm=()=>true;await card._handleAction('engine');if(calls!==1)throw Error('Confirmed command not sent exactly once');
  });
  // Missing telemetry must keep commands disabled; custom titles are escaped.
  await page.evaluate(() => {
    const card=document.querySelector('[data-test]');
    card.setConfig({title:'<img src=x onerror=alert(1)>',controls:['engine','lock'],info:[],statuses:[]});
    card._resolvedKey='|';card._entities={};card.hass={states:{},themes:{}};
    if(card.shadowRoot.querySelector('[data-action="engine"]'))throw Error('Engine enabled without telemetry');
    if(card.shadowRoot.querySelector('h2 img'))throw Error('Title not escaped');
  });
  await browser.close();
})();
