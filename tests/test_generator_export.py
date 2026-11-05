"""Generator export checks. Requires Playwright/Chromium and CDN access at startup.

Dependencies are fetched once, then replayed from memory for isolated browser tests.
"""
import base64
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as error:
    raise unittest.SkipTest("Install Playwright and its Chromium browser.") from error


GENERATOR = (Path(__file__).resolve().parents[1] / "index.html").as_uri()


class GeneratorExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        cls.resources = {}
        context = cls.browser.new_context()
        page = context.new_page()

        def cache(response):
            if response.url.startswith("https://"):
                headers = {key: value for key, value in response.headers.items()
                           if key in ["content-type", "location", "access-control-allow-origin"]}
                cls.resources[response.url] = dict(status=response.status, headers=headers,
                                                   body=b"" if 300 <= response.status < 400 else response.body())

        page.on("response", cache)
        try:
            page.goto(GENERATOR, wait_until="networkidle", timeout=45000)
            if not page.evaluate("!!window.domtoimage && !!window.tailwind"):
                raise unittest.SkipTest("Generator tests need access to the app's CDNs.")
            page.evaluate("document.fonts.ready")
            page.evaluate("domtoimage.impl.fontFaces.resolveAll()")
        except Exception:
            context.close()
            cls.browser.close()
            cls.playwright.stop()
            raise
        else:
            context.close()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1080}, reduced_motion="reduce")
        self.context.route("https://**/*", lambda route: route.fulfill(**self.resources[route.request.url])
                           if route.request.url in self.resources else route.abort())
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors = []
        self.downloads = []
        self.dialogs = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("download", lambda download: self.downloads.append(download))
        self.page.on("dialog", lambda dialog: (self.dialogs.append(dialog.message), dialog.accept()))
        self.page.goto(GENERATOR, wait_until="networkidle")
        self.page.wait_for_function("projectReady")
        self.page.evaluate("""() => {
            applyProjectSnapshot(validateBackup(exampleProjectSnapshot('PNG checks')));
            shareAppearance=false;characters.forEach(character=>character.avatar=null);
            const chat=activeConversation();conversations=[chat];
            messages=[];chat.messages=messages;storyBlocks=defaultStoryBlocks(conversations);
            settings.headerName='Lily';settings.scrollOverlap=50;previewMode='conversation';scriptDirty=false;
            exportOptions={scale:1,keepMessagesTogether:true};updateSettingsUI();
        }""")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def set_messages(self, count=24):
        self.page.evaluate("""count => {
            const chat=activeConversation();
            messages=Array.from({length:count},(_,i)=>({id:'png-'+i,type:i===8?'timestamp':'text',
                sender:i===8?null:chat.participantIds[i%2],content:i===8?'Later that evening':
                'Message '+i+'. '+('Consistent wrapping and alignment. ').repeat(i%3+1)}));
            chat.messages=messages;storyBlocks=defaultStoryBlocks(conversations);updateSettingsUI();
        }""", count)

    def test_screenshot_pages_align_top_leave_bottom_visible_and_end_at_chat_bottom(self):
        result = self.page.evaluate("""() => {
            const offsets=planCapturePages(100,0,Array.from({length:9},(_,i)=>({top:16+i*60,bottom:60+i*60})),true,456).map(p=>p.offset);
            const timestamps=planCapturePages(500,0,[{top:16,bottom:100},{top:400,bottom:450},{top:450,bottom:514}],true,30);
            for(const overlap of [0,50,200,609])for(const align of [false,true]) {
                let y=32;const rows=Array.from({length:100},(_,i)=>{const top=y;const height=i===15?1200:i%6===0?64:38.75+(i%4)*18.75;y+=height+(i%6===5?0:4);return {top,bottom:top+height};});
                const maxScroll=rows.at(-1).bottom+24-610,pages=planCapturePages(610,overlap,rows,align,maxScroll);
                if(pages.at(-1).offset!==maxScroll)throw Error('Final page is not bottom aligned');
                for(const page of pages)if(page.clipTop||page.clipBottom)throw Error('Artificial edge clipping');
                for(let i=1;i<pages.length;i++) {
                    if(pages[i].offset<=pages[i-1].offset)throw Error('No progress');
                    if(align&&i<pages.length-1&&rows.some(row=>row.top<pages[i].offset-.01&&row.bottom>pages[i].offset+.01&&row.bottom-row.top<=610))throw Error('Cropped top bubble');
                }
                for(const row of rows) {
                    const slices=pages.map(p=>[Math.max(row.top,p.offset),Math.min(row.bottom,p.offset+610)]).filter(([a,b])=>b>a);
                    let covered=row.top;
                    for(const [a,b] of slices){if(a>covered+.01)throw Error('Missing pixels');covered=Math.max(covered,b);}
                    if(covered<row.bottom-.01)throw Error('Missing end');
                }
            }
            let invalid=false;try{planCapturePages(610,610,[],true);}catch(_){invalid=true;}
            return {offsets,timestampEnd:500-timestamps[0].clipBottom,timestampStart:timestamps[1].offset,invalid};
        }""")
        self.assertEqual(result, {"offsets": [0, 76, 136, 196, 256, 316, 376, 456], "timestampEnd": 500,
                                  "timestampStart": 30, "invalid": True})

    def test_title_uses_available_space_across_widths_frames_and_avatars(self):
        result = self.page.evaluate("""async() => {
            await document.fonts.ready;const chat=activeConversation();let checked=0;
            for(const width of [300,375,600])for(const frame of [false,true])for(const avatar of [false,true])for(const name of ['Lily','Emma','Sarah and Max']) {
                const item={...chat,settings:{...chat.settings,screenWidth:width,showFrame:frame,showAvatar:avatar,headerName:name}};
                const phone=createChatPhone(item,[],characters,phoneContainer,true);document.body.appendChild(phone);
                const title=phonePart(phone,'preview-name'),header=phonePart(phone,'phone-header'),range=document.createRange();range.selectNodeContents(title);
                if(range.getBoundingClientRect().width>title.clientWidth)throw Error('Short name clipped: '+name);
                if(Math.abs(title.getBoundingClientRect().width-(header.clientWidth-112))>1)throw Error('Wrong title width');
                if(title.getBoundingClientRect().left<header.getBoundingClientRect().left+55)throw Error('Icon overlap');
                phone.remove();checked++;
            }
            return checked;
        }""")
        self.assertEqual(result, 36)

    def test_late_pages_keep_measured_alignment_and_only_mount_visible_rows(self):
        self.set_messages(500)
        result = self.page.evaluate("""async() => {
            await document.fonts.ready;const phone=createChatPhone(activeConversation(),messages,characters,phoneContainer,true);
            phone.dataset.capture='true';Object.assign(phone.style,{position:'fixed',left:'0',top:'0'});document.body.appendChild(phone);
            const viewport=phonePart(phone,'chat-container'),content=phonePart(phone,'chat-content');viewport.style.overflow='hidden';
            const layout=measureCaptureLayout(viewport,content),height=viewport.clientHeight;
            const pages=planCapturePages(height,50,layout.rows.filter(row=>row.node.dataset.messageId),true,viewport.scrollHeight-height);let maxRows=0;
            for(const page of pages) {
                renderCapturePage(viewport,content,layout,page);maxRows=Math.max(maxRows,content.children.length);
                if(viewport.clientHeight!==height)throw Error('Viewport shifted');
                for(const row of layout.rows)if(row.node.parentNode===content) {
                    const rect=row.node.getBoundingClientRect(),top=rect.top-viewport.getBoundingClientRect().top;
                    if(Math.abs(top-(row.top-page.offset))>.03||Math.abs(rect.height-row.height)>.03)throw Error('Row drift');
                }
            }
            phone.remove();return {pages:pages.length,maxRows};
        }""")
        self.assertGreater(result["pages"], 50)
        self.assertLess(result["maxRows"], 15)

    def test_actual_zip_has_png_pages_embedded_fonts_and_restores_preview(self):
        self.set_messages(18)
        self.page.evaluate("""() => {
            window.originalFontResolver=domtoimage.impl.fontFaces.resolveAll;window.fontCalls=0;
            window.countedFonts=function(){fontCalls++;return originalFontResolver();};domtoimage.impl.fontFaces.resolveAll=countedFonts;
            window.exportFrames=[];const original=domtoimage.toBlob;
            domtoimage.toBlob=async(node,options)=>{
                const fontCss=await domtoimage.impl.fontFaces.resolveAll(),viewport=phonePart(node,'chat-container');
                const title=phonePart(node,'preview-name'),rect=viewport.getBoundingClientRect(),root=node.getBoundingClientRect();
                const frame={title:title.textContent,width:title.clientWidth,rows:phonePart(node,'chat-content').children.length,
                    font:fontCss.includes('Inter')&&fontCss.includes('data:application'),height:viewport.clientHeight,
                    clip:viewport.style.clipPath,firstTop:node.querySelector('[data-message-id]').getBoundingClientRect().top-rect.top};
                exportFrames.push(frame);
                const blob=await original(node,options),bitmap=await createImageBitmap(blob),canvas=document.createElement('canvas');
                canvas.width=bitmap.width;canvas.height=bitmap.height;const context=canvas.getContext('2d');context.drawImage(bitmap,0,0);bitmap.close();
                const bubbles=Array.from(node.querySelectorAll('.bubble-sent,.bubble-received'),bubble=>bubble.getBoundingClientRect());
                const top=bubbles.find(bubble=>Math.abs(bubble.top-rect.top)<.1),bottom=bubbles.find(bubble=>bubble.top<rect.bottom-8&&bubble.bottom>rect.bottom+1);
                const painted=(bubble,y)=>{
                    const x=(bubble.left+bubble.right)/2-root.left,data=context.getImageData(Math.floor(x)-2,Math.floor(y-root.top),4,4).data;
                    for(let i=0;i<data.length;i+=4)if(data[i+3]>200&&(data[i]<245||data[i+1]<245||data[i+2]<245))return true;
                    return false;
                };
                frame.topPainted=top?painted(top,rect.top+1):null;frame.bottomPainted=bottom?painted(bottom,rect.bottom-5):null;
                return blob;
            };
            chatContainer.scrollTop=333;window.beforeExportScroll=chatContainer.scrollTop;
        }""")
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate("saveSeries()")
        with tempfile.TemporaryDirectory(prefix="chat-export-") as directory:
            archive = Path(directory) / "batch.zip"
            result.value.save_as(archive)
            with zipfile.ZipFile(archive) as batch:
                names = batch.namelist()
                self.assertGreater(len(names), 2)
                self.assertEqual(names, sorted(names))
                self.assertIsNone(batch.testzip())
                for name in names:
                    data = batch.read(name)
                    self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                    self.assertEqual(struct.unpack(">II", data[16:24]), (375, 812))
                (Path(tempfile.gettempdir()) / "chat-generator-fixed-first.png").write_bytes(batch.read(names[0]))
                (Path(tempfile.gettempdir()) / "chat-generator-aligned-middle.png").write_bytes(batch.read(names[1]))
                (Path(tempfile.gettempdir()) / "chat-generator-fixed-last.png").write_bytes(batch.read(names[-1]))
        frames = self.page.evaluate("exportFrames")
        self.assertTrue(all(frame["font"] and frame["title"] == "Lily" and frame["width"] > 200 for frame in frames))
        self.assertLess(max(frame["rows"] for frame in frames), 15)
        self.assertEqual(len({frame["height"] for frame in frames}), 1)
        self.assertTrue(all(frame["clip"] == "" for frame in frames))
        self.assertAlmostEqual(frames[0]["firstTop"], 32, delta=.05)
        self.assertTrue(all(abs(frame["firstTop"]) < .05 for frame in frames[1:-1]))
        self.assertTrue(any(frame["topPainted"] is True for frame in frames))
        self.assertTrue(any(frame["bottomPainted"] is True for frame in frames))
        self.assertFalse(any(frame["topPainted"] is False or frame["bottomPainted"] is False for frame in frames))
        self.assertEqual(self.page.evaluate("fontCalls"), 1)
        self.assertTrue(self.page.evaluate("chatContainer.scrollTop===beforeExportScroll&&domtoimage.impl.fontFaces.resolveAll===countedFonts"))
        self.assertFalse(self.page.evaluate("captureInProgress"))
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)

    def test_story_order_and_cancel_do_not_change_active_chat(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=[{id:'a',type:'text',sender:first.ownerId,content:'First'},{id:'c',type:'text',sender:first.ownerId,content:'Third'}];
            second.messages=[{id:'b',type:'text',sender:second.ownerId,content:'Second'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:['a']},{id:'two',conversationId:second.id,messageIds:['b']},
                {id:'three',conversationId:first.id,messageIds:['c']}];previewMode='story';renderChat();
            window.originalActive=activeConversationId;window.storyFrames=[];
            domtoimage.toBlob=async node=>{storyFrames.push(Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId));
                return new Blob(['test'],{type:'image/png'});};
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveSeries()")
        self.assertEqual(self.page.evaluate("storyFrames"), [["a"], ["b"], ["a", "c"]])
        self.assertTrue(self.page.evaluate("activeConversationId===originalActive&&previewMode==='story'"))
        self.page.evaluate("""() => {
            window.fontResolverBeforeCancel=domtoimage.impl.fontFaces.resolveAll;
            window.waitingForImage=false;domtoimage.toBlob=()=>new Promise(resolve=>{waitingForImage=true;window.releaseImage=resolve;});
            window.capturePromise=saveSeries();
        }""")
        self.page.wait_for_function("waitingForImage")
        self.page.evaluate("cancelCapture()")
        self.page.wait_for_function("!captureInProgress")
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)
        self.assertTrue(self.page.evaluate("domtoimage.impl.fontFaces.resolveAll===fontResolverBeforeCancel&&activeConversationId===originalActive"))
        self.assertEqual(self.page.locator("#export-status").text_content(), "Export cancelled.")
        self.page.evaluate("releaseImage(new Blob(['late'],{type:'image/png'}))")
        self.assertEqual(len(self.downloads), 1)

    def test_font_failure_can_retry_single_png_with_image_frame_dark_mode_and_scale(self):
        self.set_messages(5)
        self.page.evaluate("""() => {
            window.goodFonts=domtoimage.impl.fontFaces.resolveAll;
            window.badFonts=()=>Promise.resolve('@font-face{font-family:Inter;src:url("data:application/font-woff;base64,")}');
            domtoimage.impl.fontFaces.resolveAll=badFonts;
        }""")
        self.page.evaluate("saveImage()")
        self.assertEqual(self.page.locator("#export-status").text_content(), "Export failed.")
        self.assertTrue(any("export font could not be loaded" in dialog for dialog in self.dialogs))
        self.assertTrue(self.page.evaluate("!captureInProgress&&domtoimage.impl.fontFaces.resolveAll===badFonts"))
        self.assertEqual(len(self.downloads), 0)
        self.page.evaluate("""() => {
            domtoimage.impl.fontFaces.resolveAll=goodFonts;
            const source='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120"><rect width="240" height="120" fill="#4499cc"/></svg>');
            messages.splice(2,0,{id:'photo',type:'image',sender:activeConversation().ownerId,content:source,altText:'A blue rectangle'});
            Object.assign(settings,{headerName:'Emma',screenWidth:300,showFrame:true,darkMode:true,cropImages:true});
            exportOptions={scale:3,keepMessagesTogether:true};getPreviewDraft(activeConversation()).text='Private unsent text';
            storyBlocks=defaultStoryBlocks(conversations);updateSettingsUI();chatContainer.scrollTop=60;
            const original=domtoimage.toBlob;window.singleFrame=null;
            domtoimage.toBlob=async(node,options)=>{
                singleFrame={name:phonePart(node,'preview-name').textContent,dark:node.classList.contains('dark-theme'),
                    frame:node.classList.contains('phone-framed'),image:!!node.querySelector('img.chat-image, [data-message-id="photo"] img'),
                    clean:!node.querySelector('textarea,.preview-message-tools')&&!node.textContent.includes('Private unsent text')};
                return original(node,options);
            };
        }""")
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate("saveImage()")
            self.assertEqual(self.page.locator("#export-status").text_content(), "PNG exported.", str(self.dialogs))
        with tempfile.TemporaryDirectory(prefix="chat-single-") as directory:
            target = Path(directory) / "single.png"
            result.value.save_as(target)
            self.assertEqual(struct.unpack(">II", target.read_bytes()[16:24]), (900, 2436))
            (Path(tempfile.gettempdir()) / "chat-generator-fixed-framed.png").write_bytes(target.read_bytes())
        self.assertEqual(self.page.evaluate("singleFrame"), {"name": "Emma", "dark": True, "frame": True, "image": True, "clean": True})
        self.assertTrue(self.page.evaluate("domtoimage.impl.fontFaces.resolveAll===goodFonts&&!captureInProgress"))

    def test_continuous_png_matches_story_preview_and_contains_every_message(self):
        self.set_messages(18)
        self.page.evaluate("""async() => {
            setDirectEditing(false);setPreviewMode('story');await document.fonts.ready;
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            const phone=document.querySelector('#story-preview .phone-container'),rect=phone.getBoundingClientRect();
            window.expectedContinuous={width:rect.width,height:rect.height,rows:Array.from(phone.querySelectorAll('[data-message-id]'),row=>({
                id:row.dataset.messageId,top:row.getBoundingClientRect().top-rect.top,bottom:row.getBoundingClientRect().bottom-rect.top}))};
            setPreviewMode('conversation');setDirectEditing(true);
            getPreviewDraft(activeConversation()).text='An unsent preview draft';renderChat();chatContainer.scrollTop=333;
            window.continuousBefore={chat:activeConversationId,scroll:chatContainer.scrollTop,messages:JSON.stringify(messages)};
            window.continuousFrame=null;const original=domtoimage.toBlob;
            domtoimage.toBlob=async(node,options)=>{
                const bounds=node.getBoundingClientRect();
                continuousFrame={width:bounds.width,height:bounds.height,outputWidth:options.width,outputHeight:options.height,
                    headers:node.querySelectorAll('[data-phone-part="phone-header"]').length,
                    footers:node.querySelectorAll('[data-phone-part="phone-input-area"]').length,
                    clean:!node.querySelector('textarea,[data-preview-editor],.preview-message-tools')&&!node.textContent.includes('An unsent preview draft'),
                    rows:Array.from(node.querySelectorAll('[data-message-id]'),row=>({id:row.dataset.messageId,
                        top:row.getBoundingClientRect().top-bounds.top,bottom:row.getBoundingClientRect().bottom-bounds.top}))};
                return original(node,options);
            };
            openPreviewTools();document.getElementById('preview-export').open=true;
        }""")
        self.assertIn("PNG", self.page.locator("#btn-export-full").text_content())
        with self.page.expect_download(timeout=60000) as result:
            self.page.locator("#btn-export-full").click()
        expected = self.page.evaluate("expectedContinuous")
        frame = self.page.evaluate("continuousFrame")
        self.assertGreater(expected["height"], 812)
        self.assertEqual(frame["headers"], 1)
        self.assertEqual(frame["footers"], 1)
        self.assertTrue(frame["clean"])
        self.assertEqual([row["id"] for row in frame["rows"]], [row["id"] for row in expected["rows"]])
        for actual, reference in zip(frame["rows"], expected["rows"]):
            self.assertAlmostEqual(actual["top"], reference["top"], delta=.05)
            self.assertAlmostEqual(actual["bottom"], reference["bottom"], delta=.05)
        self.assertAlmostEqual(frame["width"], expected["width"], delta=1)
        self.assertAlmostEqual(frame["height"], expected["height"], delta=1)
        with tempfile.TemporaryDirectory(prefix="chat-continuous-") as directory:
            image = Path(directory) / "continuous.png"
            result.value.save_as(image)
            data = image.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]), (frame["outputWidth"], frame["outputHeight"]))
            (Path(tempfile.gettempdir()) / "chat-generator-continuous.png").write_bytes(data)
        self.assertTrue(result.value.suggested_filename.endswith(".png"))
        self.assertTrue(self.page.evaluate("!captureInProgress&&activeConversationId===continuousBefore.chat&&chatContainer.scrollTop===continuousBefore.scroll&&JSON.stringify(messages)===continuousBefore.messages"))
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)

    def test_continuous_story_zip_uses_one_image_per_displayed_block_in_order(self):
        self.page.evaluate("""async() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=Array.from({length:22},(_,i)=>({id:'a-'+i,type:'text',sender:first.ownerId,
                content:'Story message '+i+'. '+('A longer conversation retains all its messages. ').repeat(3)}));
            second.messages=Array.from({length:3},(_,i)=>({id:'b-'+i,type:'text',sender:second.ownerId,content:'Second chat '+i}));
            Object.assign(second.settings,{headerName:'Max',screenWidth:300,darkMode:true,showFrame:true});
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'first-visit',conversationId:first.id,messageIds:first.messages.slice(0,20).map(m=>m.id)},
                {id:'second-chat',conversationId:second.id,messageIds:second.messages.map(m=>m.id)},
                {id:'return-visit',conversationId:first.id,messageIds:first.messages.slice(20).map(m=>m.id)}];
            setDirectEditing(false);setPreviewMode('story');renderChat();await document.fonts.ready;
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            window.expectedStoryFull=Array.from(document.querySelectorAll('#story-preview .phone-container'),phone=>({
                width:phone.getBoundingClientRect().width,height:phone.getBoundingClientRect().height,
                ids:Array.from(phone.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId)}));
            window.storyFullFrames=[];window.storyFullActive=activeConversationId;exportOptions.scale=2;
            domtoimage.toBlob=async(node,options)=>{
                storyFullFrames.push({width:node.getBoundingClientRect().width,height:node.getBoundingClientRect().height,
                    outputWidth:options.width,outputHeight:options.height,
                    dark:node.classList.contains('dark-theme'),frame:node.classList.contains('phone-framed'),
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    headers:node.querySelectorAll('[data-phone-part="phone-header"]').length});
                return new Blob(['test'],{type:'image/png'});
            };
            openPreviewTools();document.getElementById('preview-export').open=true;
        }""")
        self.assertIn("ZIP", self.page.locator("#btn-export-full").text_content())
        with self.page.expect_download() as result:
            self.page.locator("#btn-export-full").click()
        expected = self.page.evaluate("expectedStoryFull")
        frames = self.page.evaluate("storyFullFrames")
        self.assertEqual(len(frames), 3)
        self.assertEqual([frame["ids"] for frame in frames], [block["ids"] for block in expected])
        self.assertGreater(frames[0]["height"], 812)
        self.assertLess(frames[2]["height"], frames[0]["height"])
        self.assertEqual(frames[2]["ids"][-2:], ["a-20", "a-21"])
        self.assertGreater(len(frames[2]["ids"]), 2)
        self.assertLessEqual(frames[2]["height"], 812)
        self.assertEqual([(frame["dark"], frame["frame"]) for frame in frames], [(False, False), (True, True), (False, False)])
        for frame, block in zip(frames, expected):
            self.assertEqual(frame["headers"], 1)
            self.assertAlmostEqual(frame["width"], block["width"], delta=1)
            self.assertAlmostEqual(frame["height"], block["height"], delta=1)
            self.assertAlmostEqual(frame["outputWidth"], block["width"] * 2, delta=2)
            self.assertAlmostEqual(frame["outputHeight"], block["height"] * 2, delta=2)
        with tempfile.TemporaryDirectory(prefix="chat-story-full-") as directory:
            target = Path(directory) / "full.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), 3)
                self.assertEqual(names, sorted(names))
                self.assertTrue(all(name.endswith(".png") for name in names))
                self.assertIsNone(archive.testzip())
        self.assertTrue(self.page.evaluate("activeConversationId===storyFullActive&&previewMode==='story'&&!captureInProgress"))

    def test_cancelling_continuous_export_restores_all_image_buttons(self):
        self.set_messages(18)
        self.page.evaluate("""() => {
            window.fontsBeforeFullCancel=domtoimage.impl.fontFaces.resolveAll;window.waitingForFull=false;
            domtoimage.toBlob=()=>new Promise(resolve=>{waitingForFull=true;window.releaseFull=resolve;});
            window.fullPending=saveContinuous();
        }""")
        self.page.wait_for_function("waitingForFull")
        for button_id in ["btn-save-image", "btn-export-screenshots", "btn-export-full"]:
            self.assertTrue(self.page.locator(f"#{button_id}").is_disabled())
        self.page.locator("#btn-cancel-export").click()
        self.page.wait_for_function("!captureInProgress")
        for button_id in ["btn-save-image", "btn-export-screenshots", "btn-export-full"]:
            self.assertFalse(self.page.locator(f"#{button_id}").is_disabled())
            self.assertIsNone(self.page.locator(f"#{button_id}").get_attribute("aria-busy"))
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)
        self.assertTrue(self.page.evaluate("domtoimage.impl.fontFaces.resolveAll===fontsBeforeFullCancel"))
        self.page.evaluate("releaseFull(new Blob(['late'],{type:'image/png'}))")
        self.assertEqual(len(self.downloads), 0)

    def test_oversized_continuous_export_splits_before_bitmap_and_restores_controls(self):
        self.set_messages(1)
        self.page.evaluate("""() => {
            const style=document.createElement('style');
            style.textContent='[data-capture="true"] [data-message-id] { min-height: 40000px !important; }';
            document.head.appendChild(style);exportOptions.scale=3;
            window.largeBitmaps=[];window.fontsBeforeLarge=domtoimage.impl.fontFaces.resolveAll;
            domtoimage.toBlob=async(node,options)=>{largeBitmaps.push({width:options.width,height:options.height});return new Blob(['part'],{type:'image/png'});};
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveContinuous()")
        frames = self.page.evaluate("largeBitmaps")
        self.assertEqual(len(frames), 4)
        self.assertTrue(all(frame["width"] <= 32767 and frame["height"] <= 32767
                            and frame["width"] * frame["height"] <= 64 * 1024 * 1024 for frame in frames))
        self.assertIn("split to fit", self.page.locator("#export-status").text_content())
        self.assertEqual(self.dialogs, [])
        self.assertTrue(result.value.suggested_filename.endswith(".zip"))
        self.assertTrue(self.page.evaluate("!captureInProgress&&domtoimage.impl.fontFaces.resolveAll===fontsBeforeLarge"))
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)
        self.assertEqual(len(self.downloads), 1)
        for button_id in ["btn-save-image", "btn-export-screenshots", "btn-export-full"]:
            self.assertFalse(self.page.locator(f"#{button_id}").is_disabled())

    def test_continuous_split_plans_cover_content_balance_parts_and_respect_limits(self):
        result = self.page.evaluate("""() => {
            const cases=[
                {width:375,height:15202,viewport:15000,scale:3,rows:[{top:16,bottom:14984}]},
                {width:600,height:2002,viewport:1800,scale:3,limits:{maxSide:32767,maxPixels:2000000},
                    rows:Array.from({length:40},(_,i)=>({top:16+i*44,bottom:56+i*44}))},
                {width:375,height:1902.25,viewport:1700.25,scale:1,limits:{maxSide:1200,maxPixels:1000000},
                    rows:[{top:16,bottom:28},{top:44,bottom:844},{top:844,bottom:908},{top:924,bottom:1684.25}]}
            ];let balanced=0;
            for(const fixture of cases) {
                const layout={paddingTop:16,paddingBottom:16,minHeight:160,rows:fixture.rows},limits=fixture.limits||CONTINUOUS_CAPTURE_LIMITS;
                const parts=planContinuousCaptureParts(fixture.width,fixture.height,fixture.viewport,layout,fixture.scale,limits);
                const maxHeight=Math.floor(Math.min(limits.maxSide,limits.maxPixels/(fixture.width*fixture.scale))/fixture.scale);
                const maxBody=Math.floor(maxHeight-(fixture.height-fixture.viewport));
                const bands=parts.map(part=>[part.offset,part.sourceEnd]);
                for(let i=0;i<parts.length;i++) {
                    const pixelsHigh=Math.ceil(fixture.height-fixture.viewport+parts[i].viewportHeight)*fixture.scale;
                    if(pixelsHigh>limits.maxSide||pixelsHigh*fixture.width*fixture.scale>limits.maxPixels)throw Error('Oversized part');
                    if(i&&Math.abs(bands[i][0]-bands[i-1][1])>.02)throw Error('Gap or duplicated pixels');
                }
                for(const row of fixture.rows) {
                    if(bands[0][0]>row.top+.02||bands.at(-1)[1]<row.bottom-.02)throw Error('Missing content');
                    if(row.bottom-row.top<=maxBody&&!bands.some(([start,end])=>start<=row.top+.02&&end>=row.bottom-.02))throw Error('Split fitting bubble');
                }
                if(fixture===cases[0]) {
                    if(parts.length!==2)throw Error('Expected halves');
                    balanced=Math.abs(parts[0].viewportHeight-parts[1].viewportHeight);
                }
            }
            const layout={paddingTop:16,paddingBottom:16,minHeight:160,rows:[{top:16,bottom:580}]};
            const atLimit=planContinuousCaptureParts(375,600,398,layout,2,{maxSide:1200,maxPixels:2000000});
            return {balanced,atLimit:atLimit.length===1&&atLimit[0].whole};
        }""")
        self.assertLessEqual(result["balanced"], 1)
        self.assertTrue(result["atLimit"])

    def test_split_continuous_chat_exports_real_png_parts_once_each_in_one_zip(self):
        self.set_messages(18)
        self.page.evaluate("""() => {
            const originalPlan=planContinuousCaptureParts,originalBlob=domtoimage.toBlob;
            planContinuousCaptureParts=(...args)=>originalPlan(...args,{maxSide:1200,maxPixels:1000000});
            window.splitFrames=[];window.splitBefore={scroll:chatContainer.scrollTop,messages:JSON.stringify(messages)};
            domtoimage.toBlob=async(node,options)=>{
                splitFrames.push({width:options.width,height:options.height,
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    headers:node.querySelectorAll('[data-phone-part="phone-header"]').length,
                    footers:node.querySelectorAll('[data-phone-part="phone-input-area"]').length,
                    rootTop:node.scrollTop,viewportScroll:phonePart(node,'chat-container').scrollTop,
                    headerTop:phonePart(node,'phone-header').getBoundingClientRect().top-node.getBoundingClientRect().top,
                    footerBottom:phonePart(node,'phone-input-area').getBoundingClientRect().bottom-node.getBoundingClientRect().top,
                    viewportTop:phonePart(node,'chat-container').getBoundingClientRect().top-node.getBoundingClientRect().top});
                const blob=await originalBlob(node,options),bitmap=await createImageBitmap(blob);
                const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
                const context=canvas.getContext('2d');context.drawImage(bitmap,0,0);bitmap.close();
                const chevron=context.getImageData(16,49,28,64).data,home=context.getImageData(120,canvas.height-24,135,22).data;
                let blue=0,black=0;
                for(let i=0;i<chevron.length;i+=4)if(chevron[i+2]>180&&chevron[i+2]-chevron[i]>70&&chevron[i+3]>200)blue++;
                for(let i=0;i<home.length;i+=4)if(home[i]<50&&home[i+1]<50&&home[i+2]<50&&home[i+3]>200)black++;
                splitFrames.at(-1).chromeVisible=blue>10&&black>100;
                return blob;
            };
        }""")
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate("saveContinuous()")
            self.assertIn("split to fit", self.page.locator("#export-status").text_content(), str(self.dialogs))
        frames = self.page.evaluate("splitFrames")
        self.assertEqual(len(frames), 2)
        self.assertTrue(all(frame["headerTop"] > 0 and frame["footerBottom"] <= frame["height"] and frame["rootTop"] == 0 for frame in frames), str(frames))
        self.assertTrue(all(frame["chromeVisible"] for frame in frames))
        self.assertEqual([message_id for frame in frames for message_id in frame["ids"]], [f"png-{i}" for i in range(18)])
        self.assertTrue(all(frame["headers"] == 1 and frame["footers"] == 1 for frame in frames))
        with tempfile.TemporaryDirectory(prefix="chat-split-") as directory:
            target = Path(directory) / "parts.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), 2)
                self.assertEqual(names, sorted(names))
                self.assertIsNone(archive.testzip())
                for index, name in enumerate(names):
                    self.assertIn(f"full-part-{index+1:03}", name)
                    data = archive.read(name)
                    self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                    width, height = struct.unpack(">II", data[16:24])
                    self.assertEqual(width, 375)
                    self.assertLessEqual(height, 1200)
                    (Path(tempfile.gettempdir()) / f"chat-generator-split-{index+1}.png").write_bytes(data)
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(self.dialogs, [])
        self.assertTrue(self.page.evaluate("chatContainer.scrollTop===splitBefore.scroll&&JSON.stringify(messages)===splitBefore.messages&&!captureInProgress"))

    def test_continuous_story_keeps_split_parts_next_to_their_block(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=Array.from({length:22},(_,i)=>({id:'a-'+i,type:'text',sender:first.ownerId,content:('Long visit '+i+'. ').repeat(8)}));
            second.messages=[{id:'b',type:'text',sender:second.ownerId,content:'Between the visits'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:first.messages.slice(0,20).map(m=>m.id)},
                {id:'two',conversationId:second.id,messageIds:['b']},
                {id:'three',conversationId:first.id,messageIds:first.messages.slice(20).map(m=>m.id)}];
            previewMode='story';renderChat();
            const original=planContinuousCaptureParts;planContinuousCaptureParts=(...args)=>original(...args,{maxSide:1200,maxPixels:1000000});
            window.splitStory=[];domtoimage.toBlob=async(node,options)=>{
                splitStory.push(Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId));
                return new Blob(['part'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveContinuous()")
        frames = self.page.evaluate("splitStory")
        self.assertGreater(len(frames), 3)
        self.assertEqual([message_id for frame in frames for message_id in frame],
                         [f"a-{i}" for i in range(20)] + ["b", "a-17", "a-18", "a-19", "a-20", "a-21"])
        with tempfile.TemporaryDirectory(prefix="chat-split-story-") as directory:
            target = Path(directory) / "story.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertTrue(all("block-001" in name and "full-part" in name for name in names[:-2]))
                self.assertIn("block-002", names[-2])
                self.assertIn("block-003", names[-1])
        self.assertEqual(len(self.downloads), 1)

    def test_cancelling_after_first_automatic_part_does_not_download_partial_zip(self):
        self.set_messages(18)
        self.page.evaluate("""() => {
            const original=planContinuousCaptureParts;planContinuousCaptureParts=(...args)=>original(...args,{maxSide:1200,maxPixels:1000000});
            window.partCalls=0;window.partsFontResolver=domtoimage.impl.fontFaces.resolveAll;
            domtoimage.toBlob=()=>{partCalls++;return partCalls===1?Promise.resolve(new Blob(['first'],{type:'image/png'})):new Promise(resolve=>{window.releasePart=resolve;});};
            window.partsPromise=saveContinuous();
        }""")
        self.page.wait_for_function("partCalls===2")
        self.page.evaluate("cancelCapture()")
        self.page.wait_for_function("!captureInProgress")
        self.assertEqual(len(self.downloads), 0)
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)
        self.assertTrue(self.page.evaluate("domtoimage.impl.fontFaces.resolveAll===partsFontResolver"))
        self.page.evaluate("releasePart(new Blob(['late'],{type:'image/png'}))")
        self.assertEqual(len(self.downloads), 0)

    def test_include_images_option_round_trips_and_old_backups_default_off(self):
        self.page.evaluate("openPreviewTools();document.getElementById('preview-export').open=true")
        option = self.page.locator("#export-include-images")
        self.assertFalse(option.is_checked())
        option.check()
        self.assertIn("ZIP", self.page.locator("#btn-export-full").text_content())
        self.assertIn("ZIP", self.page.locator("#save-image-label").text_content())
        result = self.page.evaluate("""() => {
            const backup=projectBackup(),roundTrip=validateBackup(JSON.parse(JSON.stringify(backup)));
            if(!roundTrip.exportOptions.includeImages)throw Error('Lost preference');
            delete backup.exportOptions.includeImages;
            const old=validateBackup(backup);applyProjectSnapshot(old);
            backup.exportOptions.includeImages='yes';let rejected=false;try{validateBackup(backup);}catch(_){rejected=true;}
            return {old:old.exportOptions.includeImages,rejected};
        }""")
        self.assertEqual(result, {"old": False, "rejected": True})
        self.assertFalse(option.is_checked())
        self.assertIn("PNG", self.page.locator("#save-image-label").text_content())

    def test_full_export_includes_uncropped_originals_in_order_and_original_format(self):
        self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=960;canvas.height=480;
            canvas.getContext('2d').fillRect(0,0,960,480);const png=canvas.toDataURL('image/png');
            canvas.width=320;canvas.height=640;const jpeg=canvas.toDataURL('image/jpeg',.8);
            window.originalSources=[png,jpeg];const chat=activeConversation();
            characters.find(c=>c.id!==chat.ownerId).avatar=png;
            messages=[{id:'photo-1',type:'image',sender:chat.ownerId,content:png,altText:'Wide image'},
                {id:'not-a-photo',type:'image-placeholder',sender:chat.ownerId,content:'An illustration',altText:''},
                {id:'photo-2',type:'image',sender:chat.ownerId,content:jpeg,altText:'Tall image'}];
            chat.messages=messages;settings.cropImages=true;storyBlocks=defaultStoryBlocks(conversations);
            exportOptions.includeImages=true;updateSettingsUI();
        }""")
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate("saveContinuous()")
            self.assertIn("files exported in ZIP", self.page.locator("#export-status").text_content(), str(self.dialogs))
        originals = self.page.evaluate("originalSources")
        with tempfile.TemporaryDirectory(prefix="chat-originals-") as directory:
            target = Path(directory) / "originals.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), 3)
                self.assertEqual(names, sorted(names))
                self.assertNotIn("-image-", names[0])
                self.assertTrue(names[1].startswith("000002-") and names[1].endswith("image-001.png"))
                self.assertTrue(names[2].startswith("000003-") and names[2].endswith("image-002.jpg"))
                self.assertEqual(archive.read(names[1]), base64.b64decode(originals[0].split(",", 1)[1]))
                self.assertEqual(archive.read(names[2]), base64.b64decode(originals[1].split(",", 1)[1]))
                self.assertEqual(struct.unpack(">II", archive.read(names[1])[16:24]), (960, 480))
                self.assertIsNone(archive.testzip())
        self.assertEqual(len(self.downloads), 1)
        self.assertEqual(self.dialogs, [])

    def test_paged_images_follow_first_visible_screenshot_without_overlap_duplicates(self):
        self.set_messages(18)
        self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=480;
            window.photoSource=canvas.toDataURL('image/png');window.photoFetches=0;const originalFetch=window.fetch;
            window.fetch=(source,options)=>{if(source===photoSource)photoFetches++;return originalFetch(source,options);};
            for(const index of [4,9])messages[index]={id:'photo-'+index,type:'image',sender:activeConversation().ownerId,content:photoSource,altText:'Photo '+index};
            activeConversation().messages=messages;settings.cropImages=true;exportOptions.includeImages=true;storyBlocks=defaultStoryBlocks(conversations);updateSettingsUI();
            window.photoScreens=[];domtoimage.toBlob=async(node)=>{
                const bounds=phonePart(node,'chat-container').getBoundingClientRect();
                photoScreens.push(Array.from(node.querySelectorAll('[data-message-id]')).filter(row=>{
                    if(!row.dataset.messageId.startsWith('photo-'))return false;
                    const image=row.querySelector('.preview-message-anchor img');if(!image)return false;
                    const rect=image.getBoundingClientRect();return rect.bottom>bounds.top&&rect.top<bounds.bottom;
                }).map(row=>row.dataset.messageId));
                return new Blob(['screenshot-'+photoScreens.length],{type:'image/png'});
            };
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveSeries()")
        screens = self.page.evaluate("photoScreens")
        self.assertIn("photo-4", screens[0])
        self.assertGreaterEqual(sum("photo-4" in photos for photos in screens), 2)
        with tempfile.TemporaryDirectory(prefix="chat-ordered-photos-") as directory:
            target = Path(directory) / "ordered.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertEqual([name[:6] for name in names], [f"{index+1:06}" for index in range(len(names))])
                cursor, seen = 0, set()
                for index, photos in enumerate(screens):
                    self.assertEqual(archive.read(names[cursor]), f"screenshot-{index+1}".encode())
                    cursor += 1
                    for photo in photos:
                        if photo in seen:
                            continue
                        seen.add(photo)
                        self.assertIn("-image-", names[cursor])
                        self.assertIn(f"part-{index+1:03}-image-", names[cursor])
                        cursor += 1
                self.assertEqual(cursor, len(names))
                self.assertEqual(len(seen), 2)
        self.assertEqual(self.page.evaluate("photoFetches"), 1)

    def test_single_screenshot_includes_only_its_visible_image_messages(self):
        self.set_messages(18)
        self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=180;
            const first=canvas.toDataURL('image/png');canvas.getContext('2d').fillRect(0,0,240,180);const last=canvas.toDataURL('image/png');
            messages[0]={id:'offscreen',type:'image',sender:activeConversation().ownerId,content:first,altText:''};
            messages[17]={id:'visible',type:'image',sender:activeConversation().ownerId,content:last,altText:''};
            activeConversation().messages=messages;exportOptions.includeImages=true;storyBlocks=defaultStoryBlocks(conversations);updateSettingsUI();chatContainer.scrollTop=chatContainer.scrollHeight;
            window.visibleSource=last;domtoimage.toBlob=async()=>new Blob(['screenshot'],{type:'image/png'});
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveImage()")
        original = base64.b64decode(self.page.evaluate("visibleSource").split(",", 1)[1])
        with tempfile.TemporaryDirectory(prefix="chat-visible-photo-") as directory:
            target = Path(directory) / "visible.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), 2)
                self.assertEqual(archive.read(names[0]), b"screenshot")
                self.assertEqual(archive.read(names[1]), original)

    def test_story_original_images_stay_after_their_block_screenshot(self):
        self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=120;const source=canvas.toDataURL('image/png');
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=['a','c'].map(id=>({id,type:'image',sender:first.ownerId,content:source,altText:id}));
            second.messages=[{id:'b',type:'image',sender:second.ownerId,content:source,altText:'b'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:['a']},{id:'two',conversationId:second.id,messageIds:['b']},{id:'three',conversationId:first.id,messageIds:['c']}];
            exportOptions.includeImages=true;previewMode='story';renderChat();
            window.photoContext=[];domtoimage.toBlob=async(node)=>{
                photoContext.push(node.querySelectorAll('[data-story-context]').length);
                return new Blob([node.querySelector('[data-message-id]:not([data-story-context])').dataset.messageId],{type:'image/png'});
            };
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveContinuous()")
        with tempfile.TemporaryDirectory(prefix="chat-story-originals-") as directory:
            target = Path(directory) / "story.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), 6)
                self.assertEqual(names, sorted(names))
                for index, message in enumerate(["a", "b", "c"]):
                    self.assertIn(f"block-{index+1:03}", names[2*index])
                    self.assertIn(f"block-{index+1:03}", names[2*index+1])
                    self.assertNotIn("-image-", names[2*index])
                    self.assertIn("-image-", names[2*index+1])
                    self.assertEqual(archive.read(names[2*index]), message.encode())
        self.assertEqual(self.page.evaluate("photoContext"), [0, 0, 1])

    def test_story_context_is_recent_same_chat_only_and_never_reveals_future_messages(self):
        result = self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=Array.from({length:5},(_,i)=>({id:'a'+i,type:'text',sender:first.ownerId,content:'A'+i}));
            second.messages=Array.from({length:2},(_,i)=>({id:'b'+i,type:'text',sender:second.ownerId,content:'B'+i}));
            const chats=[first,second],blocks=[
                {id:'one',conversationId:first.id,messageIds:['a0','a1','a2']},
                {id:'two',conversationId:second.id,messageIds:['b0']},
                {id:'three',conversationId:first.id,messageIds:['a3']},
                {id:'four',conversationId:first.id,messageIds:['a4']},
                {id:'five',conversationId:second.id,messageIds:['b1']}];
            const before=JSON.stringify({chats,blocks}),views=storyPreviewBlocks(chats,blocks,true);
            views.forEach(view=>createChatPhone(view.chat,view.messages,characters,phoneContainer,false,false,view.block.id,view.editableIds,view));
            return {ids:views.map(view=>view.displayMessages.map(m=>m.id)),
                context:views.map(view=>view.context.map(m=>m.id)),
                continuation:views.map(view=>view.continuation),
                compact:storyPreviewBlocks(chats,blocks,false).map(view=>view.displayMessages.map(m=>m.id)),
                unchanged:before===JSON.stringify({chats,blocks})};
        }""")
        self.assertEqual(result["ids"], [["a0", "a1", "a2"], ["b0"], ["a0", "a1", "a2", "a3"],
                                         ["a0", "a1", "a2", "a3", "a4"], ["b0", "b1"]])
        self.assertEqual(result["context"], [[], [], ["a0", "a1", "a2"], ["a0", "a1", "a2", "a3"], ["b0"]])
        self.assertEqual(result["continuation"], [False, False, True, True, True])
        self.assertEqual(result["compact"], [["a0", "a1", "a2"], ["b0"], ["a3"], ["a4"], ["b1"]])
        self.assertTrue(result["unchanged"])

    def test_short_returning_blocks_fill_spare_space_and_only_new_chats_keep_top_gap(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=Array.from({length:10},(_,i)=>({id:'a'+i,type:'text',sender:first.ownerId,content:'Message '+i}));
            second.messages=[{id:'time',type:'timestamp',sender:null,content:'Later'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:first.messages.slice(0,4).map(m=>m.id)},
                {id:'two',conversationId:second.id,messageIds:['time']},
                {id:'three',conversationId:first.id,messageIds:first.messages.slice(4).map(m=>m.id)}];
            storyContext=true;setDirectEditing(false);setPreviewMode('story');renderChat();
            window.historyFrames=[];domtoimage.toBlob=async node=>{
                const viewport=phonePart(node,'chat-container'),header=phonePart(node,'phone-header');
                const first=node.querySelector('[data-message-id]'),anchor=first.querySelector('.preview-message-anchor');
                historyFrames.push({ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    context:Array.from(node.querySelectorAll('[data-story-context]'),row=>row.dataset.messageId),
                    dividers:node.querySelectorAll('.new-messages-divider').length,
                    top:first.getBoundingClientRect().top-header.getBoundingClientRect().bottom,
                    anchorTop:anchor.getBoundingClientRect().top-viewport.getBoundingClientRect().top});
                return new Blob(['history'],{type:'image/png'});
            };
        }""")
        expected = [[f"a{i}" for i in range(4)], ["time"], [f"a{i}" for i in range(10)]]
        for export in ["saveSeries", "saveContinuous"]:
            self.page.evaluate("historyFrames=[]")
            with self.page.expect_download():
                self.page.evaluate(f"{export}()")
                self.assertEqual(self.dialogs, [])
            frames = self.page.evaluate("historyFrames")
            self.assertEqual([frame["ids"] for frame in frames], expected)
            self.assertEqual([frame["context"] for frame in frames], [[], [], [f"a{i}" for i in range(4)]])
            self.assertEqual([frame["dividers"] for frame in frames], [0, 0, 1])
            self.assertEqual([round(frame["top"]) for frame in frames], [32, 16, 0])
            self.assertEqual([round(frame["anchorTop"]) for frame in frames], [32, 56, 0])
        self.page.evaluate("setStoryContext(false);historyFrames=[]")
        with self.page.expect_download():
            self.page.evaluate("saveSeries()")
        frames = self.page.evaluate("historyFrames")
        self.assertEqual(frames[-1]["ids"], [f"a{i}" for i in range(4, 10)])
        self.assertTrue(all(not frame["context"] and not frame["dividers"] for frame in frames))
        self.assertEqual([round(frame["top"]) for frame in frames], [32, 16, 0])

    def test_returning_story_context_updates_read_only_and_compact_exports_match(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=[{id:'a',type:'text',sender:first.ownerId,content:'Earlier message'},
                {id:'c',type:'text',sender:first.ownerId,content:'Back in this chat'}];
            second.messages=[{id:'b',type:'text',sender:second.ownerId,content:'Another chat'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:['a']},{id:'two',conversationId:second.id,messageIds:['b']},
                {id:'three',conversationId:first.id,messageIds:['c']}];
            storyContext=true;setPreviewMode('story');renderChat();openPreviewTools();
        }""")
        last = self.page.locator('#story-preview section[data-story-block="three"]')
        self.assertEqual(last.locator('[data-message-id]').evaluate_all("rows=>rows.map(row=>row.dataset.messageId)"), ["a", "c"])
        self.assertEqual(last.locator('[data-story-context]').count(), 1)
        self.assertFalse(last.locator('[data-story-context]').get_attribute("data-preview-message"))
        last.locator('[data-story-context]').dblclick()
        self.assertFalse(self.page.locator("#preview-message-dialog").is_visible())
        last.locator('[data-message-id="c"]').dblclick()
        self.assertTrue(self.page.locator("#preview-message-dialog").is_visible())
        self.page.evaluate("document.getElementById('preview-message-dialog').close()")
        self.page.evaluate("messages[0].content='Updated earlier message';renderMessageUpdate('a')")
        self.assertIn("Updated earlier message", last.locator('[data-story-context]').text_content())
        self.assertEqual(self.page.locator("#phone-input-placeholder").text_content(), "Message")
        self.assertTrue(last.locator('.phone-container').evaluate("""phone=>{
            const header=phonePart(phone,'phone-header'),first=phone.querySelector('[data-message-id]');
            return Math.abs(first.getBoundingClientRect().top-header.getBoundingClientRect().bottom)<.05;
        }"""))
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate("saveContinuous()")
        with tempfile.TemporaryDirectory(prefix="chat-history-") as directory:
            target = Path(directory) / "history.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertEqual(len(names), 3)
                (Path(tempfile.gettempdir()) / "chat-generator-history-first.png").write_bytes(archive.read(names[0]))
                (Path(tempfile.gettempdir()) / "chat-generator-history-return.png").write_bytes(archive.read(names[-1]))
        old_height = last.locator(".phone-container").bounding_box()["height"]
        self.page.locator("#preview-story-context").uncheck()
        self.assertEqual(last.locator('[data-message-id]').count(), 1)
        new_height = last.locator(".phone-container").bounding_box()["height"]
        self.assertLess(new_height, old_height)
        self.assertLess(new_height, 360)
        self.page.evaluate("""() => {
            window.compactFrames=[];domtoimage.toBlob=async(node,options)=>{
                compactFrames.push({height:options.height,ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    context:node.querySelectorAll('[data-story-context]').length,label:node.textContent.includes('iMessage')});
                return new Blob(['compact'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveSeries()")
        frames = self.page.evaluate("compactFrames")
        self.assertEqual([frame["ids"] for frame in frames], [["a"], ["b"], ["c"]])
        self.assertTrue(all(frame["height"] < 360 and frame["context"] == 0 and not frame["label"] for frame in frames))

    def test_history_only_fills_short_returns_and_reflows_when_width_changes(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.settings.screenWidth=300;second.settings.headerName='Max';
            first.messages=Array.from({length:14},(_,i)=>({id:'fit-'+i,type:'text',sender:first.ownerId,
                content:i<8?'Earlier '+i:'New message '+i+'. '+('Testing measured text wrapping. ').repeat(4)}));
            second.messages=[{id:'other',type:'text',sender:second.ownerId,content:'Another chat'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'initial',conversationId:first.id,messageIds:first.messages.slice(0,8).map(m=>m.id)},
                {id:'other',conversationId:second.id,messageIds:['other']},
                {id:'return',conversationId:first.id,messageIds:first.messages.slice(8).map(m=>m.id)}];
            storyContext=true;setDirectEditing(false);setPreviewMode('story');renderChat();
            window.fittedFrames=[];domtoimage.toBlob=async node=>{
                fittedFrames.push({title:phonePart(node,'preview-name').textContent,height:node.getBoundingClientRect().height,
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    context:node.querySelectorAll('[data-story-context]').length,
                    dividers:node.querySelectorAll('.new-messages-divider').length});
                return new Blob(['fitted'],{type:'image/png'});
            };
        }""")
        returning = self.page.locator('#story-preview section[data-story-block="return"] .phone-container')
        self.assertGreater(returning.bounding_box()["height"], 812)
        self.assertEqual(returning.locator('[data-story-context],.new-messages-divider').count(), 0)
        for export in ["saveSeries", "saveContinuous"]:
            self.page.evaluate("fittedFrames=[]")
            with self.page.expect_download():
                self.page.evaluate(f"{export}()")
                self.assertEqual(self.dialogs, [])
            frames = self.page.evaluate("fittedFrames")
            returns = frames[next(i for i, frame in enumerate(frames) if frame["title"] == "Max") + 1:]
            self.assertTrue(all(not frame["context"] and not frame["dividers"] for frame in returns))
            self.assertEqual({message for frame in returns for message in frame["ids"]}, {f"fit-{i}" for i in range(8, 14)})
            if export == "saveSeries":
                self.assertGreater(len(returns), 1)
            else:
                self.assertEqual(len(returns), 1)
                self.assertGreater(returns[0]["height"], 812)
        self.page.evaluate("applyPreviewWidth(activeConversation(),600)")
        self.page.wait_for_function("document.querySelector('#story-preview section[data-story-block=return] [data-story-context]')")
        self.assertLessEqual(returning.bounding_box()["height"], 812.05)
        expected = returning.locator('[data-message-id]').evaluate_all("rows=>rows.map(row=>row.dataset.messageId)")
        self.assertEqual(expected[-6:], [f"fit-{i}" for i in range(8, 14)])
        self.assertGreater(len(expected), 6)
        self.assertEqual(returning.locator('.new-messages-divider').count(), 1)
        for export in ["saveSeries", "saveContinuous"]:
            self.page.evaluate("fittedFrames=[]")
            with self.page.expect_download():
                self.page.evaluate(f"{export}()")
            frames = self.page.evaluate("fittedFrames")
            self.assertEqual(len(frames), 3)
            self.assertEqual(frames[-1]["ids"], expected)
            self.assertEqual(frames[-1]["dividers"], 1)
            self.assertLessEqual(frames[-1]["height"], 812.05)

    def test_history_refits_after_uncropped_image_loads_and_matches_export(self):
        source = self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=960;
            canvas.getContext('2d').fillRect(0,0,240,960);return canvas.toDataURL('image/png');
        }""")
        data = base64.b64decode(source.split(',', 1)[1])
        pending, state = [], {"ready": False}

        def image_route(route):
            if state["ready"]:
                route.fulfill(body=data, content_type='image/png', headers={"access-control-allow-origin": "*"})
            else:
                pending.append(route)

        self.page.route('https://images.example.test/tall.png', image_route)
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);first.settings.cropImages=false;
            first.messages=Array.from({length:23},(_,i)=>({id:'image-fit-'+i,type:'text',sender:first.ownerId,content:'Message '+i}));
            first.messages.push({id:'photo',type:'image',sender:first.ownerId,content:'https://images.example.test/tall.png'});
            second.messages=[{id:'between',type:'text',sender:second.ownerId,content:'Other chat'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'initial',conversationId:first.id,messageIds:first.messages.slice(0,20).map(m=>m.id)},
                {id:'between',conversationId:second.id,messageIds:['between']},
                {id:'return',conversationId:first.id,messageIds:first.messages.slice(20).map(m=>m.id)}];
            storyContext=true;setDirectEditing(false);setPreviewMode('story');renderChat();
        }""")
        returning = self.page.locator('#story-preview section[data-story-block="return"] .phone-container')
        before = returning.locator('[data-story-context]').count()
        self.assertGreater(before, 0)
        state["ready"] = True
        for route in pending:
            route.fulfill(body=data, content_type='image/png', headers={"access-control-allow-origin": "*"})
        self.page.wait_for_function("document.querySelector('#story-preview section[data-story-block=return] [data-message-id=photo] img').naturalHeight===960")
        self.page.wait_for_function("count=>document.querySelectorAll('#story-preview section[data-story-block=return] [data-story-context]').length<count", arg=before)
        expected = returning.locator('[data-message-id]').evaluate_all("rows=>rows.map(row=>row.dataset.messageId)")
        self.assertLessEqual(returning.bounding_box()["height"], 812.05)
        self.page.evaluate("""() => {
            window.imageFitFrames=[];domtoimage.toBlob=async node=>{
                imageFitFrames.push(Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId));
                return new Blob(['fitted'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download():
            self.page.evaluate("saveContinuous()")
        self.assertEqual(self.page.evaluate("imageFitFrames.at(-1)"), expected)

    def test_story_context_preference_survives_backup_and_old_backups_default_on(self):
        result = self.page.evaluate("""() => {
            setStoryContext(false);const backup=projectBackup(),restored=validateBackup(JSON.parse(JSON.stringify(backup)));
            if(restored.storyContext!==false)throw Error('Lost preference');applyProjectSnapshot(restored);
            if(document.getElementById('preview-story-context').checked)throw Error('Wrong checkbox');
            delete backup.storyContext;const old=validateBackup(backup);applyProjectSnapshot(old);
            backup.storyContext='yes';let rejected=false;try{validateBackup(backup);}catch(_){rejected=true;}
            return {old:old.storyContext,checked:document.getElementById('preview-story-context').checked,rejected};
        }""")
        self.assertEqual(result, {"old": True, "checked": True, "rejected": True})

    def test_preview_controls_scroll_within_short_windows_without_panning_chats(self):
        self.set_section_story(long=True)
        self.page.set_viewport_size({'width': 1440, 'height': 480})
        self.page.evaluate("""() => {
            openPreviewTools();document.getElementById('preview-export').open=true;
            document.getElementById('preview-editing-guide').open=true;
            exportOptions.statusProgress={...DEFAULT_EXPORT_STATUS,enabled:true};syncExportOptionsUI();updatePreviewToolsLayout();
        }""")
        tools = self.page.locator('#preview-tools')
        body = tools.locator('.preview-tools-body')
        self.assertEqual(self.page.locator('#preview-panel').get_attribute('data-tools-layout'), 'sidebar')
        self.assertTrue(body.evaluate('node=>node.scrollHeight>node.clientHeight'))
        self.assertTrue(tools.evaluate('node=>node.getBoundingClientRect().bottom<=innerHeight'))
        before = self.page.evaluate("document.getElementById('preview-panel').scrollTop")
        body.hover()
        self.page.mouse.wheel(0, 1000)
        self.page.wait_for_function("document.querySelector('.preview-tools-body').scrollTop>0")
        self.assertEqual(self.page.evaluate("document.getElementById('preview-panel').scrollTop"), before)
        self.page.mouse.wheel(0, 1000)
        self.page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        self.assertEqual(self.page.evaluate("document.getElementById('preview-panel').scrollTop"), before)
        for height in [480, 300]:
            self.page.set_viewport_size({'width': 1440, 'height': height})
            self.page.wait_for_function("document.getElementById('preview-tools').getBoundingClientRect().bottom<=innerHeight")
            body.focus()
            self.page.locator('#btn-export-player').focus()
            self.assertTrue(self.page.locator('#btn-export-player').evaluate('node=>{const r=node.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}'))

    def test_preview_controls_compact_header_and_bulk_button_remain_reachable(self):
        self.set_section_story(long=True)
        self.page.set_viewport_size({'width': 390, 'height': 700})
        self.page.evaluate("""() => {
            if(!editorCollapsed)toggleEditorPanel();openPreviewTools();
            document.getElementById('preview-export').open=true;exportOptions.statusProgress={...DEFAULT_EXPORT_STATUS,enabled:true};
            syncExportOptionsUI();updatePreviewToolsLayout();
        }""")
        self.page.wait_for_function("document.getElementById('preview-panel').dataset.toolsLayout==='compact'")
        self.page.wait_for_function("parseFloat(getComputedStyle(document.getElementById('preview-panel')).paddingTop)>=63.99")
        self.page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        tools = self.page.locator('#preview-tools')
        body = tools.locator('.preview-tools-body')
        summary = tools.locator(':scope > summary')
        self.assertTrue(body.evaluate('node=>node.scrollHeight>node.clientHeight'))
        before = summary.bounding_box()['y']
        self.page.locator('#btn-export-player').focus()
        self.assertAlmostEqual(summary.bounding_box()['y'], before, delta=1)
        self.assertTrue(tools.evaluate('node=>node.getBoundingClientRect().bottom<=innerHeight'))
        self.assertTrue(self.page.locator('#btn-export-player').evaluate('node=>{const r=node.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}'))
        summary.click()
        button = self.page.locator('#preview-collapse-all')
        button.scroll_into_view_if_needed()
        self.assertTrue(button.evaluate("""node=>{
            const all=node.getBoundingClientRect(),single=node.parentNode.querySelector('.preview-collapse-handle').getBoundingClientRect();
            return all.bottom<=single.top&&all.left>=0&&all.right<=innerWidth;
        }"""))
        button.click()
        self.assertEqual(button.get_attribute('aria-label'), 'Expand all chats')
        self.assertTrue(button.evaluate('node=>{const r=node.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;}'))
        button.click()
        self.assertEqual(button.get_attribute('aria-label'), 'Collapse all chats')

    def test_preview_bulk_collapse_handles_mixed_state_rerenders_and_exports(self):
        self.set_section_story(long=True)
        self.page.evaluate('window.bulkBase=JSON.stringify({blocks:storyBlocks,messages:conversations.map(chat=>chat.messages)})')
        button = self.page.locator('#preview-collapse-all')
        self.assertEqual(button.get_attribute('aria-label'), 'Collapse all chats')
        self.assertTrue(button.evaluate("node=>{const r=node.getBoundingClientRect(),phone=node.parentNode.getBoundingClientRect();return r.bottom<phone.top;}"))
        button.click()
        self.assertEqual(self.page.locator('#story-preview .preview-chat-collapsed').count(), 3)
        self.assertEqual(button.get_attribute('aria-label'), 'Expand all chats')
        self.page.evaluate('renderChat()')
        self.assertEqual(button.get_attribute('aria-label'), 'Expand all chats')
        middle = self.page.locator('#story-preview section[data-story-block="middle"] .preview-collapse-handle')
        middle.focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(button.get_attribute('aria-label'), 'Collapse all chats')
        button.focus()
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.locator('#story-preview .preview-chat-collapsed').count(), 3)
        self.page.evaluate("""() => {
            window.bulkFrames=[];domtoimage.toBlob=async node=>{
                bulkFrames.push({height:node.getBoundingClientRect().height,
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    controls:node.querySelectorAll('.preview-collapse-all,.preview-collapse-handle').length});
                return new Blob(['bulk'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download():
            self.page.evaluate('saveContinuous()')
        frames = self.page.evaluate('bulkFrames')
        self.assertEqual(len(frames), 3)
        self.assertGreater(frames[0]['height'], 812)
        self.assertEqual(frames[0]['ids'], [f'a{i}' for i in range(10)])
        self.assertTrue(all(frame['controls'] == 0 for frame in frames))
        self.assertTrue(self.page.evaluate('bulkBase===JSON.stringify({blocks:storyBlocks,messages:conversations.map(chat=>chat.messages)})'))
        self.assertEqual(self.page.locator('#story-preview .preview-chat-collapsed').count(), 3)
        button.click()
        self.assertEqual(self.page.locator('#story-preview .preview-chat-collapsed').count(), 0)
        self.page.evaluate('conversations=[activeConversation()];storyBlocks=defaultStoryBlocks(conversations);renderChat()')
        self.assertEqual(button.count(), 0)

    def test_preview_collapse_keeps_chrome_and_locate_reopens_the_right_block(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=Array.from({length:22},(_,i)=>({id:'collapse-'+i,type:'text',sender:first.ownerId,
                content:'Message '+i+'. '+('A long chat can be folded from any visible edge. ').repeat(3)}));
            second.messages=[{id:'other',type:'text',sender:second.ownerId,content:'Another chat'}];
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'initial',conversationId:first.id,messageIds:first.messages.slice(0,20).map(m=>m.id)},
                {id:'other',conversationId:second.id,messageIds:['other']},
                {id:'return',conversationId:first.id,messageIds:first.messages.slice(20).map(m=>m.id)}];
            setPreviewMode('story');renderChat();document.getElementById('preview-panel').scrollTop=700;
        }""")
        first = self.page.locator('#story-preview section[data-story-block="initial"] .preview-phone-frame')
        other = self.page.locator('#story-preview section[data-story-block="return"] .preview-phone-frame')
        bounds = first.bounding_box()
        panel = self.page.locator('#preview-panel').bounding_box()
        y = panel['y'] + panel['height'] / 2
        self.page.mouse.move(bounds['x'] + bounds['width'], y)
        self.page.wait_for_function("Number(getComputedStyle(document.querySelector('#story-preview .preview-collapse-grip')).opacity)>0")
        self.page.mouse.click(bounds['x'] + bounds['width'] + 24, y)
        self.assertEqual(first.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'false')
        self.assertLess(first.bounding_box()['height'], 300)
        self.assertFalse(first.locator('[data-phone-part="chat-container"]').is_visible())
        self.assertTrue(first.locator('[data-phone-part="phone-header"]').is_visible())
        self.assertTrue(first.locator('[data-phone-part="phone-input-area"]').is_visible())
        self.assertTrue(first.locator('.preview-collapse-grip').evaluate("""grip=>{
            const icon=grip.getBoundingClientRect(),phone=grip.closest('.preview-phone-frame').getBoundingClientRect();
            return icon.top>=phone.top && icon.bottom<=phone.bottom && icon.top>=0 && icon.bottom<=innerHeight;
        }"""))
        self.assertEqual(other.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'true')
        self.page.evaluate('renderChat()')
        self.assertEqual(first.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'false')
        self.assertEqual(other.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'true')
        self.page.evaluate("scrollToMessage('collapse-0')")
        self.assertEqual(first.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'true')
        self.assertTrue(first.locator('[data-message-id="collapse-0"]').is_visible())
        first.locator('.preview-collapse-handle').focus()
        self.page.keyboard.press('Space')
        self.assertEqual(first.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'false')
        self.page.keyboard.press('Enter')
        self.assertEqual(first.locator('.preview-collapse-handle').get_attribute('aria-expanded'), 'true')

    def test_preview_collapse_preserves_current_scroll_and_does_not_change_exports(self):
        self.set_messages(30)
        self.page.evaluate("""() => {
            chatContainer.scrollTop=420;window.collapseScroll=chatContainer.scrollTop;
            window.collapseFrames=[];domtoimage.toBlob=async node=>{
                collapseFrames.push({height:node.getBoundingClientRect().height,viewport:phonePart(node,'chat-container').clientHeight,
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    controls:node.querySelectorAll('.preview-collapse-handle').length});
                return new Blob(['expanded export'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download():
            self.page.evaluate('saveImage()')
        current = self.page.locator('#conversation-phone-frame .preview-collapse-handle')
        current.focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(current.get_attribute('aria-expanded'), 'false')
        self.page.evaluate('renderChat()')
        self.assertEqual(current.get_attribute('aria-expanded'), 'false')
        with self.page.expect_download():
            self.page.evaluate('saveImage()')
        frames = self.page.evaluate('collapseFrames')
        self.assertEqual(frames[0], frames[1])
        self.assertEqual(frames[1]['height'], 812)
        self.assertGreater(frames[1]['viewport'], 500)
        self.assertEqual(frames[1]['controls'], 0)
        current.focus()
        self.page.keyboard.press('Enter')
        self.assertTrue(self.page.evaluate('Math.abs(chatContainer.scrollTop-collapseScroll)<1'))
        self.page.evaluate("setPreviewMode('story')")
        handle = self.page.locator('#story-preview .preview-collapse-handle')
        for export in ['saveSeries', 'saveContinuous']:
            self.page.evaluate('collapseFrames=[]')
            with self.page.expect_download():
                self.page.evaluate(f'{export}()')
            expanded = self.page.evaluate('collapseFrames')
            handle.focus()
            self.page.keyboard.press('Enter')
            self.page.evaluate('collapseFrames=[]')
            with self.page.expect_download():
                self.page.evaluate(f'{export}()')
            self.assertEqual(self.page.evaluate('collapseFrames'), expanded)
            self.assertEqual(handle.get_attribute('aria-expanded'), 'false')
            handle.focus()
            self.page.keyboard.press('Enter')

    def test_preview_collapse_control_stays_reachable_on_small_screens(self):
        self.set_messages(8)
        self.page.set_viewport_size({'width': 390, 'height': 900})
        handle = self.page.locator('#conversation-phone-frame .preview-collapse-handle')
        handle.scroll_into_view_if_needed()
        self.assertGreater(float(handle.locator('.preview-collapse-grip').evaluate('node=>getComputedStyle(node).opacity')), 0)
        self.assertTrue(handle.evaluate("node=>{const r=node.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;}"))
        handle.click()
        self.assertEqual(handle.get_attribute('aria-expanded'), 'false')
        handle.click()
        self.assertEqual(handle.get_attribute('aria-expanded'), 'true')

    def test_chat_labels_options_save_restore_and_old_backups_default_off(self):
        self.page.evaluate("setPreviewMode('story');openPreviewTools();document.getElementById('preview-export').open=true")
        toggle = self.page.locator('#export-chat-labels')
        self.assertFalse(toggle.is_checked())
        toggle.check()
        self.page.locator('#export-chat-label-skip-owner').select_option(label='User')
        self.page.locator('#export-scale').select_option('2')
        result = self.page.evaluate("""() => {
            const backup=projectBackup(),restored=validateBackup(JSON.parse(JSON.stringify(backup)));
            applyProjectSnapshot(restored);
            const saved={...exportOptions.chatLabels},ui=document.getElementById('export-chat-label-skip-owner').value;
            delete backup.exportOptions.chatLabels;const old=validateBackup(backup);
            const invalid=[null,false,{enabled:'yes'},{ignoreOwner:1},{ignoreOwner:'x'.repeat(81)}];
            let rejected=0;for(const value of invalid){backup.exportOptions.chatLabels=value;try{validateBackup(backup);}catch(_){rejected++;}}
            return {saved,ui,old:old.exportOptions.chatLabels,rejected};
        }""")
        self.assertEqual(result, {'saved': {'enabled': True, 'ignoreOwner': 'User'}, 'ui': 'User',
                                  'old': {'enabled': False, 'ignoreOwner': ''}, 'rejected': 5})
        self.page.evaluate("setPreviewMode('conversation')")
        self.assertFalse(self.page.locator('#export-chat-label-control').is_visible())
        self.page.evaluate("setPreviewMode('story')")
        self.assertTrue(toggle.is_checked())

    def test_chat_labels_owner_dropdown_tracks_renames_and_preserves_missing_names(self):
        self.page.evaluate("setPreviewMode('story');openPreviewTools();document.getElementById('preview-export').open=true")
        self.page.locator('#export-chat-labels').check()
        select = self.page.locator('#export-chat-label-skip-owner')
        self.assertEqual(select.evaluate('node=>node.tagName'), 'SELECT')
        self.assertEqual(select.locator('option').all_text_contents(), ['Include everyone'] + self.page.evaluate('characters.map(character=>character.name)'))
        select.select_option(label='User')
        self.page.evaluate("renameCharacter(characters.find(character=>character.name==='User').id,'You')")
        self.assertEqual(select.input_value(), 'You')
        self.assertEqual(self.page.evaluate('exportOptions.chatLabels.ignoreOwner'), 'You')
        self.page.evaluate('undoProject()')
        self.assertEqual(select.input_value(), 'User')
        self.page.evaluate("ensureCharacter('Nora');renderGroupAvatarSettings()")
        select.select_option(label='Nora')
        self.assertEqual(self.page.evaluate('exportOptions.chatLabels.ignoreOwner'), 'Nora')
        self.page.evaluate("removeCharacter(characters.find(character=>character.name==='Nora').id)")
        self.assertEqual(select.input_value(), 'Nora')
        self.assertIn('Nora (not in story)', select.locator('option').all_text_contents())
        select.select_option('')
        self.assertEqual(self.page.evaluate('exportOptions.chatLabels.ignoreOwner'), '')
        self.assertNotIn('Nora (not in story)', select.locator('option').all_text_contents())

    def test_chat_labels_put_owner_first_and_filter_only_exact_owner_names(self):
        result = self.page.evaluate("""() => {
            const people=[{id:'u',name:'User'},{id:'s',name:'Sarah'},{id:'m',name:'Max'},{id:'u2',name:'User 2'}];
            const user={id:'user-chat',ownerId:'u',participantIds:['s','u']},
                sarah={id:'sarah-chat',ownerId:'s',participantIds:['u','s']},
                group={id:'group',ownerId:'s',participantIds:['u','m','s']},
                another={id:'another',ownerId:'u2',participantIds:['u2','s']};
            const options={enabled:true,ignoreOwner:' User '};
            return {text:[chatLabelText(user,people),chatLabelText(sarah,people),chatLabelText(group,people)],
                show:[shouldExportChatLabel(null,sarah,options,people),shouldExportChatLabel(sarah.id,sarah,options,people),
                    shouldExportChatLabel(user.id,sarah,options,people),shouldExportChatLabel(sarah.id,user,options,people),
                    shouldExportChatLabel(sarah.id,another,options,people),
                    shouldExportChatLabel(sarah.id,user,{...options,ignoreOwner:'uSeR'},people),
                    shouldExportChatLabel(user.id,sarah,{...options,enabled:false},people)]};
        }""")
        self.assertEqual(result['text'], ['User & Sarah', 'Sarah & User', 'Sarah & User & Max'])
        self.assertEqual(result['show'], [False, False, True, False, True, False, False])

    def test_chat_labels_stay_between_jobs_parts_and_original_images_in_both_exports(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),sarah=first.participantIds.find(id=>id!==first.ownerId),max=characters.find(person=>person.name==='Max').id;
            const second=newConversation(first.participantIds,sarah),third=newConversation([sarah,max],sarah);
            Object.assign(second.settings,{screenWidth:300,darkMode:true});Object.assign(third.settings,{screenWidth:450,darkMode:false});
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=120;canvas.getContext('2d').fillRect(0,0,240,120);
            first.messages=Array.from({length:13},(_,i)=>({id:'a'+i,type:'text',sender:first.ownerId,
                content:i<10?'First '+i+'. '+('These messages need multiple screenshot pages. ').repeat(3):'Back again '+i}));
            Object.assign(first.messages[0],{type:'image',content:canvas.toDataURL('image/png')});
            second.messages=[{id:'b',type:'text',sender:sarah,content:'Sarah owns this phone.'}];
            third.messages=[{id:'c',type:'text',sender:sarah,content:'Talking to Max.'}];
            conversations=[first,second,third];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:first.messages.slice(0,10).map(m=>m.id)},
                {id:'same-chat',conversationId:first.id,messageIds:['a10','a11']},
                {id:'two',conversationId:second.id,messageIds:['b']},{id:'three',conversationId:third.id,messageIds:['c']},
                {id:'return',conversationId:first.id,messageIds:['a12']}];
            setDirectEditing(false);setPreviewMode('story');renderChat();
            exportOptions.scale=2;exportOptions.includeImages=true;exportOptions.chatLabels={enabled:true,ignoreOwner:'User'};
            exportOptions.statusProgress={...DEFAULT_EXPORT_STATUS,enabled:true,minutes:28,batteryDrop:14,connections:false};
            const original=planContinuousCaptureParts;planContinuousCaptureParts=(...args)=>original(...args,{maxSide:1200,maxPixels:1000000});
            window.labelFrames=[];window.mutateLabels=true;domtoimage.toBlob=async node=>{
                labelFrames.push({ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    time:phonePart(node,'preview-time').textContent,battery:phonePart(node,'preview-battery-text').textContent});
                if(mutateLabels){exportOptions.chatLabels.enabled=false;exportOptions.chatLabels.ignoreOwner='Sarah';mutateLabels=false;}
                return new Blob(['shot'],{type:'image/png'});
            };
        }""")
        for export in ['saveSeries', 'saveContinuous']:
            if export == 'saveContinuous':
                self.page.evaluate("exportOptions.chatLabels={enabled:true,ignoreOwner:'User'};labelFrames=[]")
            with self.page.expect_download() as result:
                self.page.evaluate(f'{export}()')
            self.assertEqual(self.page.evaluate('[labelFrames.at(-1).time,labelFrames.at(-1).battery]'), ['10:09', '86%'])
            with tempfile.TemporaryDirectory(prefix='chat-labels-') as directory:
                target = Path(directory) / 'labels.zip'
                result.value.save_as(target)
                with zipfile.ZipFile(target) as archive:
                    names = archive.namelist()
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(names, sorted(names))
                    self.assertEqual([int(name[:6]) for name in names], list(range(1, len(names)+1)))
                    labels = [name for name in names if name.endswith('-label.png')]
                    originals = [name for name in names if '-image-' in name]
                    self.assertEqual(len(labels), 2)
                    self.assertEqual(len(originals), 1)
                    self.assertEqual(len(names), len(self.page.evaluate('labelFrames')) + 3)
                    for label, block, width, artifact in zip(labels, ['003', '004'], [600, 900], ['sarah-user', 'sarah-max']):
                        self.assertIn(f'block-{block}-', label)
                        index = names.index(label)
                        self.assertIn(f'block-{block}-', names[index+1])
                        self.assertFalse(names[index+1].endswith('-label.png'))
                        png = archive.read(label)
                        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                        self.assertEqual(struct.unpack('>II', png[16:24]), (width, 128))
                        (Path(tempfile.gettempdir()) / f'chat-label-{artifact}.png').write_bytes(png)
                    before = names.index(labels[0])
                    self.assertIn('block-002-', names[before-1])
                    self.assertNotIn('-label.png', names[0])
        self.page.evaluate("exportOptions.chatLabels={enabled:true,ignoreOwner:''}")
        with self.page.expect_download() as result:
            self.page.evaluate('saveContinuous()')
        with tempfile.TemporaryDirectory(prefix='chat-label-return-') as directory:
            target = Path(directory) / 'labels.zip'
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                labels = [name for name in archive.namelist() if name.endswith('-label.png')]
                self.assertEqual(len(labels), 3)
                self.assertIn('block-005-', labels[-1])
                self.assertEqual(struct.unpack('>II', archive.read(labels[-1])[16:24]), (750, 128))
        self.page.evaluate("setPreviewMode('conversation')")
        with self.page.expect_download() as result:
            self.page.evaluate('saveSeries()')
        with tempfile.TemporaryDirectory(prefix='chat-label-current-') as directory:
            target = Path(directory) / 'current.zip'
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                self.assertFalse(any(name.endswith('-label.png') for name in archive.namelist()))
        self.assertEqual(len(self.downloads), 4)

    def test_chat_labels_wrap_long_unicode_group_names_without_transparency(self):
        with self.page.expect_download():
            self.page.evaluate("""async() => {
            const people=[{id:'s',name:('莎拉 👩‍🚀 Sarah ').repeat(5).trim()},
                {id:'m',name:('Max ').repeat(18).trim()},{id:'a',name:('Alex <&> ').repeat(8).trim()}];
            const chat={ownerId:'s',participantIds:['m','s','a'],settings:{darkMode:true}};
            const blob=await createChatLabelImage(chat,people,300,3),bitmap=await createImageBitmap(blob);
            const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
            const context=canvas.getContext('2d');context.drawImage(bitmap,0,0);bitmap.close();
            const data=context.getImageData(0,0,canvas.width,canvas.height).data;let painted=0;
            for(let y=48;y<canvas.height-48;y++)for(let x=72;x<canvas.width-72;x++)if(data[(y*canvas.width+x)*4]>100)painted++;
            window.longLabel={width:canvas.width,height:canvas.height,corner:Array.from(context.getImageData(5,5,1,1).data),painted,
                text:chatLabelText(chat,people)};downloadBlob(blob,'long-label.png');
            }""")
        self.assertEqual(len(self.downloads), 1)
        result = self.page.evaluate('longLabel')
        self.assertEqual(result['width'], 900)
        self.assertGreater(result['height'], 192)
        self.assertEqual(result['corner'], [0, 0, 0, 255])
        self.assertGreater(result['painted'], 100)
        self.assertTrue(result['text'].startswith('莎拉'))
        self.assertIn('<&>', result['text'])
        self.downloads[0].save_as(Path(tempfile.gettempdir()) / 'chat-label-long-names.png')

    def test_chat_labels_can_be_cancelled_without_downloading_partial_zip(self):
        self.set_section_story()
        self.page.evaluate("""() => {
            exportOptions.chatLabels={enabled:true,ignoreOwner:''};window.labelStarted=false;
            domtoimage.toBlob=async()=>new Blob(['shot'],{type:'image/png'});
            createChatLabelImage=()=>{labelStarted=true;return new Promise(resolve=>{window.releaseLabel=resolve;});};
            window.pendingLabelExport=saveSeries();
        }""")
        self.page.wait_for_function('labelStarted')
        self.page.evaluate('cancelCapture()')
        self.page.wait_for_function('!captureInProgress')
        self.assertEqual(self.downloads, [])
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)
        self.assertEqual(self.page.locator('#export-status').text_content(), 'Export cancelled.')
        self.page.evaluate("releaseLabel(new Blob(['late'],{type:'image/png'}))")
        self.assertEqual(self.downloads, [])

    def test_unavailable_original_keeps_screenshot_and_reports_it(self):
        self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=120;const source=canvas.toDataURL('image/png');
            messages=[{id:'photo',type:'image',sender:activeConversation().ownerId,content:source,altText:''}];
            activeConversation().messages=messages;exportOptions.includeImages=true;storyBlocks=defaultStoryBlocks(conversations);updateSettingsUI();
            const original=window.fetch;window.fetch=(url,options)=>url===source?Promise.reject(new Error('Download blocked')):original(url,options);
            domtoimage.toBlob=async()=>new Blob(['screenshot'],{type:'image/png'});
        }""")
        with self.page.expect_download() as result:
            self.page.evaluate("saveContinuous()")
        self.assertIn("1 image unavailable", self.page.locator("#export-status").text_content())
        self.assertEqual(self.dialogs, [])
        with tempfile.TemporaryDirectory(prefix="chat-unavailable-photo-") as directory:
            target = Path(directory) / "result.zip"
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(len(archive.namelist()), 1)
                self.assertEqual(archive.read(archive.namelist()[0]), b"screenshot")

    def test_status_progress_options_round_trip_and_story_order_defaults(self):
        self.page.evaluate("openPreviewTools();document.getElementById('preview-export').open=true")
        toggle = self.page.locator('#export-progress-status')
        self.assertFalse(toggle.is_checked())
        self.assertFalse(self.page.locator('#export-status-options').is_visible())
        toggle.check()
        self.assertTrue(self.page.locator('#export-status-options').is_visible())
        self.page.locator('#export-status-duration').fill('90')
        self.page.locator('#export-status-battery-drop').fill('12')
        self.page.locator('#export-status-connections').uncheck()
        result = self.page.evaluate("""() => {
            const duration=document.getElementById('export-status-duration'),toggle=document.getElementById('export-progress-status');
            duration.value='-1';toggle.checked=false;updateExportOptions();
            if(exportOptions.statusProgress.enabled || exportOptions.statusProgress.minutes!==90)throw Error('Cannot disable with invalid input');
            duration.value='0.25';toggle.checked=true;updateExportOptions();
            if(exportOptions.statusProgress.minutes!==.25)throw Error('Fractional duration rejected');
            duration.value='90';updateExportOptions();
            const backup=projectBackup(),restored=validateBackup(JSON.parse(JSON.stringify(backup)));
            applyProjectSnapshot(restored);
            const saved={...restored.exportOptions.statusProgress},mode=previewMode;
            delete backup.exportOptions.statusProgress;delete backup.previewMode;
            const old=validateBackup(backup),invalid=[null,false,{enabled:'yes'},{minutes:-1},{minutes:1441},
                {minutes:'30'},{minutes:null},{batteryDrop:1.5},{batteryDrop:101},{connections:1}];
            let rejected=0;for(const status of invalid){backup.exportOptions.statusProgress=status;try{validateBackup(backup);}catch(_){rejected++;}}
            const blank=validateBackup(blankProjectSnapshot('New story'));applyProjectSnapshot(blank);
            return {saved,mode,oldStatus:old.exportOptions.statusProgress,oldMode:old.previewMode,
                blankMode:previewMode,uiMode:document.getElementById('preview-mode').value,rejected};
        }""")
        self.assertEqual(result['saved'], {'enabled': True, 'minutes': 90, 'batteryDrop': 12, 'connections': False, 'signalVariation': 1, 'wifiVariation': 1})
        self.assertEqual(result['mode'], 'conversation')
        self.assertEqual(result['oldStatus'], {'enabled': False, 'minutes': 30, 'batteryDrop': 10, 'connections': True, 'signalVariation': 1, 'wifiVariation': 1})
        self.assertEqual([result['oldMode'], result['blankMode'], result['uiMode']], ['story'] * 3)
        self.assertEqual(result['rejected'], 10)

    def test_status_progress_timeline_rollover_limits_and_repeatable_connections(self):
        result = self.page.evaluate("""() => {
            const first={id:'a',ownerId:'user',settings:{...settings,time:'23:50',battery:35,signalStrength:2,wifiStrength:2},messages:[
                {id:'same',type:'text'},{id:'time',type:'timestamp'},{id:'last',type:'text'}]},
                second={...first,id:'b',messages:[{id:'same',type:'text'}]};
            const timeline=buildExportStatusTimeline([first,second],[
                {conversationId:'a',messageIds:['same','time']},{conversationId:'b',messageIds:['same']},
                {conversationId:'a',messageIds:['last']}]);
            const options={enabled:true,minutes:30,batteryDrop:10,connections:true};
            const points=[0,1,2].map(moment=>progressedExportStatus(first,options,moment,timeline.count));
            const connections=Array.from({length:65},(_,moment)=>progressedExportStatus(first,options,moment,65));
            const repeated=Array.from({length:65},(_,moment)=>progressedExportStatus(first,options,moment,65));
            const off=progressedExportStatus({...first,settings:{...first.settings,battery:1,signalStrength:0,wifiStrength:0}},
                {...options,batteryDrop:100},64,65);
            return {count:timeline.count,moments:[...timeline.moments].map(([id,moments])=>[id,[...moments]]),
                times:points.map(point=>point.time),battery:points.map(point=>point.battery),
                disabled:JSON.stringify(progressedExportStatus(first,{...options,enabled:false},2,3))===JSON.stringify(first.settings),
                single:progressedExportStatus(first,options,0,1).time,
                repeat:JSON.stringify(connections)===JSON.stringify(repeated),
                signal:[...new Set(connections.map(point=>point.signalStrength))],wifi:[...new Set(connections.map(point=>point.wifiStrength))],
                off:[off.battery,off.signalStrength,off.wifiStrength]};
        }""")
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['moments'], [['a', [['same', 0], ['time', 0], ['last', 2]]], ['b', [['same', 1]]]])
        self.assertEqual(result['times'], ['23:50', '00:05', '00:20'])
        self.assertEqual(result['battery'], [35, 30, 25])
        self.assertTrue(result['disabled'] and result['repeat'])
        self.assertEqual(result['single'], '23:50')
        self.assertGreater(len(result['signal']), 1)
        self.assertGreater(len(result['wifi']), 1)
        self.assertTrue(all(1 <= strength <= 4 for strength in result['signal']))
        self.assertTrue(all(1 <= strength <= 3 for strength in result['wifi']))
        self.assertEqual(result['off'], [1, 0, 0])

    def set_section_story(self, long=False):
        self.page.evaluate("""long => {
            const first=activeConversation(),person=ensureCharacter('Alex',characters),second=newConversation([first.ownerId,person.id],first.ownerId);
            first.messages=Array.from({length:long?12:4},(_,i)=>({id:'a'+i,type:'text',sender:first.ownerId,
                content:long&&i<10?'First '+i+'. '+('A longer section needs several screenshot pages. ').repeat(3):'Message '+i}));
            second.messages=[0,1].map(i=>({id:'b'+i,type:'text',sender:second.ownerId,content:'Another chat '+i}));
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'initial',conversationId:first.id,messageIds:first.messages.slice(0,-2).map(m=>m.id)},
                {id:'middle',conversationId:second.id,messageIds:second.messages.map(m=>m.id)},
                {id:'return',conversationId:first.id,messageIds:first.messages.slice(-2).map(m=>m.id)}];
            setPreviewMode('story');renderChat();
        }""", long)

    def test_section_status_icons_edit_only_their_section_and_reset_undo(self):
        self.set_section_story()
        self.page.evaluate("shareAppearance=true;sharedAppearance=sharedAppearanceFrom(settings);setPreviewChatCollapsed(document.querySelector('#story-preview section[data-story-block=return] .preview-phone-frame'),true)")
        first = self.page.locator('#story-preview section[data-story-block="initial"]')
        returning = self.page.locator('#story-preview section[data-story-block="return"]')
        returning.locator('[data-preview-setting="battery"]').click()
        self.assertIn('Applies to this section', self.page.locator('#preview-setting-popover').text_content())
        self.page.locator('[aria-label="Battery percentage"]').fill('45')
        self.assertEqual(returning.locator('[data-phone-part="preview-battery-text"]').text_content(), '45%')
        self.assertEqual(first.locator('[data-phone-part="preview-battery-text"]').text_content(), '100%')
        self.page.evaluate('closePreviewSetting()')
        returning.locator('[data-preview-setting="signalStrength"]').focus()
        self.page.keyboard.press('Home')
        self.page.keyboard.press('ArrowRight')
        wifi = returning.locator('[data-preview-setting="wifiStrength"]')
        wifi.scroll_into_view_if_needed()
        bounds = wifi.bounding_box()
        x, y = bounds['x'] + bounds['width']/2, bounds['y'] + bounds['height']/2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x-40, y, steps=5)
        self.page.mouse.up()
        self.page.evaluate("""() => {
            const anchor=document.querySelector('#story-preview section[data-story-block=return] [data-preview-setting=time]');
            openPreviewSetting(anchor);const picker=document.getElementById('preview-clock-picker');
            picker.value='14:00';picker.dispatchEvent(new Event('change',{bubbles:true}));closePreviewSetting();
        }""")
        expected = {'battery': 45, 'signalStrength': 1, 'wifiStrength': 1, 'time': '14:00'}
        self.assertEqual(self.page.evaluate("storyBlocks.find(block=>block.id==='return').status"), expected)
        self.assertEqual(self.page.evaluate('settings.battery'), 100)
        self.page.evaluate("setPreviewStatusValue(activeConversation(),'battery',99)")
        self.assertEqual(first.locator('[data-phone-part="preview-battery-text"]').text_content(), '99%')
        self.assertEqual(returning.locator('[data-phone-part="preview-battery-text"]').text_content(), '99%')
        expected.pop('battery')
        self.page.evaluate('applyProjectSnapshot(validateBackup(JSON.parse(JSON.stringify(projectBackup()))))')
        self.assertEqual(returning.locator('[data-phone-part="preview-time"]').text_content(), '14:00')
        returning.locator('[data-reset-section-status]').click()
        self.assertEqual(returning.locator('[data-phone-part="preview-battery-text"]').text_content(), '99%')
        self.assertEqual(returning.locator('[data-phone-part="preview-time"]').text_content(), '9:41')
        self.page.evaluate('undoProject()')
        self.assertEqual(self.page.evaluate("storyBlocks.find(block=>block.id==='return').status"), expected)

    def test_settings_apply_one_value_clears_only_its_overrides_and_supports_undo(self):
        self.set_section_story()
        self.page.evaluate("""() => {
            const [first,second]=conversations;Object.assign(first.settings,{time:'09:00',battery:80,screenWidth:340});
            Object.assign(second.settings,{time:'18:00',battery:30,screenWidth:460,darkMode:true,theme:'green'});
            storyBlocks[0].status={battery:70,time:'10:00'};storyBlocks[2].status={battery:20,time:'14:00',signalStrength:1};
            updateSettingsUI();switchTab('settings');
        }""")
        button = self.page.locator('[data-apply-setting="battery"]')
        self.assertEqual(self.page.locator('[data-setting-overrides="battery"]').text_content(), '2 custom')
        button.click()
        result = self.page.evaluate("""() => ({
            batteries:conversations.map(chat=>chat.settings.battery),widths:conversations.map(chat=>chat.settings.screenWidth),
            times:conversations.map(chat=>chat.settings.time),statuses:storyBlocks.map(block=>block.status||null),
            scope:shareAppearance,next:newConversation(activeConversation().participantIds).settings.battery
        })""")
        self.assertEqual(result['batteries'], [80, 80])
        self.assertEqual(result['widths'], [340, 460])
        self.assertEqual(result['times'], ['09:00', '18:00'])
        self.assertEqual(result['statuses'], [{'time': '10:00'}, None, {'time': '14:00', 'signalStrength': 1}])
        self.assertFalse(result['scope'])
        self.assertEqual(result['next'], 80)
        self.assertEqual(self.page.locator('[data-setting-overrides="battery"]').text_content(), '')
        self.page.evaluate('undoProject()')
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.battery)'), [80, 30])
        self.assertEqual(self.page.locator('[data-setting-overrides="battery"]').text_content(), '2 custom')
        self.page.evaluate('redoProject()')
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.battery)'), [80, 80])

    def test_settings_scope_changes_only_the_edited_field_and_survives_backup(self):
        self.set_section_story()
        self.page.evaluate("""() => {
            Object.assign(settings,{time:'09:00',screenWidth:340});
            Object.assign(conversations[1].settings,{time:'18:00',battery:30,screenWidth:460,darkMode:true,theme:'green',headerName:'Alex'});
            storyBlocks[0].status={time:'10:00',battery:70};storyBlocks[2].status={time:'14:00',battery:20};
            updateSettingsUI();switchTab('settings');
            window.scopeBefore=JSON.stringify({settings:conversations.map(chat=>chat.settings),blocks:storyBlocks});
        }""")
        self.page.locator('#setting-edit-scope').select_option('all')
        self.assertTrue(self.page.evaluate('scopeBefore===JSON.stringify({settings:conversations.map(chat=>chat.settings),blocks:storyBlocks})'))
        self.page.locator('#setting-darkmode').check()
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.darkMode)'), [True, True])
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.screenWidth)'), [340, 460])
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.theme)'), ['blue', 'green'])
        self.page.locator('#setting-time').fill('12:15')
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.time)'), ['12:15', '12:15'])
        self.assertEqual(self.page.evaluate('storyBlocks.map(block=>block.status||null)'), [{'battery': 70}, None, {'battery': 20}])
        self.page.locator('#setting-name').fill('Custom title')
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.headerName)'), ['Custom title', 'Alex'])
        self.page.evaluate("applyPreviewWidth(activeConversation(),500);setPreviewStatusValue(activeConversation(),'battery',60)")
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.screenWidth)'), [500, 500])
        self.assertTrue(self.page.evaluate('storyBlocks.every(block=>!block.status)'))
        self.page.evaluate('applyProjectSnapshot(validateBackup(JSON.parse(JSON.stringify(projectBackup()))))')
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.theme)'), ['blue', 'green'])
        self.assertEqual(self.page.locator('#setting-edit-scope').input_value(), 'all')
        self.assertEqual(self.page.evaluate("[sharedAppearance.time,sharedAppearance.battery,sharedAppearance.screenWidth]"), ['12:15', 60, 500])

    def test_settings_apply_all_is_one_undo_step_and_preserves_chat_details(self):
        self.set_section_story()
        self.page.evaluate("""() => {
            Object.assign(settings,{headerName:'First title',time:'09:00',battery:80,screenWidth:340,avatar:null});
            Object.assign(conversations[1].settings,{headerName:'Second title',time:'18:00',battery:30,screenWidth:460,darkMode:true,theme:'green',avatar:null});
            storyBlocks[0].status={battery:70,time:'10:00'};storyBlocks[2].status={battery:20,time:'14:00'};
            updateSettingsUI();switchTab('settings');window.applyAllUndo=undoStack.length;
        }""")
        self.page.locator('#settings-apply-all').click()
        self.assertTrue(self.page.evaluate('conversations.every(chat=>SHARED_SETTING_KEYS.every(key=>chat.settings[key]===settings[key]))'))
        self.assertTrue(self.page.evaluate('storyBlocks.every(block=>!block.status)'))
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.headerName)'), ['First title', 'Second title'])
        self.assertTrue(self.page.evaluate('undoStack.length===applyAllUndo+1&&!shareAppearance'))
        self.page.evaluate('undoProject()')
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.screenWidth)'), [340, 460])
        self.assertEqual(self.page.evaluate('storyBlocks.map(block=>block.status||null)'), [{'battery': 70, 'time': '10:00'}, None, {'battery': 20, 'time': '14:00'}])
        self.page.evaluate('applyProjectSnapshot(validateBackup(blankProjectSnapshot()))')
        self.assertTrue(self.page.locator('#settings-apply-all').is_disabled())

    def test_settings_can_apply_a_section_value_from_its_preview_popover(self):
        self.set_section_story()
        self.page.evaluate("storyBlocks[1].status={battery:44};storyBlocks[2].status={battery:20,time:'14:00'};renderChat()")
        self.page.locator('#story-preview section[data-story-block="middle"] [data-preview-setting="battery"]').click()
        self.page.locator('#preview-setting-popover [aria-label="Apply battery to all chats"]').click()
        self.assertEqual(self.page.evaluate('conversations.map(chat=>chat.settings.battery)'), [44, 44])
        self.assertEqual(self.page.evaluate('storyBlocks.map(block=>block.status||null)'), [None, None, {'time': '14:00'}])
        self.assertFalse(self.page.locator('#preview-setting-popover').is_visible())

    def test_section_status_survives_script_apply_duplicate_backup_and_player_export(self):
        self.set_section_story()
        result = self.page.evaluate("""() => {
            setPreviewStatusValue(activeConversation(),'time','14:00',{blockId:'return'});
            setPreviewStatusValue(activeConversation(),'battery',50,{blockId:'return'});
            populateScriptFromMessages();document.getElementById('script-input').value=document.getElementById('script-input').value.replace('Message 3','Edited message');
            markScriptDirty();parseScript();
            const original=storyBlocks.find(block=>block.id==='return');
            if(!original||original.status.time!=='14:00')throw Error('Script lost section status');
            duplicateStoryBlock('return');const copy=storyBlocks[storyBlocks.indexOf(original)+1];
            setPreviewStatusValue(activeConversation(),'battery',5,{blockId:copy.id});
            const backup=projectBackup(),restored=validateBackup(JSON.parse(JSON.stringify(backup)));
            const playable=buildPlayableStory(restored,'section-check');
            const invalid=[null,[],{battery:0},{signalStrength:5},{wifiStrength:-1},{time:'25:01'},{screenWidth:600},JSON.parse('{"__proto__":1}')];
            let rejected=0;for(const status of invalid){const raw=JSON.parse(JSON.stringify(backup));raw.storyBlocks[0].status=status;try{validateBackup(raw);}catch(_){rejected++;}}
            return {original:original.status,copy:copy.status,restored:restored.storyBlocks.find(block=>block.id==='return').status,
                player:playable.nodes.find(node=>node.id==='chat:return').status,rejected,scriptError:!document.getElementById('script-error').classList.contains('hidden')};
        }""")
        expected = {'time': '14:00', 'battery': 50}
        self.assertEqual(result['original'], expected)
        self.assertEqual(result['copy'], {'time': '14:00', 'battery': 5})
        self.assertEqual(result['restored'], expected)
        self.assertEqual(result['player'], expected)
        self.assertEqual(result['rejected'], 8)
        self.assertFalse(result['scriptError'])

    def test_section_status_progress_uses_local_values_in_all_png_modes(self):
        self.set_section_story(long=True)
        self.page.evaluate("""() => {
            conversations.forEach(chat=>Object.assign(chat.settings,{time:'09:00',battery:90,signalStrength:2,wifiStrength:2}));
            storyBlocks.find(block=>block.id==='return').status={time:'14:00',battery:40,signalStrength:1,wifiStrength:0};renderChat();
            exportOptions.statusProgress={enabled:true,minutes:26,batteryDrop:26,connections:false,signalVariation:0,wifiVariation:0};
            window.sectionFrames=[];window.mutateSection=true;const original=domtoimage.toBlob;
            domtoimage.toBlob=async(node,options)=>{
                sectionFrames.push({time:phonePart(node,'preview-time').textContent,battery:phonePart(node,'preview-battery-text').textContent,
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId)});
                if(mutateSection){Object.assign(storyBlocks.find(block=>block.id==='return').status,{time:'22:00',battery:1});mutateSection=false;}
                return node.querySelector('[data-message-id="a11"]')&&options.height<1000?original(node,options):new Blob(['section'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate('saveContinuous()')
        frames = self.page.evaluate('sectionFrames')
        self.assertEqual([frame['time'] for frame in frames], ['9:18', '9:22', '14:02'])
        self.assertEqual([frame['battery'] for frame in frames], ['72%', '68%', '38%'])
        with tempfile.TemporaryDirectory(prefix='chat-section-status-') as directory:
            target = Path(directory) / 'sections.zip'
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                png = archive.read(archive.namelist()[-1])
                self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                (Path(tempfile.gettempdir()) / 'chat-generator-section-status.png').write_bytes(png)
        self.page.evaluate("Object.assign(storyBlocks.find(block=>block.id==='return').status,{time:'14:00',battery:40});sectionFrames=[]")
        with self.page.expect_download():
            self.page.evaluate('saveSeries()')
        frames = self.page.evaluate('sectionFrames')
        self.assertGreater(len(frames), 3)
        self.assertEqual((frames[-1]['time'], frames[-1]['battery']), ('14:02', '38%'))
        self.page.evaluate("setPreviewMode('conversation');chatContainer.scrollTop=chatContainer.scrollHeight;sectionFrames=[]")
        with self.page.expect_download():
            self.page.evaluate('saveImage()')
        self.assertEqual(self.page.evaluate("[sectionFrames[0].time,sectionFrames[0].battery]"), ['14:02', '38%'])
        self.page.evaluate('exportOptions.statusProgress.enabled=false;sectionFrames=[]')
        with self.page.expect_download():
            self.page.evaluate('saveImage()')
        self.assertEqual(self.page.evaluate("[sectionFrames[0].time,sectionFrames[0].battery]"), ['14:00', '40%'])

    def test_section_status_variation_ranges_are_configurable_bounded_and_saved(self):
        self.page.evaluate("openPreviewTools();document.getElementById('preview-export').open=true")
        self.page.locator('#export-progress-status').check()
        self.page.locator('#export-status-signal-range').select_option('0')
        self.page.locator('#export-status-wifi-range').select_option('3')
        result = self.page.evaluate("""() => {
            const backup=projectBackup(),restored=validateBackup(JSON.parse(JSON.stringify(backup)));
            applyProjectSnapshot(restored);
            const chat={id:'a',ownerId:'user',settings:{...settings,signalStrength:2,wifiStrength:2}};
            const options={...exportOptions.statusProgress,signalVariation:4,wifiVariation:3};
            const large=Array.from({length:128},(_,moment)=>progressedExportStatus(chat,options,moment,128));
            const fixed=Array.from({length:128},(_,moment)=>progressedExportStatus(chat,{...options,signalVariation:0,wifiVariation:0},moment,128));
            const small=Array.from({length:128},(_,moment)=>progressedExportStatus(chat,{...options,signalVariation:1,wifiVariation:1},moment,128));
            const custom=progressedExportStatus(chat,options,20,128,{start:20,status:{signalStrength:1,wifiStrength:3}});
            const invalid=[{signalVariation:5},{signalVariation:-1},{signalVariation:1.5},{wifiVariation:4},{wifiVariation:'2'}];
            let rejected=0;for(const patch of invalid){const raw=JSON.parse(JSON.stringify(backup));Object.assign(raw.exportOptions.statusProgress,patch);try{validateBackup(raw);}catch(_){rejected++;}}
            return {saved:restored.exportOptions.statusProgress,
                ui:[document.getElementById('export-status-signal-range').value,document.getElementById('export-status-wifi-range').value],
                signal:[...new Set(large.map(value=>value.signalStrength))],wifi:[...new Set(large.map(value=>value.wifiStrength))],
                fixed:fixed.every(value=>value.signalStrength===2&&value.wifiStrength===2),
                small:small.every(value=>Math.abs(value.signalStrength-2)<=1&&Math.abs(value.wifiStrength-2)<=1),
                custom:[custom.signalStrength,custom.wifiStrength],rejected};
        }""")
        self.assertEqual(result['saved']['signalVariation'], 0)
        self.assertEqual(result['saved']['wifiVariation'], 3)
        self.assertEqual(result['ui'], ['0', '3'])
        self.assertEqual(set(result['signal']), set(range(5)))
        self.assertEqual(set(result['wifi']), set(range(4)))
        self.assertTrue(result['fixed'] and result['small'])
        self.assertEqual(result['custom'], [1, 3])
        self.assertEqual(result['rejected'], 5)

    def test_status_progress_exports_follow_script_order_ignore_context_and_freeze_options(self):
        self.page.evaluate("""() => {
            const first=activeConversation(),second=newConversation(first.participantIds);
            first.messages=Array.from({length:24},(_,i)=>({id:'a'+i,type:'text',sender:first.ownerId,
                content:i<20?'Earlier message '+i+'. '+('Text that makes several screenshot pages. ').repeat(3):'Returning message '+i}));
            second.messages=[0,1].map(i=>({id:'b'+i,type:'text',sender:second.ownerId,content:'Another chat '+i}));
            conversations=[first,second];messages=first.messages;storyBlocks=[
                {id:'one',conversationId:first.id,messageIds:first.messages.slice(0,20).map(m=>m.id)},
                {id:'two',conversationId:second.id,messageIds:second.messages.map(m=>m.id)},
                {id:'three',conversationId:first.id,messageIds:first.messages.slice(20).map(m=>m.id)}];
            conversations.forEach(chat=>Object.assign(chat.settings,{time:'23:50',battery:80,signalStrength:2,wifiStrength:2}));
            setDirectEditing(false);setPreviewMode('story');renderChat();
            exportOptions.statusProgress={enabled:true,minutes:30,batteryDrop:70,connections:true};
            window.statusBase=JSON.stringify(conversations.map(chat=>chat.settings));
            window.statusFrames=[];window.realStatus=true;window.mutateStatus=true;const original=domtoimage.toBlob;
            domtoimage.toBlob=async(node,options)=>{
                statusFrames.push({time:phonePart(node,'preview-time').textContent,battery:phonePart(node,'preview-battery-text').textContent,
                    signal:Array.from(node.querySelectorAll('[data-signal-bar]'),bar=>bar.getAttribute('fill-opacity')),
                    wifi:Array.from(node.querySelectorAll('[data-wifi-level]'),bar=>bar.getAttribute('fill-opacity')),
                    ids:Array.from(node.querySelectorAll('[data-message-id]'),row=>row.dataset.messageId),
                    context:node.querySelectorAll('[data-story-context]').length,
                    red:phonePart(node,'battery-level-rect').style.fill});
                if(mutateStatus){exportOptions.statusProgress.minutes=120;exportOptions.statusProgress.batteryDrop=0;mutateStatus=false;}
                return realStatus&&node.querySelector('[data-message-id="a23"]')?original(node,options):new Blob(['status'],{type:'image/png'});
            };
        }""")
        with self.page.expect_download(timeout=60000) as result:
            self.page.evaluate('saveContinuous()')
        frames = self.page.evaluate('statusFrames')
        self.assertEqual([frame['time'] for frame in frames], ['0:12', '0:15', '0:20'])
        self.assertEqual([frame['battery'] for frame in frames], ['27%', '22%', '10%'])
        self.assertGreater(frames[-1]['context'], 0)
        self.assertEqual(frames[-1]['red'], 'rgb(239, 68, 68)')
        with tempfile.TemporaryDirectory(prefix='chat-status-') as directory:
            target = Path(directory) / 'status.zip'
            result.value.save_as(target)
            with zipfile.ZipFile(target) as archive:
                png = archive.read(archive.namelist()[-1])
                self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
                (Path(tempfile.gettempdir()) / 'chat-generator-status-progress.png').write_bytes(png)
        self.assertTrue(self.page.evaluate("JSON.stringify(conversations.map(chat=>chat.settings))===statusBase"))
        self.assertEqual(self.page.locator('#preview-time').text_content(), '23:50')
        self.page.evaluate("exportOptions.statusProgress={enabled:true,minutes:30,batteryDrop:70,connections:true};statusFrames=[];realStatus=false")
        with self.page.expect_download():
            self.page.evaluate('saveContinuous()')
        self.assertEqual(self.page.evaluate('statusFrames'), frames)
        self.page.evaluate('statusFrames=[]')
        with self.page.expect_download():
            self.page.evaluate('saveSeries()')
        paged = self.page.evaluate('statusFrames')
        self.assertGreater(len(paged), 3)
        self.page.evaluate("""() => {
            const original=planContinuousCaptureParts;
            planContinuousCaptureParts=(...args)=>original(...args,{maxSide:1200,maxPixels:1000000});statusFrames=[];
        }""")
        with self.page.expect_download():
            self.page.evaluate('saveContinuous()')
        parts = self.page.evaluate('statusFrames')
        self.assertGreater(len(parts), 3)
        for frame in paged + parts:
            moments = [(int(message[1:]) if int(message[1:]) < 20 else int(message[1:]) + 2)
                       if message.startswith('a') else 20 + int(message[1:]) for message in frame['ids']]
            progress = max(moments) / 25
            minutes = (23 * 60 + 50 + int(30 * progress + 1e-7)) % 1440
            self.assertEqual(frame['time'], f'{minutes // 60}:{minutes % 60:02}')
            self.assertEqual(frame['battery'], f'{80-int(70 * progress + 1e-7)}%')
        self.page.evaluate('exportOptions.statusProgress.enabled=false;statusFrames=[]')
        with self.page.expect_download():
            self.page.evaluate('saveSeries()')
        self.assertTrue(all(frame['time'] == '23:50' and frame['battery'] == '80%' for frame in self.page.evaluate('statusFrames')))
        self.page.evaluate("exportOptions.statusProgress.enabled=true;statusFrames=[];setPreviewMode('conversation');chatContainer.scrollTop=chatContainer.scrollHeight")
        with self.page.expect_download():
            self.page.evaluate('saveImage()')
        single = self.page.evaluate('statusFrames')
        self.assertEqual(len(single), 1)
        self.assertEqual((single[0]['time'], single[0]['battery']), ('0:20', '10%'))

    def test_cancelling_original_image_fetch_stops_export_without_download(self):
        source = self.page.evaluate("""() => {
            const canvas=document.createElement('canvas');canvas.width=240;canvas.height=120;return canvas.toDataURL('image/png');
        }""")
        image_data = base64.b64decode(source.split(",", 1)[1])
        pending = []

        def serve_image(route):
            if route.request.resource_type == "image":
                route.fulfill(body=image_data, content_type="image/png", headers={"access-control-allow-origin": "*"})
            else:
                pending.append(route)

        self.page.route("https://images.example.test/photo.png", serve_image)
        self.page.evaluate("""() => {
            messages=[{id:'photo',type:'image',sender:activeConversation().ownerId,content:'https://images.example.test/photo.png',altText:''}];
            activeConversation().messages=messages;exportOptions.includeImages=true;storyBlocks=defaultStoryBlocks(conversations);updateSettingsUI();
            window.fontsBeforeImageCancel=domtoimage.impl.fontFaces.resolveAll;
            domtoimage.toBlob=async()=>new Blob(['screenshot'],{type:'image/png'});window.imageExport=saveContinuous();
        }""")
        self.page.wait_for_function("document.getElementById('export-status').textContent.startsWith('Including image')")
        self.page.evaluate("cancelCapture()")
        self.page.wait_for_function("!captureInProgress")
        self.assertEqual(len(self.downloads), 0)
        self.assertEqual(self.page.locator('[data-capture="true"]').count(), 0)
        self.assertTrue(self.page.evaluate("domtoimage.impl.fontFaces.resolveAll===fontsBeforeImageCancel"))
        self.assertFalse(self.page.locator("#btn-export-full").is_disabled())
        for route in pending:
            route.abort("aborted")
        self.page.unroute("https://images.example.test/photo.png", serve_image)


if __name__ == "__main__":
    unittest.main()
