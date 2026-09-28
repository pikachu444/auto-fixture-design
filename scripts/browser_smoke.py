"""Actual Chromium acceptance test: edit input, generate CAD, download and reject."""
from pathlib import Path
import io,json,socket,subprocess,sys,time,urllib.request,zipfile
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'artifacts/browser';out.mkdir(parents=True,exist_ok=True)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
process=subprocess.Popen([sys.executable,'-m','fixturelab','serve','--port',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    address=f'http://127.0.0.1:{port}'
    for _ in range(60):
        try:
            with urllib.request.urlopen(address+'/api/examples',timeout=1) as response:examples=json.load(response)
            break
        except OSError:time.sleep(.25)
    else:raise RuntimeError('Server did not become ready')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(address);page.locator('#examples option').first.wait_for(state='attached')
        film=next(i for i,e in enumerate(examples) if e['id']=='film_alignment')
        page.locator('#examples').select_option(str(film))
        page.locator('input[name="specimen.width"]').fill('20')
        page.locator('#run').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('REVIEW_REQUIRED')",timeout=180000)
        frame=page.frame_locator('#report');frame.locator('h1').wait_for()
        assert frame.locator('table').count()>=1
        page.screenshot(path=str(out/'application-success.png'),full_page=True)
        with page.expect_download() as download:page.locator('#download').click()
        downloaded=download.value;downloaded.save_as(str(out/'ui-generated-fixture.zip'))
        with zipfile.ZipFile(out/'ui-generated-fixture.zip') as z:
            assert z.testzip() is None
            assert 'alignment_tray.stl' in z.namelist()
            result=json.loads(z.read('result.json'))
            assert result['input']['specimen']['width']==20
            assert abs(result['bom'][0]['bounds_mm'][1]-32.5)<1e-6
        failed=next(i for i,e in enumerate(examples) if e['id']=='film_travel_reject')
        page.locator('#examples').select_option(str(failed));page.locator('#run').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('REJECTED')",timeout=180000)
        page.frame_locator('#report').locator('.alert').wait_for()
        page.screenshot(path=str(out/'application-rejected.png'),full_page=True)
        assert not errors,errors
        browser.close()
    (out/'result.json').write_text(json.dumps({'status':'PASS','engine':'Chromium via Playwright','checks':['input edited to 20 mm','real CAD generation','report iframe','ZIP download and CAD files','modified geometry dimension verified','travel rejection shown','no JavaScript errors']},indent=2))
finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait()
