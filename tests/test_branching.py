"""Browser regression checks for scene authoring and branching playback."""
import unittest

import test_generator_export as generator_checks
import test_player_timeline as player_checks


BRANCH_SCRIPT = """[Scene: invitation]
[Chat: User / Sarah]
[Phone owner: User]
Sarah: Can you meet me tonight?
[Choice]
"Yes. Where?" -> meet
"Sorry, I can't." -> stay_home
[End choice]

[Scene: meet]
[Chat: User / Sarah]
Sarah: MEET_ONLY: At the station.
[Go to: later]

[Scene: stay_home]
[Chat: User / Sarah]
Sarah: STAY_ONLY: Keep your phone nearby.
[Go to: later]

[Scene: later]
[Chat: User / Sarah]
Time: Later that evening
Sarah: MERGED_END: Text me when you're home.
[End]
"""


PLAYER_STORY = """() => {
    const raw=exampleStory();raw.version=2;raw.startNodeId='intro';
    const message=(id,sender,content,next)=>({id,type:'message',chatId:'sarah',
        message:{id:'m-'+id,type:'text',sender,content,altText:''},next});
    raw.nodes=[
        {id:'intro',type:'chat',chatId:'sarah',next:'question',status:{time:'09:00',battery:95}},
        message('question','sarah','Are you coming?','first-choice'),
        {id:'first-choice',type:'choice',chatId:'sarah',options:[
            {id:'yes',text:'Yes. Where?',next:'yes-reply'},
            {id:'no',text:"Sorry, I can't.",next:'no-reply'}]},
        message('yes-reply','user','Yes. Where?','meet-chat'),
        {id:'meet-chat',type:'chat',chatId:'sarah',next:'meet-message',status:{time:'10:00',battery:70}},
        message('meet-message','sarah','MEET_ONLY','second-choice'),
        message('no-reply','user',"Sorry, I can't.",'stay-chat'),
        {id:'stay-chat',type:'chat',chatId:'sarah',next:'stay-message',status:{time:'12:00',battery:40}},
        message('stay-message','sarah','STAY_ONLY','second-choice'),
        {id:'second-choice',type:'choice',chatId:'sarah',options:[
            {id:'continue',text:'Keep going.',next:'continue-reply'},
            {id:'wait',text:'Wait a moment.',next:'wait-reply'}]},
        message('continue-reply','user','Keep going.','joined'),
        message('wait-reply','user','Wait a moment.','joined'),
        {id:'joined',type:'chat',chatId:'sarah',next:'merged-message'},
        message('merged-message','sarah','MERGED_END','end'),
        {id:'end',type:'end'}
    ];return raw;
}"""


class BranchingGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator_checks.GeneratorExportTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        generator_checks.GeneratorExportTests.tearDownClass.__func__(cls)

    setUp = generator_checks.GeneratorExportTests.setUp
    tearDown = generator_checks.GeneratorExportTests.tearDown

    def apply_script(self, script=BRANCH_SCRIPT):
        self.page.evaluate("""raw => {
            switchTab('script');document.getElementById('script-input').value=raw;markScriptDirty();parseScript();
        }""", script)
        self.assertFalse(self.page.locator('#script-error').is_visible(),
                         self.page.locator('#script-error').text_content())

    def test_scene_script_survives_preview_edits_and_serialization_with_stable_blocks(self):
        self.apply_script()
        before = self.page.evaluate("storyFlow.scenes.map(scene=>[scene.id,...scene.blockIds])")
        self.page.evaluate("""() => {
            const chat=activeConversation(),first=storyFlow.scenes[0].blockIds[0];
            getPreviewDraft(chat).text='Added through the preview.';sendPreviewMessage(chat.id,first);
        }""")
        script = self.page.locator('#script-input').input_value()
        self.assertIn('[Scene: invitation]', script)
        self.assertIn('[Choice]', script)
        self.assertIn('[Go to: later]', script)
        self.assertIn('Added through the preview.', script)
        self.apply_script(script)
        self.assertEqual(self.page.evaluate("storyFlow.scenes.map(scene=>[scene.id,...scene.blockIds])"), before)
        self.assertEqual(self.page.evaluate("storyFlow.scenes[0].exit.options.map(option=>option.text)"),
                         ['Yes. Where?', "Sorry, I can't."])

    def test_branching_example_loads_from_its_own_button(self):
        self.page.locator('#load-branching-example').click()
        self.page.wait_for_function("!!storyFlow && !projectOperationPending")
        self.assertEqual(self.page.evaluate('previewMode'), 'story')
        self.assertTrue(self.page.locator('#preview-path-controls').is_visible())
        self.assertGreaterEqual(self.page.locator('[data-preview-choice]').count(), 1)
        self.assertIn('[Choice]', self.page.locator('#script-input').input_value())
        self.assertEqual(self.page.evaluate("buildPlayableStory(validateBackup(projectBackup()),currentProjectId).version"), 2)

    def test_branch_backup_selected_path_and_undo_restore_flow(self):
        self.apply_script()
        result = self.page.evaluate("""() => {
            const choice=storyFlow.scenes[0].exit;selectPreviewChoice(choice.id,choice.options[1].id);
            const backup=projectBackup(),restored=validateBackup(JSON.parse(JSON.stringify(backup)));
            applyProjectSnapshot(restored);
            const selection=previewChoices[choice.id],flow=JSON.stringify(storyFlow);
            beginProjectChange();applyProjectSnapshot(validateBackup(blankProjectSnapshot('Blank')));
            const cleared=storyFlow===null&&Object.keys(previewChoices).length===0;
            undoProject();
            return {version:backup.version,selection,expected:choice.options[1].id,cleared,
                restored:JSON.stringify(storyFlow)===flow,undoSelection:previewChoices[choice.id]};
        }""")
        self.assertEqual(result['version'], 3)
        self.assertEqual(result['selection'], result['expected'])
        self.assertTrue(result['cleared'])
        self.assertTrue(result['restored'])
        self.assertEqual(result['undoSelection'], result['expected'])

    def test_invalid_scene_scripts_reject_atomically(self):
        self.apply_script()
        snapshot = self.page.evaluate("JSON.stringify({characters,storyBlocks,storyFlow,conversations})")
        invalid = [
            BRANCH_SCRIPT.replace('[Scene: meet]', '[Scene: invitation]'),
            BRANCH_SCRIPT.replace('-> meet', '-> missing'),
            BRANCH_SCRIPT.replace('"Sorry, I can\'t." -> stay_home\n', ''),
            BRANCH_SCRIPT.replace('[Go to: later]', '[Go to: invitation]', 1),
            BRANCH_SCRIPT.rsplit('[End]', 1)[0],
            '[Scene: start]\n[Choice]\n"Yes" -> start\n"No" -> start\n[End choice]',
            BRANCH_SCRIPT.replace('[End choice]', '[Go to: later]', 1),
        ]
        for script in invalid:
            with self.subTest(script=script[:100]):
                self.page.evaluate("""raw=>{document.getElementById('script-input').value=raw;
                    markScriptDirty();parseScript();}""", script)
                self.assertTrue(self.page.locator('#script-error').is_visible())
                self.assertEqual(self.page.evaluate("JSON.stringify({characters,storyBlocks,storyFlow,conversations})"), snapshot)

    def test_selected_path_context_contains_its_reply_and_never_the_other_branch(self):
        self.apply_script()
        self.page.evaluate("setPreviewMode('story')")
        for selected, included, excluded, reply in [(0, 'MEET_ONLY', 'STAY_ONLY', 'Yes. Where?'),
                                                   (1, 'STAY_ONLY', 'MEET_ONLY', "Sorry, I can't.")]:
            result = self.page.evaluate("""index => {
                const choice=storyFlow.scenes[0].exit;selectPreviewChoice(choice.id,choice.options[index].id);
                const path=selectedStoryPath(),views=storyPreviewBlocks();
                return {text:views.flatMap(view=>view.messages.map(message=>message.content)).join(' | '),
                    history:views.at(-1).history.map(message=>message.content).join(' | '),
                    generated:path.chats.flatMap(chat=>chat.messages).filter(message=>message.choiceReply).map(message=>message.content),
                    authored:conversations.flatMap(chat=>chat.messages).some(message=>message.choiceReply),
                    visible:document.getElementById('story-preview').textContent};
            }""", selected)
            self.assertIn(included, result['text'])
            self.assertNotIn(excluded, result['text'])
            self.assertIn(reply, result['history'])
            self.assertNotIn(excluded, result['history'])
            self.assertEqual(result['generated'], [reply])
            self.assertFalse(result['authored'])
            self.assertIn(included, result['visible'])
            self.assertNotIn(excluded, result['visible'])

    def test_returning_reply_context_stays_unique_after_repeated_refits_and_resizing(self):
        self.apply_script()
        result = self.page.evaluate("""async() => {
            setPreviewMode('story');await document.fonts.ready;
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            const views=storyPreviewBlocks(),checks=[];
            for(const view of views) {
                const section=Array.from(document.querySelectorAll('#story-preview > section'))
                    .find(section=>section.dataset.storyBlock===view.block.id);
                const phone=section.querySelector('.phone-container');
                for(const width of [300,600,375,300,375]) {
                    phone.style.width=width+'px';fitStoryPhoneContext(phone,view);
                    phone.dispatchEvent(new Event('storylayoutchange'));
                    fitStoryPhoneContext(phone,view);
                    const rows=Array.from(phone.querySelectorAll('[data-message-id]'));
                    const ids=rows.map(row=>row.dataset.messageId);
                    checks.push({unique:new Set(ids).size===ids.length,
                        replies:rows.filter(row=>row.dataset.choiceReply==='true').length,
                        historyReplies:rows.filter(row=>row.dataset.choiceReply==='true'&&row.dataset.storyContext==='true').length});
                }
            }
            return checks;
        }""")
        self.assertEqual(len(result), 15)
        self.assertTrue(all(check['unique'] for check in result))
        self.assertTrue(all(check['replies'] == 1 for check in result))
        self.assertTrue(any(check['historyReplies'] == 1 for check in result))

    def test_export_status_stays_frozen_when_later_live_sections_gain_overrides(self):
        self.apply_script()
        self.page.evaluate("""() => {
            setPreviewMode('story');setDirectEditing(false);exportOptions.scale=1;
            exportOptions.statusProgress={...DEFAULT_EXPORT_STATUS,enabled:false};
            window.frozenBranchFrames=[];window.releaseBranchCapture=null;
            domtoimage.toBlob=async node=>{
                frozenBranchFrames.push({time:phonePart(node,'preview-time').textContent,
                    battery:phonePart(node,'preview-battery-text').textContent});
                if(frozenBranchFrames.length===1)await new Promise(resolve=>releaseBranchCapture=resolve);
                return new Blob(['png'],{type:'image/png'});
            };
        }""")
        for capture in ['saveSeries', 'saveContinuous']:
            self.page.evaluate("""() => {storyBlocks.forEach(block=>delete block.status);
                frozenBranchFrames=[];releaseBranchCapture=null;}""")
            with self.page.expect_download():
                self.page.evaluate(f'() => {{window.pendingBranchCapture={capture}();}}')
                self.page.wait_for_function("typeof releaseBranchCapture==='function'")
                self.page.evaluate("""() => {
                    storyBlocks.slice(1).forEach(block=>{block.status={time:'22:22',battery:13,
                        signalStrength:0,wifiStrength:0};});releaseBranchCapture();
                }""")
                self.page.evaluate('() => pendingBranchCapture')
            frames = self.page.evaluate('frozenBranchFrames')
            self.assertGreaterEqual(len(frames), 3)
            self.assertTrue(all(frame == {'time': '9:41', 'battery': '100%'} for frame in frames))
            self.assertTrue(self.page.evaluate("storyBlocks.slice(1).every(block=>block.status.time==='22:22')"))

    def test_empty_start_path_rejects_player_and_png_export_after_chat_deletion(self):
        self.apply_script("""[Scene: start]
[Chat: User / Sarah]
[Phone owner: User]
Sarah: Starting chat.
[End]
[Scene: unused]
[Chat: User / Max]
[Phone owner: User]
Max: Unreachable chat still has messages.
[End]
""")
        self.page.evaluate("deleteConversation();setPreviewMode('story')")
        result = self.page.evaluate("""() => {
            try{buildPlayableStory(validateBackup(projectBackup()),'empty-start');return '';}
            catch(error){return error.message;}
        }""")
        self.assertIn('starting scene', result.lower())
        self.assertTrue(self.page.evaluate("conversations.some(chat=>chat.messages.length)"))
        for capture in ['saveSeries', 'saveContinuous']:
            self.page.evaluate(f'{capture}()')
            self.assertFalse(self.page.evaluate('captureInProgress'))
            self.assertIn('no chat blocks', self.dialogs[-1].lower())
        self.assertEqual(self.downloads, [])

    def test_branch_backup_rejects_reordered_scene_blocks_and_invalid_flow(self):
        self.apply_script(BRANCH_SCRIPT.replace('Sarah: Can you meet me tonight?\n',
                          'Sarah: Can you meet me tonight?\n[Chat: User / Sarah]\nSarah: Second block.\n'))
        result = self.page.evaluate("""() => {
            const backup=projectBackup(),patches=[
                raw=>raw.flow.scenes[0].blockIds.reverse(),
                raw=>{raw.flow.scenes[0].exit.options[0].target='missing';},
                raw=>{raw.flow.scenes[0].exit.options[1].id=raw.flow.scenes[0].exit.options[0].id;},
                raw=>{raw.flow.scenes[1].blockIds.push(raw.flow.scenes[0].blockIds[0]);},
                raw=>{raw.flow.scenes[1].exit={type:'goto',target:'invitation'};}
            ];let rejected=0;
            for(const patch of patches){const raw=JSON.parse(JSON.stringify(backup));patch(raw);
                try{validateBackup(raw);}catch(_){rejected++;}}
            return {rejected,total:patches.length,blocks:backup.flow.scenes[0].blockIds.length};
        }""")
        self.assertEqual(result['blocks'], 2)
        self.assertEqual(result['rejected'], result['total'])

    def test_both_png_exports_follow_the_selected_route_and_freeze_it(self):
        self.apply_script()
        self.page.evaluate("""() => {
            setPreviewMode('story');setDirectEditing(false);exportOptions.scale=1;
            window.branchFrames=[];window.flipBranch=true;
            domtoimage.toBlob=async node=>{
                branchFrames.push(node.textContent);
                if(flipBranch){const choice=storyFlow.scenes[0].exit;
                    previewChoices[choice.id]=choice.options[0].id;flipBranch=false;}
                return new Blob(['png'],{type:'image/png'});
            };
        }""")
        for capture in ['saveSeries', 'saveContinuous']:
            self.page.evaluate("""() => {const choice=storyFlow.scenes[0].exit;
                selectPreviewChoice(choice.id,choice.options[1].id);branchFrames=[];flipBranch=true;}""")
            with self.page.expect_download():
                self.page.evaluate(f'{capture}()')
            frames = '\n'.join(self.page.evaluate('branchFrames'))
            self.assertIn('STAY_ONLY', frames)
            self.assertIn("Sorry, I can't.", frames)
            self.assertIn('MERGED_END', frames)
            self.assertNotIn('MEET_ONLY', frames)

    def test_player_export_contains_all_branches_and_prepared_owner_replies(self):
        self.apply_script()
        result = self.page.evaluate("""() => {
            const backup=validateBackup(projectBackup()),first=buildPlayableStory(backup,'branch-test'),
                second=buildPlayableStory(backup,'branch-test'),choice=first.nodes.find(node=>node.type==='choice');
            return {story:first,stable:first.nodes.map(node=>node.id).join()===second.nodes.map(node=>node.id).join(),
                choice:choice.options.map(option=>({text:option.text,
                    reply:first.nodes.find(node=>node.id===option.next)}))};
        }""")
        self.assertEqual(result['story']['version'], 2)
        self.assertTrue(result['stable'])
        texts = [node['message']['content'] for node in result['story']['nodes'] if node['type'] == 'message']
        self.assertTrue(any('MEET_ONLY' in text for text in texts))
        self.assertTrue(any('STAY_ONLY' in text for text in texts))
        for option in result['choice']:
            self.assertEqual(option['reply']['type'], 'message')
            self.assertEqual(option['reply']['message']['content'], option['text'])
        player = self.context.new_page()
        player.on('pageerror', lambda error: self.errors.append(str(error)))
        player.goto(player_checks.PLAYER)
        loaded = player.evaluate("raw=>{loadStory(raw);pause();return story.nodes.size;}", result['story'])
        self.assertEqual(loaded, len(result['story']['nodes']))


class BranchingPlayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        player_checks.PlayerTimelineTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        player_checks.PlayerTimelineTests.tearDownClass.__func__(cls)

    setUp = player_checks.PlayerTimelineTests.setUp
    tearDown = player_checks.PlayerTimelineTests.tearDown
    open_timeline = player_checks.PlayerTimelineTests.open_timeline

    def load_branching(self):
        self.page.evaluate(f"() => {{loadStory(({PLAYER_STORY})());pause();}}")

    def test_choice_prepares_reply_and_send_commits_once(self):
        self.load_branching()
        self.page.evaluate("seekStory('first-choice');play()")
        self.assertTrue(self.page.locator('#reply-options').is_visible())
        self.assertTrue(self.page.locator('#send-button').is_disabled())
        self.page.locator('[data-choice-option="yes"]').click()
        self.assertEqual(self.page.locator('#scripted-message').input_value(), 'Yes. Where?')
        self.assertNotIn('Yes. Where?', self.page.locator('#chat-messages').text_content())
        self.page.locator('[data-choice-option="no"]').click()
        self.assertEqual(self.page.locator('#scripted-message').input_value(), "Sorry, I can't.")
        self.page.locator('#send-button').click()
        self.page.evaluate('pause()')
        result = self.page.evaluate("""() => ({texts:engine.histories.get('sarah').map(message=>message.content),
            decisions:Array.from(engine.decisions),visited:engine.visitedNodeIds})""")
        self.assertEqual(result['texts'], ['Are you coming?', "Sorry, I can't."])
        self.assertEqual(result['decisions'], [['first-choice', 'no']])
        self.assertEqual(result['visited'].count('no-reply'), 1)
        self.assertNotIn('yes-reply', result['visited'])

    def test_branching_demo_opens_at_a_working_reply_choice(self):
        self.page.locator('#phone-branching-example-button').click()
        self.page.evaluate("pause();seekStory('demo-invitation');play()")
        self.assertEqual(self.page.evaluate('story.version'), 2)
        self.assertEqual(self.page.locator('#reply-options [data-choice-option]').count(), 2)
        self.assertTrue(self.page.locator('#reply-options').is_visible())
        self.page.locator('[data-choice-option="meet"]').click()
        self.assertTrue(self.page.locator('#scripted-message').input_value())
        self.assertTrue(self.page.locator('#send-button').is_enabled())

    def test_chosen_branch_notifies_for_an_incoming_chat_with_another_owner(self):
        self.page.evaluate(f"""() => {{
            const raw=({PLAYER_STORY})();
            const chat=raw.nodes.find(node=>node.id==='stay-chat');chat.chatId='friends';
            const incoming=raw.nodes.find(node=>node.id==='stay-message');
            incoming.chatId='friends';incoming.message.sender='max';incoming.next='end';
            loadStory(raw);pause();seekStory('first-choice');
            const originalSchedule=schedule;schedule=(delay,callback)=>originalSchedule(Math.min(delay,20),callback);
            play();
        }}""")
        self.page.locator('[data-choice-option="no"]').click()
        self.page.locator('#send-button').click()
        self.page.wait_for_function("pendingChatId==='friends'")
        self.assertTrue(self.page.locator('#chat-notification').is_visible())
        self.assertEqual(self.page.locator('#notification-owner').text_content(), 'As Sarah')
        self.assertIn('STAY_ONLY', self.page.locator('#notification-preview').text_content())
        self.assertNotIn('MEET_ONLY', self.page.locator('#chat-messages').text_content())
        self.page.locator('#chat-notification').click()
        self.page.evaluate('pause()')
        self.assertEqual(self.page.evaluate('pendingChatId'), None)
        self.assertEqual(self.page.locator('#phone-role').text_content(), 'As Sarah')
        self.assertIn('STAY_ONLY', self.page.locator('#chat-messages').text_content())

    def test_alternatives_merge_without_history_leaks_and_seek_reopens_choices(self):
        self.load_branching()
        result = self.page.evaluate("""() => {
            engine.seekTo('first-choice');engine.choose('no');engine.advance();engine.advance();
            while(engine.current().type!=='choice')engine.advance();
            const status={...engine.chatStatuses.get('sarah')};
            engine.choose('wait');engine.advance();engine.advance();
            while(!engine.finished)engine.advance();
            const first=engine.histories.get('sarah').map(message=>message.content),decisions=Array.from(engine.decisions);
            engine.seekTo('first-choice');
            const reset={node:engine.current().id,decisions:Array.from(engine.decisions),
                history:engine.histories.get('sarah').map(message=>message.content),status:engine.chatStatuses.get('sarah')};
            engine.choose('yes');engine.advance();engine.advance();
            while(engine.current().type!=='choice')engine.advance();
            engine.choose('continue');engine.advance();engine.advance();
            while(!engine.finished)engine.advance();
            return {first,decisions,status,reset,second:engine.histories.get('sarah').map(message=>message.content)};
        }""")
        self.assertIn('STAY_ONLY', result['first'])
        self.assertNotIn('MEET_ONLY', result['first'])
        self.assertIn('Wait a moment.', result['first'])
        self.assertEqual(result['status'], {'time': '12:00', 'battery': 40})
        self.assertEqual(result['reset']['node'], 'first-choice')
        self.assertEqual(result['reset']['decisions'], [])
        self.assertEqual(result['reset']['history'], ['Are you coming?'])
        self.assertEqual(result['reset']['status'], {'time': '09:00', 'battery': 95})
        self.assertIn('MEET_ONLY', result['second'])
        self.assertNotIn('STAY_ONLY', result['second'])
        self.assertNotIn('Wait a moment.', result['second'])
        self.assertIn('MERGED_END', result['first'])
        self.assertIn('MERGED_END', result['second'])

    def test_seeking_later_choice_keeps_earlier_decision_and_clears_later_one(self):
        self.load_branching()
        result = self.page.evaluate("""() => {
            engine.seekTo('first-choice');engine.choose('yes');engine.advance();engine.advance();
            while(engine.current().type!=='choice')engine.advance();
            engine.choose('continue');engine.advance();engine.advance();
            while(!engine.finished)engine.advance();
            engine.seekTo('second-choice');
            return {node:engine.current().id,decisions:Array.from(engine.decisions),
                history:engine.histories.get('sarah').map(message=>message.content)};
        }""")
        self.assertEqual(result['node'], 'second-choice')
        self.assertEqual(result['decisions'], [['first-choice', 'yes']])
        self.assertIn('MEET_ONLY', result['history'])
        self.assertNotIn('Keep going.', result['history'])
        self.assertNotIn('MERGED_END', result['history'])

    def test_timeline_contains_forks_and_merges_but_unplayed_nodes_cannot_seek(self):
        self.load_branching()
        self.page.evaluate("seekStory('first-choice')")
        self.open_timeline()
        result = self.page.evaluate("""() => {
            const before=JSON.stringify(engine.visitedNodeIds),has=id=>timelineModel.byId.has(id);
            const rejected=seekStory('stay-message');
            return {hasMeet:has('meet-message'),hasStay:has('stay-message'),hasMerge:has('merged-message'),
                unchanged:before===JSON.stringify(engine.visitedNodeIds),rejected,
                route:engine.route.map(node=>node.id)};
        }""")
        self.assertTrue(result['hasMeet'])
        self.assertTrue(result['hasStay'])
        self.assertTrue(result['hasMerge'])
        self.assertFalse(result['rejected'])
        self.assertTrue(result['unchanged'])
        self.assertEqual(result['route'][-1], 'first-choice')

    def test_choices_overview_preserves_forks_and_cursor_anchoring_to_two_percent(self):
        self.load_branching()
        self.page.evaluate("seekStory('first-choice')")
        self.open_timeline()
        before = self.page.evaluate('JSON.stringify(engine.visitedNodeIds)')
        for zoom in [.1, .079, .05, .02]:
            result = self.page.evaluate("""zoom => {
                const viewport=$('timeline-viewport'),point=timelineView.byId.get('first-choice');
                const x=point.x+timelineOffset-viewport.scrollLeft,y=point.y+timelineTop-viewport.scrollTop;
                zoomTimeline(zoom,{x,y});
                const after=timelineView.byId.get('first-choice');
                return {dx:after.x+timelineOffset-viewport.scrollLeft-x,
                    dy:after.y+timelineTop-viewport.scrollTop-y};
            }""", zoom)
            self.assertAlmostEqual(result['dx'], 0, delta=1.5)
            self.assertAlmostEqual(result['dy'], 0, delta=1.5)
        self.assertEqual(self.page.locator('#timeline-viewport').get_attribute('data-detail'), 'choices')
        self.assertEqual(self.page.locator('#timeline-zoom-reset').text_content(), '2%')
        self.assertTrue(self.page.locator('#timeline-zoom-out').is_disabled())
        self.assertEqual(self.page.evaluate('JSON.stringify(engine.visitedNodeIds)'), before)
        result = self.page.evaluate("""() => ({
            kinds:timelineView.moments.filter(moment=>moment.display!=='hidden').map(moment=>moment.source.kind),
            forks:timelineView.edges.filter(edge=>edge.from.id==='first-choice').map(edge=>edge.next),
            joins:timelineView.edges.filter(edge=>edge.to.id==='second-choice').length,
            paths:[...$('timeline-links').querySelectorAll('path')].map(path=>path.getAttribute('d')),
            labels:[...$('timeline-points').querySelectorAll('button')].filter(button=>button.dataset.detail!=='dot').map(button=>button.dataset.kind)
        })""")
        self.assertEqual(result['kinds'], ['start', 'choice', 'choice', 'end'])
        self.assertEqual(result['forks'], ['yes-reply', 'no-reply'])
        self.assertEqual(result['joins'], 2)
        self.assertEqual(len(set(result['paths'])), len(result['paths']))
        self.assertTrue(all(kind == 'choice' for kind in result['labels']))
        self.page.locator('.timeline-node[data-kind="choice"].current').press('Enter')
        self.assertEqual(self.page.evaluate('engine.current().id'), 'first-choice')
        self.assertEqual(self.page.evaluate('engine.decisions.size'), 0)

    def test_invalid_choices_graph_targets_cycles_and_v1_choices_are_rejected(self):
        result = self.page.evaluate(f"""() => {{
            const make={PLAYER_STORY},patches=[
                raw=>{{raw.nodes.find(n=>n.type==='choice').options=[];}},
                raw=>{{raw.nodes.find(n=>n.type==='choice').options[1].id='yes';}},
                raw=>{{raw.nodes.find(n=>n.type==='choice').options[0].next='missing';}},
                raw=>{{raw.nodes.find(n=>n.type==='choice').options[0].text='';}},
                raw=>{{raw.nodes.find(n=>n.id==='meet-message').next='first-choice';}},
                raw=>{{raw.nodes.find(n=>n.id==='yes-reply').message.sender='sarah';}},
                raw=>{{raw.version=1;}}
            ];let rejected=0;
            for(const patch of patches){{const raw=make();patch(raw);try{{validateStory(raw);}}catch(_){{rejected++;}}}}
            return {{rejected,total:patches.length}};
        }}""")
        self.assertEqual(result['rejected'], result['total'])


if __name__ == '__main__':
    unittest.main()
