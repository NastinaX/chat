"""Offline regression checks. Requires Python, Playwright, and its Chromium browser."""
import tempfile
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as error:
    raise unittest.SkipTest("Install Playwright and its Chromium browser to run these checks.") from error


PLAYER = (Path(__file__).resolve().parents[1] / "player.html").as_uri()


class PlayerTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={"width": 1440, "height": 1000}, offline=True, reduced_motion="reduce"
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(PLAYER)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def open_timeline(self):
        self.page.locator("#controls-toggle").click()
        self.page.locator("#timeline-button").click()
        self.assertTrue(self.page.locator("#timeline-panel").is_visible())

    def test_reopened_chat_keeps_earlier_messages_without_transport_label(self):
        self.assertEqual(self.page.locator("#scripted-message").get_attribute("placeholder"), "Message")
        self.assertEqual(self.page.locator(".service").count(), 0)
        self.page.locator("#phone-example-button").click()
        self.page.evaluate("pause();seekStory('step-16')")
        self.assertEqual(self.page.evaluate("engine.histories.get('sarah').length"), 4)
        text = self.page.locator("#chat-messages").text_content()
        self.assertIn("Still up for a movie", text)
        self.assertIn("Tickets are booked", text)
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 1)
        self.assertIn("Tickets are booked", self.page.locator('.new-messages-divider + .message').text_content())
        self.assertNotIn("iMessage", self.page.locator("#chat-scroll").text_content())
        self.page.locator("#chat-back").click()
        self.page.locator('.chat-list-row[data-open-chat="sarah"]').click()
        self.assertEqual(self.page.locator("#chat-messages").text_content(), text)
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 1)

    def test_section_status_follows_visits_browsing_and_timeline_seeks(self):
        self.page.evaluate("""() => {
            const raw=exampleStory();raw.nodes[0].status={time:'09:00',battery:90};
            raw.nodes[15].status={time:'14:00',battery:40,signalStrength:1,wifiStrength:0};loadStory(raw);pause();seekStory('step-3');
        }""")
        self.assertEqual(self.page.locator('#clock').text_content(), '9:00')
        self.assertEqual(self.page.locator('#battery-text').text_content(), '90%')
        self.page.evaluate("seekStory('step-14');openChat('sarah')")
        self.assertEqual(self.page.locator('#clock').text_content(), '9:00')
        self.page.evaluate("seekStory('step-16')")
        self.assertEqual(self.page.locator('#clock').text_content(), '14:00')
        self.assertEqual(self.page.locator('#battery-text').text_content(), '40%')
        self.assertTrue(self.page.locator('#wifi-off').is_visible())
        self.page.locator('#chat-back').click()
        self.page.locator('[data-open-chat="sarah"]').click()
        self.assertEqual(self.page.locator('#clock').text_content(), '14:00')
        self.page.evaluate("seekStory('step-3')")
        self.assertEqual(self.page.locator('#clock').text_content(), '9:00')
        self.assertEqual(self.page.locator('#battery-text').text_content(), '90%')
        self.page.evaluate("loadStory(exampleStory());pause()")
        self.assertEqual(self.page.locator('#clock').text_content(), '9:41')
        result = self.page.evaluate("""() => {
            const invalid=[null,[],{time:'25:00'},{battery:0},{signalStrength:5},{wifiStrength:4},{theme:'green'}];
            let rejected=0;for(const status of invalid){const raw=exampleStory();raw.nodes[0].status=status;try{validateStory(raw);}catch(_){rejected++;}}
            return rejected;
        }""")
        self.assertEqual(result, 7)

    def test_return_dividers_follow_played_visits_and_reset_when_seeking(self):
        self.page.evaluate("""() => {
            const raw=exampleStory();raw.startNodeId='return-0';
            const records=[['sarah','text','user'],['sarah','text','user'],['max','text','user'],
                ['sarah','timestamp',null],['sarah','text','sarah'],['max','text','user'],['sarah','text','sarah']];
            raw.nodes=records.map(([chatId,type,sender],i)=>({id:'return-'+i,type:'message',chatId,
                message:{id:'message-'+i,type,sender,content:type==='timestamp'?'Later':'Message '+i},
                next:i===records.length-1?null:'return-'+(i+1)}));loadStory(raw);pause();seekStory('return-6');
        }""")
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 2)
        self.assertTrue(self.page.locator('.new-messages-divider').first.evaluate("node=>node.nextElementSibling.matches('.timestamp')"))
        self.assertFalse(self.page.locator('.new-messages-divider + .message').last.evaluate("node=>node.classList.contains('sequence')"))
        for _ in range(2):
            self.page.locator('#chat-back').click()
            self.page.locator('[data-open-chat="sarah"]').click()
            self.assertEqual(self.page.locator('.new-messages-divider').count(), 2)
        self.page.evaluate("seekStory('return-4');pause();openChat('sarah')")
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 1)
        self.page.evaluate("seekStory('return-1')")
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 0)
        self.assertEqual(self.page.evaluate("engine.returnMarkers.size"), 0)
        self.page.evaluate("seekStory('return-6')")
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 2)
        self.page.evaluate("loadStory(exampleStory());pause()")
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 0)
        self.assertEqual(self.page.evaluate("engine.returnMarkers.size"), 0)

    def load_long_chat(self, page=None):
        (page or self.page).evaluate("""() => {
            const raw=exampleStory();raw.startNodeId='drag-0';raw.nodes=Array.from({length:80},(_,i)=>({
                id:'drag-'+i,type:'message',chatId:'sarah',message:{id:'m-'+i,type:'text',sender:'user',
                    content:'Message '+i+'. This longer conversation has enough text to scroll through.'},
                next:i===79?null:'drag-'+(i+1)}));loadStory(raw);pause();seekStory('drag-59');
        }""")

    def test_drag_phone_bubbles_scrolls_without_selection_and_controls_still_work(self):
        self.load_long_chat()
        bubble = self.page.locator(".bubble").last.bounding_box()
        x, y = bubble["x"] + bubble["width"] / 2, bubble["y"] + bubble["height"] / 2
        before = self.page.evaluate("$('chat-scroll').scrollTop")
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x, y + 10)
        self.assertTrue(self.page.evaluate("document.body.classList.contains('scroll-panning')"))
        self.page.evaluate("render()")
        self.assertAlmostEqual(self.page.evaluate("$('chat-scroll').scrollTop"), before - 10, delta=1)
        # Pointer capture keeps scrolling when the mouse leaves the phone.
        self.page.mouse.move(x, y + 180, steps=8)
        self.page.mouse.up()
        self.assertAlmostEqual(self.page.evaluate("$('chat-scroll').scrollTop"), before - 180, delta=1)
        self.assertTrue(self.page.evaluate("scrollPan===null&&!document.body.classList.contains('scroll-panning')"))
        self.assertEqual(self.page.evaluate("getSelection().toString()"), "")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 60)
        self.page.locator("#controls-toggle").click()
        self.assertTrue(self.page.locator("#player-controls").is_visible())
        self.page.locator("#playback-paused").uncheck()
        self.page.locator("#controls-close").click()
        self.page.locator("#send-button").click()
        self.assertEqual(self.page.evaluate("engine.messageCount"), 61)

    def test_drag_timeline_cards_pans_in_both_axes_without_seeking(self):
        self.load_long_chat()
        self.open_timeline()
        before = self.page.evaluate("$('timeline-viewport').scrollTop")
        card = self.page.locator(".timeline-node.current").bounding_box()
        x, y = card["x"] + card["width"] / 2, card["y"] + card["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x, y - 200, steps=10)
        self.page.mouse.up()
        self.assertAlmostEqual(self.page.evaluate("$('timeline-viewport').scrollTop"), before + 200, delta=1)
        self.assertEqual(self.page.evaluate("engine.visitedNodeIds.at(-1)"), "drag-59")
        self.assertFalse(self.page.evaluate("timelineFollow"))
        self.assertEqual(self.page.evaluate("getSelection().toString()"), "")
        self.page.locator("#timeline-now").click()
        self.page.evaluate("zoomTimeline(2)")
        before = self.page.evaluate("({x:$('timeline-viewport').scrollLeft,y:$('timeline-viewport').scrollTop})")
        card = self.page.locator(".timeline-node.current").bounding_box()
        x, y = card["x"] + card["width"] / 2, card["y"] + card["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x - 70, y - 90, steps=8)
        self.page.mouse.up()
        self.assertAlmostEqual(self.page.evaluate("$('timeline-viewport').scrollLeft"), before["x"] + 70, delta=1)
        self.assertAlmostEqual(self.page.evaluate("$('timeline-viewport').scrollTop"), before["y"] + 90, delta=1)
        self.assertEqual(self.page.evaluate("engine.messageCount"), 60)
        self.page.evaluate("selectTimelineMoment('drag-62',{center:true})")
        self.page.locator('.timeline-node[data-timeline-index="63"]').click()
        self.assertEqual(self.page.evaluate("engine.visitedNodeIds.at(-1)"), "drag-62")
        self.assertFalse(self.page.evaluate("playing"))

    def test_drag_cancellation_releases_capture_and_keeps_timeline_available(self):
        self.load_long_chat()
        self.open_timeline()
        for cancellation in ["escape", "blur", "pointercancel", "lostcapture"]:
            with self.subTest(cancellation=cancellation):
                bounds = self.page.locator("#timeline-viewport").bounding_box()
                x, y = bounds["x"] + 15, bounds["y"] + 200
                self.page.mouse.move(x, y)
                self.page.mouse.down()
                self.page.mouse.move(x, y - 40, steps=3)
                self.assertTrue(self.page.evaluate("scrollPan?.moved"))
                if cancellation == "escape":
                    self.page.keyboard.press("Escape")
                elif cancellation == "blur":
                    self.page.evaluate("window.dispatchEvent(new Event('blur'))")
                elif cancellation == "pointercancel":
                    pointer_id = self.page.evaluate("scrollPan.pointerId")
                    self.page.locator("#timeline-viewport").dispatch_event("pointercancel", {"pointerId": pointer_id})
                else:
                    self.page.evaluate("scrollPan.viewport.releasePointerCapture(scrollPan.pointerId)")
                    self.page.mouse.move(x, y - 41)
                self.page.wait_for_function("scrollPan===null")
                self.assertFalse(self.page.evaluate("document.body.classList.contains('scroll-panning')"))
                self.page.mouse.up()
                self.assertTrue(self.page.locator("#timeline-panel").is_visible())
                self.assertEqual(self.page.evaluate("engine.messageCount"), 60)
        self.page.locator("#timeline-now").click()
        self.assertTrue(self.page.evaluate("timelineFollow"))

    def test_drag_chat_list_scrolls_without_opening_a_row(self):
        self.page.evaluate("""() => {
            const raw=exampleStory(),chat=raw.chats[0];
            raw.chats=Array.from({length:20},(_,i)=>({...chat,id:'chat-'+i,title:'Chat '+i}));
            raw.startNodeId='row-0';raw.nodes=raw.chats.map((chat,i)=>({id:'row-'+i,type:'message',chatId:chat.id,
                message:{id:'m-'+i,type:'text',sender:'user',content:'A message in this chat'},next:i===19?null:'row-'+(i+1)}));
            loadStory(raw);pause();seekStory('row-19');
        }""")
        self.page.locator("#chat-back").click()
        row = self.page.locator(".chat-list-row").first.bounding_box()
        x, y = row["x"] + row["width"] / 2, row["y"] + row["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x, y - 150, steps=8)
        self.page.mouse.up()
        self.assertTrue(self.page.locator("#chat-overview").is_visible())
        self.assertAlmostEqual(self.page.evaluate("$('chat-list').scrollTop"), 150, delta=1)
        name = self.page.locator(".chat-list-row").nth(3).locator(".chat-list-name").text_content()
        self.page.locator(".chat-list-row").nth(3).click()
        self.assertFalse(self.page.locator("#chat-overview").is_visible())
        self.assertEqual(self.page.locator("#chat-name").text_content(), name)

    def test_native_touch_swipes_scroll_phone_and_timeline_without_jumping(self):
        context = self.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                           has_touch=True, offline=True, reduced_motion="reduce")
        try:
            page = context.new_page()
            page.set_default_timeout(5000)
            page.on("pageerror", lambda error: self.errors.append(str(error)))
            page.goto(PLAYER)
            self.load_long_chat(page)
            page.locator("#controls-toggle").tap()
            page.locator("#timeline-button").tap()
            session = context.new_cdp_session(page)

            def swipe(selector, distance):
                bounds = page.locator(selector).bounding_box()
                x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + 230
                session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
                self.assertTrue(page.evaluate("scrollPan===null"))
                for step in range(1, 9):
                    session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y + distance * step / 8}]})
                    page.wait_for_timeout(20)
                session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

            before = page.evaluate("$('timeline-viewport').scrollTop")
            swipe("#timeline-viewport", -140)
            page.wait_for_function("before=>$('timeline-viewport').scrollTop>before+50", arg=before)
            self.assertEqual(page.evaluate("engine.messageCount"), 60)
            page.locator("#timeline-close").tap()
            page.locator("#chat-scroll").scroll_into_view_if_needed()
            before = page.evaluate("$('chat-scroll').scrollTop")
            swipe("#chat-scroll", 140)
            page.wait_for_function("before=>$('chat-scroll').scrollTop<before-50", arg=before)
            self.assertEqual(page.evaluate("engine.messageCount"), 60)
            self.assertFalse(page.evaluate("document.body.classList.contains('scroll-panning')"))
        finally:
            context.close()

    def test_every_seek_matches_link_order_and_invalid_targets_do_not_mutate(self):
        result = self.page.evaluate("""() => {
            const raw=exampleStory();raw.nodes.reverse();
            raw.nodes.push({id:'unreachable',type:'end'});
            const story=validateStory(raw), sought=new PlaybackEngine(story), normal=new PlaybackEngine(story);
            const snapshot=e=>JSON.stringify({node:e.nodeId,path:e.visitedNodeIds,histories:[...e.histories],
                returns:[...e.returnMarkers].map(([id,markers])=>[id,[...markers]]),lastMessageChatId:e.lastMessageChatId,statuses:[...e.chatStatuses],
                chats:e.visitedChatIds,active:e.activeChatId,count:e.messageCount,part:e.part,finished:e.finished});
            const original=JSON.stringify(raw);let checked=0;
            for(const node of sought.route) {
                normal.advance();sought.seekTo(node.id);
                if(snapshot(normal)!==snapshot(sought))throw Error('Wrong prefix at '+node.id);
                checked++;
            }
            for(const id of ['missing','unreachable']) {
                const before=snapshot(sought);let rejected=false;
                try{sought.seekTo(id);}catch(_){rejected=true;}
                if(!rejected||snapshot(sought)!==before)throw Error('Invalid seek changed state');
            }
            sought.seekTo(null);
            return {checked,empty:sought.histories.size===0&&sought.messageCount===0,
                unchanged:JSON.stringify(raw)===original,routeOnly:!sought.routeIndex.has('unreachable')};
        }""")
        self.assertEqual(result, {"checked": 18, "empty": True, "unchanged": True, "routeOnly": True})

    def test_cards_jump_without_closing_panel_and_preserve_manual_pause(self):
        self.page.locator("#phone-example-button").click()
        self.page.locator("#controls-toggle").click()
        self.page.locator("#playback-paused").check()
        self.page.locator("#timeline-button").click()
        before = self.page.evaluate("engine.messageCount")
        index = self.page.evaluate("timelineModel.moments.findIndex(m=>m.node?.type==='message'&&m.node.chatId==='group')")
        self.page.evaluate("(index)=>selectTimelineMoment(timelineModel.moments[index].id,{center:true})", index)
        target = self.page.evaluate("timelineSelection")
        self.assertEqual(self.page.evaluate("engine.messageCount"), before)
        self.assertIn("Movie night", self.page.locator(f'.timeline-node[data-timeline-index="{index}"]').text_content())
        self.page.locator(f'.timeline-node[data-timeline-index="{index}"]').click()
        self.assertTrue(self.page.locator("#timeline-panel").is_visible())
        self.assertEqual(self.page.evaluate("engine.visitedNodeIds.at(-1)"), target)
        self.assertTrue(self.page.evaluate("!playing && !pendingChatId && unreadCounts.size===0"))
        self.assertEqual(self.page.locator("#chat-name").text_content(), "Movie night")
        self.page.evaluate("selectTimelineMoment('step-2',{center:true})")
        self.page.locator('.timeline-node[data-timeline-index="3"]').click()
        self.assertEqual(self.page.evaluate("engine.visitedNodeIds.at(-1)"), "step-2")
        self.assertFalse(self.page.evaluate("playing"))

    def test_seeking_cancels_old_reply_and_restores_send_turn(self):
        self.page.locator("#phone-example-button").click()
        self.page.wait_for_function("typingSender !== null")
        self.assertTrue(self.page.evaluate("seekStory('step-3')"))
        self.page.wait_for_function("ownerWaiting")
        self.page.wait_for_timeout(1800)
        self.assertEqual(self.page.evaluate("engine.messageCount"), 3)
        self.assertEqual(self.page.evaluate("engine.current().id"), "step-5")
        self.assertEqual(self.page.locator("#scripted-message").input_value(), "Movie night with Sarah?")
        self.assertTrue(self.page.evaluate("playing && pendingChatId===null"))

    def test_backward_seek_clears_unread_notifications_and_later_chats(self):
        self.page.evaluate("""() => {
            const raw=exampleStory();raw.startNodeId='a';raw.nodes=[
                {id:'a',type:'message',chatId:'sarah',message:{id:'a',type:'text',sender:'user',content:'Hello'},next:'b'},
                {id:'b',type:'chat',chatId:'max',next:'c'},
                {id:'c',type:'message',chatId:'max',message:{id:'c',type:'text',sender:'max',content:'Another chat'},next:null}
            ];$('speed').value='2';loadStory(raw);
        }""")
        self.page.locator("#send-button").click()
        self.page.wait_for_function("pendingChatId==='max'")
        self.assertTrue(self.page.locator("#chat-notification").is_visible())
        self.page.evaluate("seekStory(null)")
        self.assertTrue(self.page.evaluate("ownerWaiting && pendingChatId===null && unreadCounts.size===0"))
        self.assertEqual(self.page.evaluate("engine.messageCount"), 0)
        self.assertTrue(self.page.evaluate("[...engine.histories.values()].every(messages=>messages.length===0)"))
        self.assertFalse(self.page.locator("#chat-notification").is_visible())
        self.page.locator("#chat-back").click()
        self.assertEqual(self.page.locator(".chat-list-row").count(), 1)

    def test_seeking_back_from_completion_continues_without_start_or_resume(self):
        self.page.locator("#phone-example-button").click()
        self.page.evaluate("seekStory('step-17')")
        self.assertTrue(self.page.evaluate("engine.finished && !playing"))
        self.assertEqual(self.page.locator("#phone-play-button").text_content(), "Replay")
        self.page.evaluate("seekStory('step-2')")
        self.assertTrue(self.page.evaluate("playing && ownerWaiting && !engine.finished"))
        self.assertFalse(self.page.locator("#phone-play-button").is_visible())
        self.assertEqual(self.page.evaluate("engine.messageCount"), 2)

    def test_timeline_keyboard_does_not_send_background_messages(self):
        self.page.evaluate("""() => {
            const raw=exampleStory();raw.startNodeId='first-0';raw.nodes=Array.from({length:30},(_,i)=>({
                id:'first-'+i,type:'message',chatId:'sarah',message:{id:'first-'+i,type:'text',sender:'user',content:'Wait for Send'},
                next:i===29?null:'first-'+(i+1)}));loadStory(raw);
        }""")
        self.open_timeline()
        self.page.locator("#timeline-viewport").focus()
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 0)
        self.page.keyboard.press("ArrowDown")
        self.assertEqual(self.page.evaluate("timelineSelection"), "first-0")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 0)
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 1)
        self.page.evaluate("seekStory(null)")
        self.page.keyboard.press("Home")
        self.page.evaluate("$('timeline-viewport').scrollTop=$('timeline-viewport').scrollHeight")
        self.page.wait_for_function("document.activeElement===$('timeline-viewport')")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 0)

    def test_long_timeline_only_renders_visible_markers(self):
        self.page.evaluate("""() => {
            const raw=exampleStory();raw.startNodeId='node-0';raw.nodes=Array.from({length:2000},(_,i)=>({
                id:'node-'+i,type:'message',chatId:'sarah',message:{id:'m-'+i,type:'text',sender:'sarah',content:'Message '+i},
                next:i===1999?null:'node-'+(i+1)}));loadStory(raw);pause();
        }""")
        self.open_timeline()
        self.assertEqual(self.page.evaluate("timelineModel.moments.length"), 2001)
        self.assertLess(self.page.locator(".timeline-node").count(), 30)
        self.page.evaluate("selectTimelineMoment('node-1899',{center:true})")
        self.assertIn("Message 1899", self.page.locator('.timeline-node[data-timeline-index="1900"]').text_content())
        self.assertGreater(self.page.evaluate("$('timeline-viewport').scrollTop"), 1000)
        self.assertLess(self.page.locator(".timeline-node").count(), 30)
        self.assertEqual(self.page.evaluate("engine.messageCount"), 0)
        self.page.locator('.timeline-node[data-timeline-index="1900"]').click()
        self.assertEqual(self.page.evaluate("engine.messageCount"), 1900)
        self.assertEqual(self.page.evaluate("engine.current().id"), "node-1900")
        self.page.evaluate("zoomTimeline(.15)")
        self.assertEqual(self.page.locator("#timeline-viewport").get_attribute("data-detail"), "chats")
        self.assertEqual(self.page.evaluate("timelineModel.segments.length"), 1)
        self.assertEqual(self.page.evaluate("timelineModel.segments[0].count"), 2000)
        self.assertLess(self.page.evaluate("timelineView.height"), 250)
        self.assertLess(self.page.locator(".timeline-node").count(), 7)
        self.assertLess(self.page.locator("#timeline-links path").count(), 6)
        self.assertEqual(self.page.locator(".timeline-node.current").get_attribute("data-timeline-index"), "1900")
        self.page.locator('.timeline-node[data-detail="segment"]').click()
        self.assertEqual(self.page.locator("#timeline-viewport").get_attribute("data-detail"), "cards")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 1900)

    def test_wheel_zoom_anchors_cursor_across_detail_levels_and_near_beginning(self):
        self.load_long_chat()
        self.open_timeline()
        self.page.evaluate("$('timeline-viewport').scrollLeft+=70;$('timeline-viewport').scrollTop+=110")
        self.page.evaluate("()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
        state = self.page.evaluate("JSON.stringify(engine.visitedNodeIds)")
        target = self.page.locator(".timeline-node.current")
        for step in range(9):
            before = target.bounding_box()
            x, y = before["x"] + before["width"] / 2, before["y"] + before["height"] / 2
            zoom = self.page.evaluate("timelineZoom")
            self.page.mouse.move(x, y)
            self.page.mouse.wheel(0, 100)
            self.page.wait_for_function("previous=>timelineZoom<previous", arg=zoom)
            self.page.evaluate("()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
            after = target.bounding_box()
            self.assertAlmostEqual(after["x"] + after["width"] / 2, x, delta=1.5)
            self.assertAlmostEqual(after["y"] + after["height"] / 2, y, delta=1.5)
            if step in [4, 8]:
                name = "dots" if step == 4 else "chats"
                self.page.screenshot(path=str(Path(tempfile.gettempdir()) / f"chat-player-map-{name}.png"))
        self.assertEqual(self.page.locator("#timeline-viewport").get_attribute("data-detail"), "chats")
        self.assertEqual(self.page.evaluate("JSON.stringify(engine.visitedNodeIds)"), state)
        self.page.evaluate("loadStory(exampleStory());pause();zoomTimeline(1);selectTimelineMoment(null,{center:true})")
        self.page.evaluate("$('timeline-viewport').scrollLeft+=60;$('timeline-viewport').scrollTop+=100")
        self.page.evaluate("()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))")
        target = self.page.locator('.timeline-node[data-kind="start"]')
        before = target.bounding_box()
        x, y = before["x"] + before["width"] / 2, before["y"] + before["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.wheel(0, -150)
        self.page.wait_for_function("timelineZoom>1")
        after = target.bounding_box()
        self.assertAlmostEqual(after["x"] + after["width"] / 2, x, delta=1.5)
        self.assertAlmostEqual(after["y"] + after["height"] / 2, y, delta=1.5)

    def test_dot_markers_keep_message_clicks_and_keyboard_navigation(self):
        self.load_long_chat()
        self.open_timeline()
        self.page.evaluate("zoomTimeline(.5);selectTimelineMoment('drag-62',{center:true})")
        self.assertEqual(self.page.locator("#timeline-viewport").get_attribute("data-detail"), "dots")
        target = self.page.locator('.timeline-node[data-timeline-index="63"]')
        self.assertEqual(target.get_attribute("data-detail"), "dot")
        self.assertEqual(target.text_content(), "")
        self.assertIn("Message 62", target.get_attribute("title"))
        target.click()
        self.assertEqual(self.page.evaluate("engine.messageCount"), 63)
        self.assertFalse(self.page.evaluate("playing"))
        self.page.keyboard.press("ArrowDown")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("engine.messageCount"), 64)

    def test_overview_keeps_chat_returns_separate_and_drills_in_without_seeking(self):
        self.page.locator("#phone-example-button").click()
        self.page.evaluate("pause();seekStory('step-11')")
        self.open_timeline()
        self.page.evaluate("zoomTimeline(.15)")
        self.assertEqual(self.page.evaluate("timelineModel.segments.map(s=>[s.chatId,s.count])"),
                         [["sarah", 3], ["max", 2], ["friends", 2], ["group", 4], ["sarah", 1]])
        self.assertEqual(self.page.locator('.timeline-node[data-detail="segment"]').count(), 5)
        self.assertTrue(self.page.locator(".timeline-node.current").is_visible())
        self.page.screenshot(path=str(Path(tempfile.gettempdir()) / "chat-player-map-overview.png"))
        state = self.page.evaluate("JSON.stringify(engine.visitedNodeIds)")
        line = self.page.locator('.timeline-segment[data-timeline-segment="step-7"]')
        bounds = line.bounding_box()
        x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x + 30, y + 20, steps=4)
        self.page.mouse.up()
        self.assertEqual(self.page.locator("#timeline-viewport").get_attribute("data-detail"), "chats")
        self.assertEqual(self.page.evaluate("JSON.stringify(engine.visitedNodeIds)"), state)
        self.page.locator('.timeline-node[data-timeline-segment="step-7"]').press("Enter")
        self.assertEqual(self.page.locator("#timeline-viewport").get_attribute("data-detail"), "cards")
        self.assertEqual(self.page.evaluate("timelineSelection"), "step-7")
        self.assertEqual(self.page.evaluate("JSON.stringify(engine.visitedNodeIds)"), state)

    def test_compaction_preserves_forks_merges_and_readable_branch_labels(self):
        result = self.page.evaluate("""() => {
            const items=['root','choice','left','right','left-end','right-end','merge'].map(id=>({
                id,title:id,kind:id==='choice'?'choice':id==='root'?'chat':'text',
                node:{type:id==='choice'?'choice':id==='root'?'chat':'message',chatId:'same-chat'}}));
            const links=new Map([['root',['choice']],['choice',['left','right']],['left',['left-end']],
                ['right',['right-end']],['left-end',['merge']],['right-end',['merge']]]);
            const graph=layoutTimelineGraph(items,links);Object.assign(graph,groupTimelineVisits(graph));
            const view=projectTimeline(graph,.1),left=view.byId.get('left'),right=view.byId.get('right');
            return {segments:graph.segments.map(s=>s.moments.map(m=>m.id)),
                labelsApart:left.x+left.w/2<right.x-right.w/2,choice:view.byId.get('choice').display,
                mergeBelow:view.byId.get('merge').y>view.byId.get('left-end').y};
        }""")
        self.assertEqual(result, {"segments": [["root"], ["left", "left-end"], ["right", "right-end"], ["merge"]],
                                  "labelsApart": True, "choice": "label", "mergeBelow": True})

    def test_compact_map_keeps_shrinking_and_choices_overview_collapses_long_runs(self):
        self.load_long_chat()
        result = self.page.evaluate("""() => {
            const model=buildTimelineModel(engine),levels=[.24,.15,.1,.08,.06,.04,.02];
            const views=levels.map(zoom=>projectTimeline(model,zoom));
            const overview=views.at(-1);
            return {heights:views.map(view=>view.height),
                details:views.map(view=>view.detail),links:overview.edges.length,
                visible:overview.moments.filter(moment=>moment.display!=='hidden').map(moment=>moment.source.kind),
                increasing:views.every(view=>view.ys.every((y,index)=>!index||y>view.ys[index-1])),
                cardWidth:projectTimeline(model,1).moments.find(moment=>moment.source.kind==='text').w};
        }""")
        self.assertTrue(all(first > second for first, second in zip(result['heights'], result['heights'][1:])))
        self.assertEqual(result['details'], ['chats'] * 4 + ['choices'] * 3)
        self.assertEqual(result['links'], 1)
        self.assertEqual(result['visible'], ['start', 'text'])
        self.assertTrue(result['increasing'])
        self.assertLessEqual(result['cardWidth'], 180)

    def test_wheel_over_phone_still_scrolls_without_zooming_timeline(self):
        self.load_long_chat()
        self.open_timeline()
        viewport = self.page.locator("#chat-scroll").bounding_box()
        before = self.page.evaluate("$('chat-scroll').scrollTop")
        self.page.mouse.move(viewport["x"] + viewport["width"] / 2, viewport["y"] + viewport["height"] / 2)
        self.page.mouse.wheel(0, -150)
        self.page.wait_for_function("before=>$('chat-scroll').scrollTop<before-50", arg=before)
        self.assertEqual(self.page.evaluate("timelineZoom"), 1)

    def test_loading_another_story_clears_timeline_and_rejects_old_targets(self):
        self.page.locator("#phone-example-button").click()
        self.open_timeline()
        self.page.evaluate("""() => {
            const raw=exampleStory();raw.story.id='other';raw.nodes.forEach(node=>{node.id='new-'+node.id;if(node.next)node.next='new-'+node.next;});
            raw.startNodeId='new-'+raw.startNodeId;loadStory(raw);
        }""")
        self.assertTrue(self.page.locator("#timeline-panel").is_visible())
        state = self.page.evaluate("JSON.stringify({node:engine.nodeId,path:engine.visitedNodeIds,timer:timerGeneration})")
        self.assertFalse(self.page.evaluate("seekStory('step-2')"))
        self.assertEqual(self.page.evaluate("JSON.stringify({node:engine.nodeId,path:engine.visitedNodeIds,timer:timerGeneration})"), state)
        self.assertTrue(self.page.evaluate("timelineModel.moments.every(m=>m.id===null||m.id.startsWith('new-'))"))

    def test_timeline_sits_beside_interactive_phone_and_closes_with_escape(self):
        self.assertFalse(self.page.locator("#timeline-panel").is_visible())
        self.page.locator("#phone-example-button").click()
        self.page.evaluate("pause();seekStory('step-11')")
        self.open_timeline()
        phone = self.page.locator("#phone").bounding_box()
        panel = self.page.locator("#timeline-panel").bounding_box()
        self.assertGreater(panel["x"], phone["x"] + phone["width"])
        self.assertAlmostEqual(panel["y"], phone["y"], delta=1)
        self.assertEqual(self.page.locator("dialog[open]").count(), 0)
        positions = self.page.evaluate("timelineModel.moments.map(m=>({x:m.x,y:m.y}))")
        self.assertTrue(all(a["y"] < b["y"] for a, b in zip(positions, positions[1:])))
        self.assertEqual(len({p["x"] for p in positions}), 1)
        self.page.locator("#chat-back").click()
        self.assertTrue(self.page.locator("#chat-overview").is_visible())
        self.assertTrue(self.page.locator("#timeline-panel").is_visible())
        self.page.locator("#overview-current").click()
        self.page.screenshot(path=str(Path(tempfile.gettempdir()) / "chat-player-timeline-vertical-desktop.png"))
        self.page.keyboard.press("Escape")
        self.assertFalse(self.page.locator("#timeline-panel").is_visible())
        self.assertEqual(self.page.locator("#timeline-button").get_attribute("aria-expanded"), "false")

    def test_zoom_preserves_position_and_does_not_change_playback(self):
        self.page.locator("#phone-example-button").click()
        self.page.evaluate("pause()")
        self.open_timeline()
        self.page.evaluate("selectTimelineMoment('step-11',{center:true})")
        state = self.page.evaluate("JSON.stringify(engine.visitedNodeIds)")
        target = self.page.locator('.timeline-node[data-timeline-index="12"]')
        before = target.bounding_box()
        self.page.locator("#timeline-zoom-in").click()
        self.assertEqual(self.page.locator("#timeline-zoom-reset").text_content(), "125%")
        after = target.bounding_box()
        self.assertAlmostEqual(after["x"] + after["width"] / 2, before["x"] + before["width"] / 2, delta=1)
        self.assertAlmostEqual(after["y"] + after["height"] / 2, before["y"] + before["height"] / 2, delta=1)
        self.page.locator("#timeline-zoom-out").click()
        self.assertEqual(self.page.evaluate("timelineZoom"), 1)
        self.page.locator("#timeline-viewport").dispatch_event("wheel", {"deltaY": -100, "ctrlKey": True, "clientX": 950, "clientY": 400})
        self.assertGreater(self.page.evaluate("timelineZoom"), 1)
        self.page.locator("#timeline-zoom-reset").click()
        self.assertEqual(self.page.evaluate("timelineZoom"), 1)
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth===innerWidth"))
        self.page.evaluate("zoomTimeline(.01)")
        self.assertEqual(self.page.locator("#timeline-zoom-reset").text_content(), "2%")
        self.assertTrue(self.page.locator("#timeline-zoom-out").is_disabled())
        self.assertLess(self.page.locator(".timeline-node").count(), 35)
        self.page.evaluate("zoomTimeline(10)")
        self.assertEqual(self.page.locator("#timeline-zoom-reset").text_content(), "200%")
        self.assertTrue(self.page.locator("#timeline-zoom-in").is_disabled())
        self.assertEqual(self.page.evaluate("JSON.stringify(engine.visitedNodeIds)"), state)
        self.page.locator("#timeline-now").click()
        self.assertTrue(self.page.evaluate("timelineFollow && timelineSelection===currentTimelineId()"))

    def test_graph_layout_places_forks_and_merges_without_enabling_choices(self):
        result = self.page.evaluate("""() => {
            const items=['merge','right-end','left-end','right','left','choice','root'].map(id=>({id,kind:'text'}));
            const original=JSON.stringify(items);
            const links=new Map([['root',['choice']],['choice',['left','right']],['left',['left-end']],
                ['right',['right-end']],['left-end',['merge']],['right-end',['merge']]]);
            const model=layoutTimelineGraph(items,links),m=id=>model.byId.get(id);
            let loops=false,missing=false,choices=false;
            try{layoutTimelineGraph(items,new Map([...links,['merge',['root']]]));}catch(_){loops=true;}
            try{layoutTimelineGraph(items,new Map([...links,['merge',['unknown']]]));}catch(_){missing=true;}
            const raw=exampleStory();raw.nodes[0].type='choice';try{validateStory(raw);}catch(_){choices=true;}
            return {split:m('left').y===m('right').y&&m('left').x+m('left').w/2<m('right').x-m('right').w/2,
                lanes:m('left').x===m('left-end').x&&m('right').x===m('right-end').x,
                merge:m('merge').y>m('left-end').y&&m('merge').x===(m('left').x+m('right').x)/2,
                order:m('root').y<m('choice').y&&m('choice').y<m('left').y,
                unchanged:JSON.stringify(items)===original,edges:model.edges.length,loops,missing,choices};
        }""")
        self.assertEqual(result, {"split": True, "lanes": True, "merge": True, "order": True,
                                  "unchanged": True, "edges": 7, "loops": True, "missing": True, "choices": True})

    def test_touch_timeline_fits_small_screens_and_jumps(self):
        for width, height in [(390, 844), (320, 568)]:
            with self.subTest(viewport=(width, height)):
                context = self.browser.new_context(viewport={"width": width, "height": height}, is_mobile=True,
                                                   has_touch=True, offline=True, reduced_motion="reduce")
                try:
                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.on("pageerror", lambda error: self.errors.append(str(error)))
                    page.goto(PLAYER)
                    page.locator("#phone-example-button").tap()
                    page.locator("#controls-toggle").tap()
                    page.locator("#playback-paused").check()
                    page.locator("#timeline-button").tap()
                    index = page.evaluate("timelineModel.moments.findIndex(m=>m.node?.type==='message'&&m.node.chatId==='group')")
                    page.evaluate("(index)=>selectTimelineMoment(timelineModel.moments[index].id,{center:true})", index)
                    bounds = page.locator("#timeline-panel").bounding_box()
                    phone = page.locator("#phone").bounding_box()
                    self.assertGreater(bounds["y"], phone["y"] + phone["height"])
                    self.assertGreaterEqual(bounds["x"], 0)
                    self.assertLessEqual(bounds["x"] + bounds["width"], width + 1)
                    self.assertLessEqual(bounds["height"], height - 23)
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth===innerWidth"))
                    if width == 390:
                        page.screenshot(path=str(Path(tempfile.gettempdir()) / "chat-player-timeline-vertical-mobile.png"), full_page=True)
                    page.locator(f'.timeline-node[data-timeline-index="{index}"]').tap()
                    self.assertTrue(page.locator("#timeline-panel").is_visible())
                    self.assertEqual(page.locator("#chat-name").text_content(), "Movie night")
                    self.assertFalse(page.evaluate("playing"))
                    page.locator("#timeline-zoom-out").tap()
                    self.assertEqual(page.locator("#timeline-zoom-reset").text_content(), "80%")
                    page.locator("#timeline-now").tap()
                    self.assertEqual(page.evaluate("timelineSelection"), page.evaluate("engine.visitedNodeIds.at(-1)"))
                    count = page.evaluate("engine.messageCount")
                    page.evaluate("zoomTimeline(.15)")
                    page.locator('.timeline-node[data-timeline-segment="step-10"]').tap()
                    self.assertEqual(page.locator("#timeline-viewport").get_attribute("data-detail"), "cards")
                    self.assertEqual(page.evaluate("engine.messageCount"), count)
                    page.locator("#timeline-close").tap()
                    self.assertFalse(page.locator("#timeline-panel").is_visible())
                finally:
                    context.close()


if __name__ == "__main__":
    unittest.main()
