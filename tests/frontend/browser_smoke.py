"""Optional Chromium smoke test using synthetic data and minimal HA UI hosts.

Run with Playwright installed and CHROMIUM_EXECUTABLE pointing to Chromium.
The real card JS runs in a browser; this does not simulate bpost's network API.
"""

import os
from pathlib import Path
import tempfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_EXECUTABLE', '/usr/bin/chromium'),
                                    headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 440, 'height': 850}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.set_content('''<!doctype html><html lang="fr"><style>
          body{margin:20px;font-family:Arial,sans-serif;background:#f4f6f8;
            --primary-color:#176b9a;--primary-text-color:#17212b;--secondary-text-color:#52616b;
            --card-background-color:#fff;--secondary-background-color:#edf4f8;--divider-color:#d8e1e8;
            --warning-color:#b95f00;--success-color:#237a42;--error-color:#b63030;--info-color:#176b9a}
          ha-card{display:block;background:white;border-radius:16px;overflow:hidden;border:1px solid #d8e1e8}
        </style><body></body></html>''')
        page.add_script_tag(content='''
          customElements.define('ha-card', class extends HTMLElement {
            connectedCallback(){this.setAttribute('aria-label',this.getAttribute('header') || '');}
          });
          customElements.define('ha-icon', class extends HTMLElement {
            connectedCallback(){this.textContent=this.getAttribute('icon')?.includes('truck')?'🚚':'📦';}
          });
          window.openedEntity=null;
          document.addEventListener('hass-more-info', e=>window.openedEntity=e.detail.entityId);
        ''')
        page.add_script_tag(path=str(ROOT / 'custom_components/my_bpost/frontend/my-bpost-parcels-card.js'))
        page.evaluate('''() => {
          window.demoStates={
            "sensor.my_parcel": {entity_id:"sensor.my_parcel",state:"out_for_delivery",attributes:{
              integration:"my_bpost",account_id:"demo",tracking_number:"DEMO-001",friendly_name:"Colis de démonstration",
              active:true,user_type:"RECEIVER",live_available:true,stops_remaining:7,live_eta:"14:10 – 14:35",
              live_updated_at:"2026-10-05T12:02:00Z",last_event:"Votre colis est en tournée",
              events:[{date:"05/10",time:"10:42",description:"En tournée"},{date:"05/10",time:"08:13",description:"Centre de distribution"}]}},
            "device_tracker.demo": {entity_id:"device_tracker.demo",state:"not_home",attributes:{
              integration:"my_bpost",account_id:"demo",tracking_number:"DEMO-001",location_kind:"courier",latitude:50.85,longitude:4.35}}
          };
          window.demoCard=document.createElement('my-bpost-parcels-card');
          demoCard.setConfig({}); document.body.append(demoCard);
          demoCard.hass={language:'fr',states:demoStates};
        }''')
        page.get_by_text('Livraison en direct', exact=True).wait_for()
        page.get_by_role('button', name='Voir le livreur sur la carte').click()
        assert page.evaluate('window.openedEntity') == 'device_tracker.demo'
        page.locator('summary').click()
        assert page.locator('details').evaluate('(el) => el.open')
        page.evaluate("demoCard.hass={language:'fr',states:{...demoStates, 'sensor.unrelated':{state:'on'}}}")
        assert page.locator('details').evaluate('(el) => el.open'), 'History collapsed on unrelated HA update'
        overflow = page.evaluate('''() => {
          const root=demoCard.shadowRoot;
          return [...root.querySelectorAll('.bpost-row,.bpost-live')].some(el=>el.scrollWidth>el.clientWidth+1);
        }''')
        assert not overflow, 'Card overflows on mobile'
        output = Path(os.environ.get('BPOST_ARTIFACT_DIR', tempfile.gettempdir()))
        output.mkdir(parents=True, exist_ok=True)
        page.locator('my-bpost-parcels-card').screenshot(path=str(output / 'my-bpost-live-demo.png'))
        page.evaluate('''() => {
          demoStates['sensor.my_parcel'].attributes.live_available=false;
          demoCard.hass={language:'fr',states:demoStates};
        }''')
        page.get_by_text('Suivi en direct indisponible', exact=True).wait_for()
        assert page.get_by_role('button', name='Voir le livreur sur la carte').count() == 0

        # Native editor controls use the real browser focus and change events.
        page.evaluate('''() => {
          window.editor=demoCard.constructor.getConfigElement();
          editor.setConfig({type:'custom:my-bpost-parcels-card', custom_future_option:'preserve'});
          editor.hass={language:'fr',states:demoStates,callWS:async()=>[
            {domain:'my_bpost',entry_id:'demo',title:'Compte de démonstration'},
            {domain:'my_bpost',entry_id:'empty',title:'Autre compte'}]};
          editor.addEventListener('config-changed',event=>{
            window.lastConfig=event.detail.config;
            demoCard.setConfig(lastConfig);
            editor.setConfig(lastConfig);
          });
          document.body.append(editor);
        }''')
        editor = page.locator('my-bpost-parcels-card-editor')
        editor.get_by_label('Titre', exact=True).fill('Mes livraisons')
        assert editor.get_by_label('Titre', exact=True).input_value() == 'Mes livraisons'
        # Repeated HA state updates must not replace the active input or its caret.
        editor.get_by_label('Titre', exact=True).evaluate('(el)=>{el.focus();el.setSelectionRange(3,3)}')
        page.evaluate("editor.hass={language:'fr',states:demoStates}")
        assert editor.get_by_label('Titre', exact=True).evaluate('(el)=>el===el.getRootNode().activeElement && el.selectionStart===3')
        editor.get_by_label('Compte', exact=True).select_option('empty')
        page.get_by_text('Aucun colis', exact=True).wait_for()
        editor.get_by_label('Compte', exact=True).select_option('demo')
        editor.get_by_label('Colis', exact=True).select_option('outgoing')
        page.get_by_text('Aucun colis', exact=True).wait_for()
        editor.get_by_label('Colis', exact=True).select_option('incoming')
        editor.get_by_label('Trier par', exact=True).select_option('delivery_date')
        editor.get_by_label('Mode discret', exact=True).check()
        assert page.locator('my-bpost-parcels-card').get_by_text('Colis de démonstration', exact=True).count() == 0
        assert page.locator('my-bpost-parcels-card').get_by_text('Colis 1', exact=True).count() == 1
        assert page.evaluate('lastConfig.custom_future_option') == 'preserve'
        editor.screenshot(path=str(output / 'my-bpost-editor-demo.png'))
        editor.get_by_label('Mode discret', exact=True).uncheck()
        page.locator('my-bpost-parcels-card').get_by_text('Colis de démonstration', exact=True).wait_for()

        # Today groups and duplicate controls operate on actual rendered rows.
        page.evaluate('''() => {
          demoStates['sensor.my_parcel'].attributes.parcel_group='Maison';
          demoStates['sensor.duplicate']={...demoStates['sensor.my_parcel'],entity_id:'sensor.duplicate',attributes:{
            ...demoStates['sensor.my_parcel'].attributes,tracking_source:'public',friendly_name:'Copie manuelle'}};
          for (const [id,state,name] of [['pickup','at_pickup_point','À récupérer'],['problem','problem','Livraison à vérifier']]) {
            demoStates['sensor.'+id]={entity_id:'sensor.'+id,state,attributes:{integration:'my_bpost',
              account_id:'demo',tracking_number:id,active:true,user_type:'RECEIVER',parcel_group:'Maison',friendly_name:name}};
          }
          demoCard.hass={language:'fr',config:{time_zone:'Europe/Brussels'},states:demoStates};
        }''')
        editor.get_by_label('Vue', exact=True).select_option('today')
        assert page.locator('my-bpost-parcels-card').locator('.bpost-row').count() == 3
        assert page.locator('my-bpost-parcels-card').get_by_text('Copie manuelle', exact=True).count() == 0
        editor.get_by_label('Masquer les doublons', exact=True).uncheck()
        assert page.locator('my-bpost-parcels-card').locator('.bpost-row').count() == 4
        editor.get_by_label('Masquer les doublons', exact=True).check()
        editor.get_by_label('Groupe', exact=True).fill('Bureau')
        page.get_by_text('Rien à signaler aujourd’hui', exact=True).wait_for()
        editor.get_by_label('Groupe', exact=True).fill('Maison')
        assert page.locator('my-bpost-parcels-card').locator('.bpost-row').count() == 3
        page.locator('my-bpost-parcels-card').screenshot(path=str(output / 'my-bpost-today-demo.png'))
        editor.screenshot(path=str(output / 'my-bpost-editor-demo.png'))
        assert not errors, errors
        browser.close()
        print('PASS: Chromium card/editor, map, history, privacy, focus, Today groups and duplicate controls')


if __name__ == '__main__':
    main()
