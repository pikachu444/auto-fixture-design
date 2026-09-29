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
        page.frame_locator('#report').locator('.alert').filter(has_text='REJECTED').wait_for()
        page.screenshot(path=str(out/'application-rejected.png'),full_page=True)
        with page.expect_download() as rejected_download:page.locator('#download').click()
        rejected_download.value.save_as(str(out/'ui-rejected-report.zip'))
        with zipfile.ZipFile(out/'ui-rejected-report.zip') as z:
            assert json.loads(z.read('result.json'))['decision']=='REJECTED'
            assert not any(n.endswith(('.stl','.step','.3mf')) for n in z.namelist())
        page.locator('#show-models').click()
        page.locator('#models option').first.wait_for(state='attached')
        page.locator('#models').select_option(label='3점 굽힘 롤러 지지대')
        page.locator('input[name="cad.support_width_mm"]').fill('38')
        page.locator('#cad-run').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('REVIEW_REQUIRED')",timeout=180000)
        page.frame_locator('#report').locator('h1').filter(has_text='롤러 지지대').wait_for()
        page.screenshot(path=str(out/'cad-source-parametric.png'),full_page=True)
        with page.expect_download() as cad_download:page.locator('#download').click()
        cad_download.value.save_as(str(out/'cad-source-modified.zip'))
        with zipfile.ZipFile(out/'cad-source-modified.zip') as z:
            assert {'cad_source.py','roller_support.stl','assembly.step'}<=set(z.namelist())
            result=json.loads(z.read('result.json'))
            assert result['parameters']['support_width_mm']==38
            assert result['bom'][0]['bounds_mm'][0]==38
        page.locator('input[name="cad.bolt_pitch_x_mm"]').fill('30')
        page.locator('#cad-run').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('REJECTED')",timeout=180000)
        with page.expect_download() as blocked_download:page.locator('#download').click()
        blocked_download.value.save_as(str(out/'cad-source-rejected.zip'))
        with zipfile.ZipFile(out/'cad-source-rejected.zip') as z:
            assert json.loads(z.read('result.json'))['decision']=='REJECTED'
            assert not any(n.endswith(('.stl','.step','.3mf')) for n in z.namelist())
        page.locator('#show-native').click()
        page.locator('#native-new').click()
        page.locator('#native-target option').first.wait_for(state='attached',timeout=180000)
        canvas=page.locator('#native-surface');canvas.wait_for(state='visible',timeout=180000)
        bounds=canvas.bounding_box()
        for x,y in ((.5,.5),(.4,.45),(.6,.55),(.5,.65)):
            canvas.click(position={'x':bounds['width']*x,'y':bounds['height']*y})
            if '선택한 솔리드 면' in page.locator('#native-face-help').inner_text():break
        else:raise AssertionError('Clicking the FreeCAD solid did not select a face')
        assert page.locator('#native-target option').count()>0
        page.screenshot(path=str(out/'native-clicked-face.png'),full_page=True)
        page.locator('#native-show-all').click()
        page.locator('#native-target').select_option('SupportBlock|property|Length')
        page.locator('#native-name').fill('browser_width')
        page.locator('#native-min').fill('28')
        page.locator('#native-max').fill('60')
        page.locator('#native-definition button').click()
        page.locator('input[name="native.browser_width"]').wait_for(timeout=180000)
        page.locator('input[name="native.browser_width"]').fill('38')
        page.locator('#native-values button').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('REVIEW_REQUIRED')",timeout=180000)
        page.frame_locator('#report').locator('h1').filter(has_text='FreeCAD').wait_for()
        page.screenshot(path=str(out/'native-defined-parameter.png'),full_page=True)
        with page.expect_download() as native_download:page.locator('#download').click()
        native_download.value.save_as(str(out/'native-modified.zip'))
        with zipfile.ZipFile(out/'native-modified.zip') as z:
            assert {'editable.FCStd','native.step','native_printed_part.stl','native_printed_part.3mf'}<=set(z.namelist())
            value=json.loads(z.read('result.json'))
            assert value['bounds_mm'][0]==38 and value['parameters']['browser_width']==38
        page.locator('#native-target').select_option('BoltBore1|property|Radius')
        page.locator('#native-name').fill('browser_bore_radius')
        page.locator('#native-min').fill('2')
        page.locator('#native-max').fill('20')
        page.locator('#native-definition button').click()
        page.locator('input[name="native.browser_bore_radius"]').wait_for(timeout=180000)
        page.locator('input[name="native.browser_bore_radius"]').fill('5')
        page.locator('#native-values button').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('REJECTED')",timeout=180000)
        with page.expect_download() as blocked:page.locator('#download').click()
        blocked.value.save_as(str(out/'native-rejected.zip'))
        with zipfile.ZipFile(out/'native-rejected.zip') as z:
            assert json.loads(z.read('result.json'))['decision']=='REJECTED'
            assert not any(n.endswith(('.stl','.step','.3mf')) for n in z.namelist())
        assert not errors,errors
        browser.close()
    (out/'result.json').write_text(json.dumps({'status':'PASS','engine':'Chromium via Playwright','checks':['input edited to 20 mm','real CAD generation','report iframe','ZIP download and CAD files','modified geometry dimension verified','travel rejection shown','rejected ZIP contains report but no CAD','CAD source parameters loaded into form','CAD source width change rebuilt STEP and STL','CAD source relation rejected invalid geometry','clicked actual FreeCAD BREP face in 3D viewer','face-based CAD dimension suggestions shown','FreeCAD feature dimension selected and named in browser','editable FCStd exported with modified STEP/STL/3MF','native hole edge land rejection without CAD','no JavaScript errors']},indent=2))
finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait()
