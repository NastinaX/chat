# Chat Story Generator

[Open the generator](https://nastinax.github.io/chat/) · [Open the player](player.html)

Create fictional chat stories with private and group conversations. Write a script or edit the phone preview, then export screenshots, continuous chat images, or an interactive playback file.

Both apps are standalone HTML files. No account or build step is required.

<img width="1440" height="1000" alt="Story editor and live phone preview" src="https://github.com/user-attachments/assets/d3256bd1-376f-4669-9fbf-aa5b59b3267a" />

## Get started

1. Download or clone this repository and open [index.html](index.html) in a modern browser.
2. Click **Load example** to explore private chats, groups, timestamps, and images.
3. Edit through **Messages**, **Script**, or the preview.

The generator loads Tailwind CSS, Font Awesome, Inter, and dom-to-image from CDNs, so it needs an internet connection. The [player](player.html) works offline with embedded images; external image URLs still need their host.

To serve the folder locally with Python:

```sh
python -m http.server 8000
```

Open [localhost:8000](http://localhost:8000). Keep using the same browser and address to access your saved stories.

## Edit a story

| Editor | Use it to… |
| --- | --- |
| **Messages** | Add text, images, and timestamps; search, filter, reorder, or locate messages with the eye icon. |
| **Script** | Write conversations as text, then click **Apply script**. |
| **Edit in preview** | Type into each phone and choose a sender below it. On by default; toggle it in Preview controls. |

Preview controls:

- **Enter** sends; **Shift+Enter** adds a line. The camera adds images; the clock adds timestamps.
- **Double-click** a message to edit. The editor can change its sender or type: text, image, or timestamp.
- Hover briefly over a bubble, or tap it on touchscreens, to reveal its controls. **Change image** replaces an image in place.
- Drag a message's handle up/down to reorder, left/right to change sender, or onto a character button to assign it. Holding a bubble still for half a second also starts dragging.
- **Right-click** or **⋯** opens insertion, duplication, sender, and deletion options. **Insert above/below** uses the same message editor.
- **Save** or **Ctrl/Cmd+Enter** applies message edits. Click outside or press **Esc** to close a pop-up.

Drag the conversation or empty preview space to scroll; touchscreens support swipes. A down arrow appears in long chats to reach the input. Use **+ Character** below a phone to add a participant.

Preview edits update the script. Apply pending script edits before editing in the preview or exporting. **Undo/Redo** reverses changes; **Ctrl/Cmd+Z** and **Ctrl/Cmd+Shift+Z** work outside text fields.

The sidebar button at the top-left collapses the editor. Click again, or press **Esc**, to reopen it.

## Script syntax

Start a block with `[Chat: Name / Name]`. List three or more participants for a group, then prefix messages with their sender:

```text
[Chat: User / Sarah]
[Phone owner: User]
Time: Friday, 4:30 PM
Sarah: Still up for a movie tonight?
  I'll bring the tickets.
User: I'll check with Max.

[Chat: User / Max]
[Phone owner: User]
User: Movie night with Sarah?
Max: Yes! Let's get snacks first.

[Chat: Sarah / Max]
[Phone owner: Sarah]
Sarah: Does User know about the snacks?
Max: I'll suggest it in the group.

[Chat: User / Sarah / Max]
[Phone owner: User]
Max: Snacks before the movie?
Sarah: Only if there's popcorn!
User: [img:A cinema entrance with a café next door]

[Chat: User / Sarah]
[Phone owner: User]
User: See you at 6:30!
```

**Phone owner** identifies the person whose messages appear on the right. The owner must belong to the chat and stay the same across its blocks. Others appear on the left, with sender names in groups.

Repeat a chat header to return to it later. Participant order does not matter; changing the participant set creates a different chat. New names create shared characters whose names and avatars carry across chats.

| Syntax | Result |
| --- | --- |
| `Sarah: Hello!` | Text from Sarah. |
| `Time: Friday, 4:30 PM` | A centered timestamp. |
| `Sarah: [img:A beach at sunset]` | An image placeholder. |
| `Sarah: [img:https://example.com/photo.jpg\|alt:A beach]` | An image URL with optional description. |
| Two spaces before a continuation line | A new line in the preceding message. |
| `Sarah: \[img:This is text]` | Literal text beginning with image syntax. |

Upload real images through Messages or the preview. Descriptions create placeholders; they do not generate images. Uploads are included in JSON backups; external URLs remain external.

Quote names containing `/`, brackets, or colons:

```text
[Chat: User / "Sarah / Work"]
[Phone owner: User]
"Sarah / Work": Hello!
```

**Apply script replaces messages in the chats it lists.** Other chats remain. Without headers, it updates the selected chat. Syntax errors leave existing chats intact.

## Preview and appearance

**Story order** is the default view. It stacks blocks in script order, including separate blocks for later visits to a chat. **Current chat** shows one conversation together. Preview and export preferences are saved with each story.

**Earlier messages** fills spare room in short returning blocks with recent messages from that chat. A **New messages** line separates this read-only history from the new content. Long blocks show only new messages. Turn it off for compact blocks. New chats keep their top spacing; returning chats start below the header. PNG exports use the same layout.

Move near a phone's right edge to reveal its collapse button. Collapsed phones show only the top and bottom bars; exports still include all messages. The button above the first phone collapses or expands all blocks. Use **Script → Story blocks** to move or duplicate blocks.

<img width="1100" height="1136" alt="Chat blocks stacked in story order" src="https://github.com/user-attachments/assets/cecc2619-13cf-4335-a165-53986525a375" />

**Settings** groups chat details, status, appearance, and screenshot overlap:

- **Changes → All chats / This chat** sets the scope for future edits. Switching scope does not copy values. New stories use All chats.
- **Apply to all** beside a setting copies that value everywhere and clears only its section overrides. **Apply all** copies the selected chat's phone settings. Globally applied values become defaults for new chats.
- A **custom** count marks section overrides. Undo restores both values and overrides. Titles and group avatars belong to individual chats; character names and avatars are shared.

In the preview, click the **clock** for its time picker, or **battery**, **signal**, and **Wi-Fi** for their controls. Drag those three icons to adjust their values; arrow keys also work. In Story order, these edits affect only that section. **Reset status** restores the chat's defaults; **Apply to all** copies a section value everywhere. In Current chat, edits follow Changes.

Move near either phone edge to reveal a width handle. Drag to resize between 300–600 px, or use arrow keys (Shift for 10 px steps). Width follows Changes and supports Undo.

<p align="center">
  <img width="250" alt="Group conversation with sender names" src="https://github.com/user-attachments/assets/1cfc538a-4e44-49bf-9e44-f6a0747ab57e" />
</p>

## Export images

Open **Export** in Preview controls; it starts collapsed. Choose **1×–3×** resolution and an export:

| Export | Current chat | Story order |
| --- | --- | --- |
| **Screenshots (ZIP)** | Pages covering the chat. | Pages of all blocks, in script order. |
| **Full chat(s)** | One continuous PNG. | One continuous image per block, in an ordered ZIP. |
| **Screenshot** | One image at the current scroll position. | One image of the selected chat at its scroll position. |

Oversized continuous images split into numbered parts in one ZIP, preserving resolution. Each part includes the header and footer. Editing controls and unsent text are excluded. ZIP exports use a single download; progress and Cancel remain accessible during capture.

Export options:

- **Align top bubble** starts pages at message boundaries where possible. Bottom bubbles may be cropped; the final page aligns with the chat's bottom. Oversized messages continue across pages.
- **Screenshot overlap (px)** in Settings controls repeated content between pages. Top alignment may adjust it; continuous images ignore it.
- **Include full images** adds each image message's uncropped original after its first screenshot, once per message. Avatars, placeholders, and repeated history are excluded. Originals keep their dimensions and format. This option makes any image export a ZIP.
- **Chat labels** inserts narrow PNGs such as **Sarah & Max** between conversation changes in Story order ZIPs, with the owner first. Labels match the next chat's width, resolution, and theme. The opening chat and consecutive blocks of the same chat have no label. **Skip owner** selects a character to omit labels for, such as User; a recipient with that name does not trigger the filter. Choose **Include everyone** to clear it.
- **Progress status** advances time and drains battery across PNG exports. **Duration (min)** and **Battery drop (%)** set the totals; zero keeps either steady. Progress starts from preview values. A custom section clock or battery restarts that value's progress at the section's first message; other values use overall story progress.
- **Vary signal & Wi-Fi** adds repeatable fluctuations around preview values. Choose each range independently, or Fixed; connections set to off stay off.

Status progression follows the latest new message visible in each image. Repeated history, labels, and original image files do not advance it. Preview values stay unchanged.

## Play a story

1. Apply script edits, then choose **Preview → Export → Player (JSON)**.
2. Open [player.html](player.html), click **Open story**, and select the `.chatstory.json` file. **Try example** loads a demo.
3. Incoming messages arrive after a typing delay. Click **Send** or press **Enter** for the owner's scripted replies.

The player opens with just the phone. **Controls** at the top-right contains pause, speed, restart, chats, timeline, and file options. Switching browser tabs pauses playback until you return.

The phone's **back arrow** shows chats reached so far, recent messages, and unread counts. **As …** identifies the phone owner. A new chat starting with an incoming message shows a notification at the top of the phone; open it or its unread chat to continue. Chats starting with the owner's message open automatically. Returning chats retain their history and show a New messages divider.

**Controls → Timeline** opens a story map beside the phone, or below it on small screens. Scroll to zoom at the cursor and drag to pan. Zooming out turns messages into dots, then compact chat lines. Click a message to jump; click a compact chat to zoom into it. **Now** follows playback; the percentage resets zoom. Arrow keys, Home/End, and Enter support navigation.

Jumping rebuilds chat history and section status through that moment, clearing later notifications. A manual pause is preserved. Playback is linear; choices and branching remain future work. See the [player format](docs/player-format.md) for technical details.

Player files contain applied story content, excluding drafts and undo history. They cannot be imported into the generator. Files stay in the browser session and are not uploaded; reopen them after reloading.

## Save and manage stories

Use the story selector to switch stories, or **New story**, **Rename**, and **Delete story** to manage them. The trash button beside the chat selector deletes only that chat.

Changes autosave in this browser using IndexedDB; the status appears below the app title. Stories do not sync between browsers or devices. Back up before clearing browser data or changing the app's address.

**Settings → Story backup (JSON) → Export** saves one editable story, including its name, chats, characters, images, settings, order, and drafts. **Import** replaces the current story; Undo restores it. Create a new story before importing to keep both. Duplicate names receive a number.

## Project files and tests

| File | Purpose |
| --- | --- |
| [index.html](index.html) | Generator, preview, browser storage, and exports. |
| [player.html](player.html) | Standalone player. |
| [docs/player-format.md](docs/player-format.md) | Versioned playback format. |
| [tests/test_generator_export.py](tests/test_generator_export.py) | Browser checks for preview settings, PNG layout, pagination, images, and ZIPs. |
| [tests/test_player_timeline.py](tests/test_player_timeline.py) | Offline browser checks for playback, navigation, and seeking. |

Both apps can run on a static host. Optional regression checks require Python, Playwright, and Chromium:

```sh
python -m pip install playwright
python -m playwright install chromium
python -B -m unittest discover -s tests
```

Generator tests need CDN access at startup; player tests work offline.
