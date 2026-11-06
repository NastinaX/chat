"""Offline regression checks. Requires Python, Playwright, and its Chromium browser."""
import json
import tempfile
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as error:
    raise unittest.SkipTest("Install Playwright and its Chromium browser to run these checks.") from error


PLAYER = (Path(__file__).resolve().parents[1] / "player.html").as_uri()
LINEAR_STORY = json.loads((Path(__file__).parent / "fixtures/linear-player.json").read_text(encoding="utf-8"))
LINEAR_STORY_SCRIPT = "window.linearExampleStory = () => (" + json.dumps(LINEAR_STORY) + ");"


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
        self.context.add_init_script(LINEAR_STORY_SCRIPT)
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
        self.page.evaluate("loadStory(linearExampleStory())")
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
            const raw=linearExampleStory();raw.nodes[0].status={time:'09:00',battery:90};
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
        self.page.evaluate("loadStory(linearExampleStory());pause()")
        self.assertEqual(self.page.locator('#clock').text_content(), '9:41')
        result = self.page.evaluate("""() => {
            const invalid=[null,[],{time:'25:00'},{battery:0},{signalStrength:5},{wifiStrength:4},{theme:'green'}];
            let rejected=0;for(const status of invalid){const raw=linearExampleStory();raw.nodes[0].status=status;try{validateStory(raw);}catch(_){rejected++;}}
            return rejected;
        }""")
        self.assertEqual(result, 7)

    def test_return_dividers_follow_played_visits_and_reset_when_seeking(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='return-0';
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
        self.page.evaluate("loadStory(linearExampleStory());pause()")
        self.assertEqual(self.page.locator('.new-messages-divider').count(), 0)
        self.assertEqual(self.page.evaluate("engine.returnMarkers.size"), 0)

    def load_long_chat(self, page=None):
        (page or self.page).evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='drag-0';raw.nodes=Array.from({length:80},(_,i)=>({
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
            const raw=linearExampleStory(),chat=raw.chats[0];
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
            context.add_init_script(LINEAR_STORY_SCRIPT)
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
            const raw=linearExampleStory();raw.nodes.reverse();
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
        self.page.evaluate("loadStory(linearExampleStory())")
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

    def test_seeking_cancels_old_reply_and_prompts_for_next_chat(self):
        self.page.evaluate("loadStory(linearExampleStory())")
        self.page.wait_for_function("typingSender !== null")
        self.assertTrue(self.page.evaluate("seekStory('step-3')"))
        self.page.wait_for_function("pendingChatId==='max'")
        self.assertEqual(self.page.evaluate('viewedChatId'), 'sarah')
        self.assertEqual(self.page.evaluate('pendingChatKind'), 'reply')
        self.assertTrue(self.page.locator('#phone-play-button').is_hidden())
        self.page.locator('#chat-notification').click()
        self.page.wait_for_function("ownerWaiting")
        self.page.wait_for_timeout(1800)
        self.assertEqual(self.page.evaluate("engine.messageCount"), 3)
        self.assertEqual(self.page.evaluate("engine.current().id"), "step-5")
        self.assertEqual(self.page.locator("#scripted-message").input_value(), "Movie night with Sarah?")
        self.assertTrue(self.page.evaluate("playing && pendingChatId===null"))

    def test_outgoing_chat_prompts_before_timestamp_and_sends_only_after_opening(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='opening';
            const message=(id,chatId,type,sender,content,next)=>({id,type:'message',chatId,
                message:{id:'m-'+id,type,sender,content},next});
            raw.nodes=[message('opening','sarah','text','user','See you soon.','switch'),
                {id:'switch',type:'chat',chatId:'friends',next:'time'},
                message('time','friends','timestamp',null,'Later that evening','reply'),
                message('reply','friends','text','sarah','Are you bringing snacks?','second'),
                message('second','friends','text','sarah','And drinks?','end'),{id:'end',type:'end'}];
            const originalSchedule=schedule;schedule=(delay,callback)=>originalSchedule(Math.min(delay,20),callback);
            loadStory(raw);
        }""")
        self.page.locator('#send-button').click()
        self.page.wait_for_function("pendingChatId==='friends'")
        self.assertEqual(self.page.evaluate('pendingChatKind'), 'reply')
        self.assertEqual(self.page.evaluate('viewedChatId'), 'sarah')
        self.assertEqual(self.page.evaluate('engine.current().id'), 'time')
        self.assertEqual(self.page.evaluate("engine.histories.get('friends').length"), 0)
        self.assertEqual(self.page.evaluate('unreadCounts.size'), 0)
        self.assertEqual(self.page.locator('#notification-owner').text_content(), 'As Sarah')
        self.assertIn('Your turn', self.page.locator('#notification-preview').text_content())
        self.assertNotIn('Are you bringing snacks?', self.page.locator('#chat-messages').text_content())
        self.assertTrue(self.page.locator('#phone-play-button').is_hidden())
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.locator('#chat-notification').click()
        self.page.wait_for_function('ownerWaiting')
        self.assertEqual(self.page.evaluate('viewedChatId'), 'friends')
        self.assertEqual(self.page.locator('#scripted-message').input_value(), 'Are you bringing snacks?')
        self.assertEqual(self.page.evaluate("engine.histories.get('friends').map(message=>message.type)"), ['timestamp'])
        self.page.locator('#send-button').click()
        self.page.wait_for_function("ownerWaiting&&engine.current().id==='second'")
        self.assertTrue(self.page.locator('#chat-notification').is_hidden())
        self.assertEqual(self.page.evaluate("engine.histories.get('friends').filter(message=>message.type==='text').map(message=>message.content)"), ['Are you bringing snacks?'])

    def test_reply_prompt_can_be_opened_from_chat_list_and_survives_pause(self):
        self.page.evaluate("loadStory(linearExampleStory());pause();seekStory('step-3');play()")
        self.page.wait_for_function("pendingChatId==='max'")
        self.page.locator('#chat-back').click()
        self.assertEqual(self.page.locator('[data-open-chat="max"] .chat-list-preview').text_content(), 'Your turn')
        self.assertEqual(self.page.locator('[data-open-chat="max"] .unread-count').count(), 0)
        self.page.locator('[data-open-chat="sarah"]').click()
        self.assertTrue(self.page.locator('#chat-notification').is_visible())
        self.page.evaluate('pause()')
        self.page.locator('#chat-back').click()
        self.page.locator('[data-open-chat="max"]').click()
        self.assertTrue(self.page.evaluate("!playing&&pendingChatId===null&&pendingChatKind===null&&viewedChatId==='max'"))
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.evaluate('play()')
        self.assertEqual(self.page.locator('#scripted-message').input_value(), 'Movie night with Sarah?')
        self.assertEqual(self.page.evaluate("engine.histories.get('max').length"), 0)
        self.page.locator('#send-button').click()
        self.page.evaluate('pause()')
        self.assertEqual(self.page.evaluate("engine.histories.get('max').map(message=>message.content)"), ['Movie night with Sarah?'])

    def test_browsing_away_from_an_existing_reply_turn_uses_notification(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.nodes.find(node=>node.id==='step-16').next='last-reply';
            raw.nodes.push({id:'last-reply',type:'message',chatId:'sarah',
                message:{id:'m-last-reply',type:'text',sender:'user',content:"I'll text you later."},next:'step-17'});
            loadStory(raw);pause();seekStory('step-16');play();
        }""")
        self.assertTrue(self.page.evaluate("ownerWaiting&&viewedChatId==='sarah'"))
        self.page.locator('#chat-back').click()
        self.assertEqual(self.page.locator('[data-open-chat="sarah"] .chat-list-preview').text_content(), 'Your turn')
        self.page.locator('[data-open-chat="max"]').click()
        self.assertEqual(self.page.evaluate('viewedChatId'), 'max')
        self.assertTrue(self.page.locator('#chat-notification').is_visible())
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.locator('#chat-notification').click()
        self.assertTrue(self.page.locator('#chat-notification').is_hidden())
        self.assertTrue(self.page.locator('#send-button').is_enabled())
        self.assertEqual(self.page.locator('#scripted-message').input_value(), "I'll text you later.")

    def test_backward_seek_clears_unread_notifications_and_later_chats(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='a';raw.nodes=[
                {id:'a',type:'message',chatId:'sarah',message:{id:'a',type:'text',sender:'user',content:'Hello'},next:'b'},
                {id:'b',type:'chat',chatId:'max',next:'c'},
                {id:'c',type:'message',chatId:'max',message:{id:'c',type:'text',sender:'max',content:'Another chat'},next:null}
            ];$('speed').value='2';loadStory(raw);
        }""")
        self.page.locator("#send-button").click()
        self.page.wait_for_function("pendingChatId==='max'")
        self.assertTrue(self.page.locator("#chat-notification").is_visible())
        self.assertEqual(self.page.evaluate('pendingChatKind'), 'incoming')
        self.assertTrue(self.page.locator('#phone-play-button').is_hidden())
        self.page.evaluate("seekStory(null)")
        self.assertTrue(self.page.evaluate("ownerWaiting && pendingChatId===null && unreadCounts.size===0"))
        self.assertEqual(self.page.evaluate("engine.messageCount"), 0)
        self.assertTrue(self.page.evaluate("[...engine.histories.values()].every(messages=>messages.length===0)"))
        self.assertFalse(self.page.locator("#chat-notification").is_visible())
        self.page.locator("#chat-back").click()
        self.assertEqual(self.page.locator(".chat-list-row").count(), 1)

    def test_seeking_back_from_completion_continues_without_start_or_resume(self):
        self.page.evaluate("loadStory(linearExampleStory())")
        self.page.evaluate("seekStory('step-17')")
        self.assertTrue(self.page.evaluate("engine.finished && !playing"))
        self.assertEqual(self.page.locator("#phone-play-button").text_content(), "Replay")
        self.page.evaluate("seekStory('step-2')")
        self.assertTrue(self.page.evaluate("playing && ownerWaiting && !engine.finished"))
        self.assertFalse(self.page.locator("#phone-play-button").is_visible())
        self.assertEqual(self.page.evaluate("engine.messageCount"), 2)

    def test_timeline_keyboard_does_not_send_background_messages(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='first-0';raw.nodes=Array.from({length:30},(_,i)=>({
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

    def test_space_sends_from_composer_and_chat_once_per_press(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='space-0';raw.nodes=Array.from({length:3},(_,index)=>({
                id:'space-'+index,type:'message',chatId:'sarah',message:{id:'m-'+index,type:'text',sender:'user',content:'Reply '+index},
                next:index===2?null:'space-'+(index+1)}));$('speed').value='2';loadStory(raw);
        }""")
        self.page.locator('#scripted-message').focus()
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.wait_for_function('ownerWaiting')
        self.page.locator('#chat-scroll').focus()
        self.page.keyboard.down('Space')
        self.page.wait_for_function('ownerWaiting')
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 2)
        self.page.keyboard.up('Space')
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 3)
        self.assertTrue(self.page.evaluate('engine.finished'))

    def test_send_and_shortcuts_skip_typing_once_without_leaving_stale_timers(self):
        self.page.clock.install()
        self.page.clock.pause_at(self.page.evaluate('Date.now()'))
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='typing-0';
            raw.nodes=Array.from({length:5},(_,index)=>({id:'typing-'+index,type:'message',chatId:'sarah',
                message:{id:'typing-'+index,type:index===1?'image-placeholder':'text',
                    sender:index===3?'user':'sarah',content:'A scripted message with a typing delay'},
                next:index===4?null:'typing-'+(index+1)}));loadStory(raw);
        }""")
        self.assertTrue(self.page.locator('#send-button').is_enabled())
        self.assertEqual(self.page.locator('#send-button').get_attribute('aria-label'), 'Show incoming message')
        self.page.locator('#scripted-message').focus()
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.keyboard.up('Space')
        self.page.locator('#send-button').click()
        self.assertEqual(self.page.evaluate('engine.messageCount'), 2)
        self.page.locator('#chat-scroll').focus()
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 3)
        self.page.clock.fast_forward(3000)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 3)
        self.assertEqual(self.page.locator('#send-button').get_attribute('aria-label'), 'Send next message')
        self.page.locator('#send-button').click()
        self.assertEqual(self.page.evaluate('engine.messageCount'), 4)
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.clock.run_for(500)
        self.assertTrue(self.page.locator('#send-button').is_enabled())
        self.page.locator('#send-button').click()
        self.assertEqual(self.page.evaluate('engine.messageCount'), 5)
        self.assertTrue(self.page.evaluate('engine.finished&&!playing'))
        self.page.clock.fast_forward(3000)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 5)
        self.assertEqual(self.page.locator('[data-story-node]').count(), 5)

    def test_skip_typing_respects_pause_navigation_and_input_focus(self):
        self.page.clock.install()
        self.page.clock.pause_at(self.page.evaluate('Date.now()'))
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='incoming';raw.nodes=[
                {id:'incoming',type:'message',chatId:'sarah',message:{id:'one',type:'text',sender:'sarah',content:'Hello'},next:'elsewhere'},
                {id:'elsewhere',type:'message',chatId:'max',message:{id:'two',type:'text',sender:'max',content:'Over here'},next:null}
            ];loadStory(raw);pause();sendMessage();
        }""")
        self.assertEqual(self.page.evaluate('engine.messageCount'), 0)
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.evaluate("""() => {
            play();const input=document.createElement('textarea');input.id='typing-test';document.body.appendChild(input);input.focus();
        }""")
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.locator('#typing-test').input_value(), ' ')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 0)
        self.page.evaluate("$('typing-test').remove()")
        self.open_timeline()
        self.page.locator('#timeline-viewport').focus()
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 0)
        self.page.locator('#timeline-close').click()
        self.page.locator('#chat-back').click()
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.evaluate('sendMessage()')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 0)
        self.page.evaluate("openChat('sarah')")
        self.page.locator('#chat-scroll').focus()
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.clock.run_for(500)
        self.assertTrue(self.page.evaluate('!spaceSendHeld&&spaceRepeatTimer===null'))
        self.page.keyboard.up('Space')
        self.page.locator('#chat-scroll').focus()
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.clock.fast_forward(3000)
        self.assertTrue(self.page.evaluate("pendingChatId==='max'&&pendingChatKind==='incoming'"))
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.evaluate('viewedChatId'), 'sarah')
        self.assertTrue(self.page.locator('#send-button').is_disabled())

    def test_phone_speed_cycles_and_stays_synced_with_controls_without_starting_story(self):
        button = self.page.locator('#phone-speed')
        self.assertIn('Playback speed: Normal. Switch to Fast', button.get_attribute('aria-label'))
        for value, label, next_label in [('2', 'Fast', 'Very fast'), ('very-fast', 'Very fast', 'Normal'), ('1', 'Normal', 'Fast')]:
            button.click()
            self.assertEqual(self.page.locator('#speed').input_value(), value)
            self.assertEqual(button.get_attribute('title'), f'Speed: {label} → {next_label}')
            self.assertFalse(self.page.evaluate('!!engine'))
        button.focus()
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.locator('#speed').input_value(), '2')
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.locator('#speed').input_value(), 'very-fast')
        self.page.locator('#controls-toggle').click()
        self.page.locator('#speed').select_option('1')
        self.page.locator('#controls-close').click()
        self.assertIn('Playback speed: Normal.', button.get_attribute('aria-label'))

    def test_phone_speed_changes_active_timers_and_respects_pause(self):
        self.page.clock.install()
        self.page.clock.pause_at(self.page.evaluate('Date.now()'))
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='speed-0';raw.nodes=Array.from({length:3},(_,i)=>({
                id:'speed-'+i,type:'message',chatId:'sarah',message:{id:'speed-'+i,type:'text',
                    sender:i===1?'sarah':'user',content:i===1?'Long reply '.repeat(100):'Hello'},next:i===2?null:'speed-'+(i+1)}));
            loadStory(raw);
        }""")
        button = self.page.locator('#phone-speed')
        button.click()
        self.page.clock.run_for(300)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 0)
        button.click()
        self.page.clock.run_for(250)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        button.click()
        self.assertEqual(self.page.locator('#speed').input_value(), '1')
        self.page.clock.run_for(500)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        button.click()
        self.page.clock.run_for(500)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 2)
        self.page.evaluate('pause()')
        button.click()
        self.assertIn('Playback speed: Very fast.', button.get_attribute('aria-label'))
        self.page.clock.run_for(2000)
        self.assertTrue(self.page.evaluate('!playing&&timer===null&&engine.messageCount===2'))

    def test_holding_space_repeats_after_delay_and_release_stops_it(self):
        self.page.clock.install()
        self.page.clock.pause_at(self.page.evaluate('Date.now()'))
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='hold-0';raw.nodes=Array.from({length:12},(_,i)=>({
                id:'hold-'+i,type:'message',chatId:'sarah',message:{id:'hold-'+i,type:'text',
                    sender:i===3?'user':'sarah',content:'A long incoming message '.repeat(20)},next:i===11?null:'hold-'+(i+1)}));
            loadStory(raw);
        }""")
        self.page.locator('#scripted-message').focus()
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.clock.run_for(499)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.clock.run_for(1)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 2)
        self.page.clock.run_for(160)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 3)
        self.page.clock.run_for(160)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 4)
        self.page.clock.run_for(640)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 8)
        self.page.keyboard.up('Space')
        self.page.clock.run_for(500)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 8)
        self.assertTrue(self.page.evaluate('!spaceSendHeld&&spaceRepeatTimer===null'))
        self.page.locator('#send-button').focus()
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 9)
        self.page.clock.run_for(500)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 10)
        self.page.keyboard.up('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 10)

    def test_space_hold_keeps_constant_rate_across_consecutive_owner_replies(self):
        self.page.clock.install()
        self.page.clock.pause_at(self.page.evaluate('Date.now()'))
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='reply-0';raw.nodes=Array.from({length:8},(_,i)=>({
                id:'reply-'+i,type:'message',chatId:'sarah',message:{id:'reply-'+i,type:'text',sender:'user',content:'Reply'},
                next:i===7?null:'reply-'+(i+1)}));loadStory(raw);
        }""")
        self.page.locator('#chat-scroll').focus()
        self.page.keyboard.down('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), 1)
        self.page.clock.run_for(500)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 2)
        for expected in range(3, 7):
            self.page.keyboard.down('Space')
            self.page.clock.run_for(159)
            self.assertEqual(self.page.evaluate('engine.messageCount'), expected - 1)
            self.page.clock.run_for(1)
            self.assertEqual(self.page.evaluate('engine.messageCount'), expected)
        self.page.keyboard.up('Space')
        self.page.clock.run_for(1000)
        self.assertEqual(self.page.evaluate('engine.messageCount'), 6)

    def test_space_hold_cancels_on_focus_pause_blur_and_story_load(self):
        self.page.clock.install()
        self.page.clock.pause_at(self.page.evaluate('Date.now()'))
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='hold-0';raw.nodes=Array.from({length:12},(_,i)=>({
                id:'hold-'+i,type:'message',chatId:'sarah',message:{id:'hold-'+i,type:'text',sender:'user',content:'Reply'},
                next:i===11?null:'hold-'+(i+1)}));window.holdStory=raw;loadStory(raw);
        }""")
        for cancel in ["$('chat-back').focus()", 'pause()', "window.dispatchEvent(new Event('blur'))", 'loadStory(holdStory)']:
            self.page.evaluate('loadStory(holdStory)')
            self.page.locator('#scripted-message').focus()
            self.page.keyboard.down('Space')
            self.page.evaluate(cancel)
            count = self.page.evaluate('engine.messageCount')
            self.page.clock.run_for(1200)
            self.assertEqual(self.page.evaluate('engine.messageCount'), count, cancel)
            self.assertTrue(self.page.evaluate('!spaceSendHeld&&spaceRepeatTimer===null'), cancel)
            self.page.keyboard.up('Space')

    def test_space_respects_editable_fields_controls_and_timeline(self):
        self.page.evaluate("loadStory(linearExampleStory());pause();seekStory('step-2');play()")
        count = self.page.evaluate('engine.messageCount')
        self.page.evaluate("""() => {
            const input=document.createElement('textarea');input.id='typing-test';document.body.appendChild(input);input.focus();
        }""")
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.locator('#typing-test').input_value(), ' ')
        self.page.evaluate("document.getElementById('typing-test').remove()")
        self.page.locator('#chat-scroll').focus()
        self.page.keyboard.press('Control+Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), count)
        self.open_timeline()
        self.page.locator('#timeline-viewport').focus()
        self.page.keyboard.press('Space')
        self.assertEqual(self.page.evaluate('engine.messageCount'), count)
        self.page.locator('#timeline-close').click()
        self.page.locator('#controls-toggle').click()
        self.page.locator('#playback-paused').focus()
        self.page.keyboard.press('Space')
        self.assertFalse(self.page.evaluate('playing'))
        self.assertEqual(self.page.evaluate('engine.messageCount'), count)

    def test_message_menu_pauses_and_dismisses_without_changing_history(self):
        self.page.evaluate("$('speed').value='2';loadStory(linearExampleStory());pause();seekStory('step-5');play()")
        row = self.page.locator('[data-story-node="step-5"]')
        count = self.page.evaluate('engine.messageCount')
        row.locator('.bubble').click(button='right')
        self.assertTrue(self.page.locator('#message-menu').is_visible())
        self.assertTrue(self.page.evaluate('!playing&&timer===null'))
        self.page.wait_for_timeout(600)
        self.assertEqual(self.page.evaluate('engine.messageCount'), count)
        self.page.keyboard.press('Escape')
        self.assertTrue(self.page.locator('#message-menu').is_hidden())
        self.assertTrue(self.page.evaluate('playing'))
        self.page.evaluate('pause()')
        row.focus()
        self.page.keyboard.press('Shift+F10')
        self.assertTrue(self.page.locator('#message-menu').is_visible())
        self.page.locator('.phone-header').click(position={'x': 5, 'y': 60})
        self.assertTrue(self.page.locator('#message-menu').is_hidden())
        self.assertFalse(self.page.evaluate('playing'))

    def test_message_menu_seeks_in_older_chat_and_supports_timestamp_and_image(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();
            for(const id of ['step-2','step-6'])raw.nodes.find(node=>node.id===id).message.id='shared-message-id';
            loadStory(raw);pause();seekStory('step-14');
        }""")
        self.page.locator('.image-placeholder').click(button='right')
        self.page.locator('#message-jump').click()
        self.assertEqual(self.page.evaluate('engine.visitedNodeIds.at(-1)'), 'step-13')
        self.assertFalse(self.page.evaluate('playing'))
        self.page.locator('#chat-back').click()
        self.page.locator('[data-open-chat="sarah"]').click()
        self.page.locator('[data-story-node="step-2"] .bubble').click(button='right')
        self.page.locator('#message-jump').click()
        self.assertEqual(self.page.evaluate('engine.visitedNodeIds'), ['step-0', 'step-1', 'step-2'])
        self.assertEqual(self.page.evaluate('viewedChatId'), 'sarah')
        self.assertEqual(self.page.evaluate('engine.histories.size'), 1)
        self.assertFalse(self.page.evaluate('playing'))
        self.page.locator('.timestamp').click(button='right')
        self.page.locator('#message-jump').click()
        self.assertEqual(self.page.evaluate('engine.visitedNodeIds.at(-1)'), 'step-1')
        self.assertEqual(self.page.locator('#chat-messages [data-story-node]').count(), 1)

    def test_message_menu_is_cleared_when_another_story_loads(self):
        self.page.evaluate("loadStory(linearExampleStory());pause();seekStory('step-2')")
        self.page.locator('.bubble').click(button='right')
        self.page.evaluate("loadStory(linearExampleStory());pause()")
        self.assertTrue(self.page.locator('#message-menu').is_hidden())
        self.page.evaluate("document.getElementById('message-jump').click()")
        self.assertEqual(self.page.evaluate('engine.messageCount'), 0)

    def test_long_timeline_only_renders_visible_markers(self):
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.startNodeId='node-0';raw.nodes=Array.from({length:2000},(_,i)=>({
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
        self.page.evaluate("loadStory(linearExampleStory());pause();zoomTimeline(1);selectTimelineMoment(null,{center:true})")
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
        self.page.evaluate("loadStory(linearExampleStory())")
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
        self.page.evaluate("loadStory(linearExampleStory())")
        self.open_timeline()
        self.page.evaluate("""() => {
            const raw=linearExampleStory();raw.story.id='other';raw.nodes.forEach(node=>{node.id='new-'+node.id;if(node.next)node.next='new-'+node.next;});
            raw.startNodeId='new-'+raw.startNodeId;loadStory(raw);
        }""")
        self.assertTrue(self.page.locator("#timeline-panel").is_visible())
        state = self.page.evaluate("JSON.stringify({node:engine.nodeId,path:engine.visitedNodeIds,timer:timerGeneration})")
        self.assertFalse(self.page.evaluate("seekStory('step-2')"))
        self.assertEqual(self.page.evaluate("JSON.stringify({node:engine.nodeId,path:engine.visitedNodeIds,timer:timerGeneration})"), state)
        self.assertTrue(self.page.evaluate("timelineModel.moments.every(m=>m.id===null||m.id.startsWith('new-'))"))

    def test_timeline_sits_beside_interactive_phone_and_closes_with_escape(self):
        self.assertFalse(self.page.locator("#timeline-panel").is_visible())
        self.page.evaluate("loadStory(linearExampleStory())")
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
        self.page.evaluate("loadStory(linearExampleStory())")
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
            const raw=linearExampleStory();raw.nodes[0].type='choice';try{validateStory(raw);}catch(_){choices=true;}
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
                    context.add_init_script(LINEAR_STORY_SCRIPT)
                    page = context.new_page()
                    page.set_default_timeout(5000)
                    page.on("pageerror", lambda error: self.errors.append(str(error)))
                    page.goto(PLAYER)
                    page.evaluate("loadStory(linearExampleStory())")
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
