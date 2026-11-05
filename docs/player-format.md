# Chat Story Player format

The generator's **Player (JSON)** command writes a `<story-name>.chatstory.json` file for [`player.html`](../player.html), separate from editable story backups.

Apply script edits before exporting. Drafts, composer text, undo history, browser-storage records, and editor UI state are excluded. Uploaded images and avatars are embedded; external image URLs remain external. The player accepts files up to **50 MiB** (52,428,800 bytes).

## Top-level fields

| Field | Meaning |
| --- | --- |
| `format` | Exactly `"chat-story-player"`. |
| `version` | `1` for linear stories; `2` also supports choices. Unknown versions are rejected. |
| `story` | An object with nonempty string `id` and `title` fields. |
| `characters` | Characters with unique string `id`, display `name`, and nullable image-source `avatar`. |
| `chats` | Chat definitions, including participants, phone owner, and appearance. |
| `startNodeId` | The ID of the first node to play. |
| `nodes` | The event graph. Node IDs must be unique; playback follows `next`, not array order. |

IDs are opaque strings. The generator uses the saved project's ID for `story.id` and derives node IDs from existing block and message IDs:

- A block entry: `chat:<encoded block ID>`.
- A message: `message:<encoded block ID>:<encoded message ID>`.
- The final node: `end`.

The encoded parts use `encodeURIComponent`. Readers should use IDs as lookup keys instead of parsing their contents. Re-exporting or moving existing blocks keeps their node IDs; recreating blocks or messages can create new IDs.

## Chats and appearance

Each chat has `id`, `title`, `participantIds`, `ownerId`, and `settings`. Participants reference characters, include at least two distinct people, and must include the phone owner. The owner's messages appear on the right. Other participants appear on the left, with sender names in group chats.

Settings may be omitted or partially supplied when authoring a file; omitted values use these defaults. Supplied values are validated.

| Setting | Type / allowed values | Default |
| --- | --- | --- |
| `time` | Clock time, `HH:mm` | `"09:41"` |
| `battery` | Integer, 1–100 | `100` |
| `signalStrength` | Integer, 0–4 | `4` |
| `wifiStrength` | Integer, 0–3; 0 means off | `3` |
| `theme` | `"blue"` or `"green"` | `"blue"` |
| `darkMode` | Boolean | `false` |
| `screenWidth` | Integer, 300–600 | `375` |
| `showAvatar` | Boolean | `true` |
| `showFrame` | Boolean | `false` |
| `cropImages` | Boolean | `false` |
| `avatar` | Group avatar image source or `null` | `null` |

Character avatars are shared by character ID. A chat's optional `settings.avatar` supplies its group avatar.

## Node types

### Chat

```json
{ "id": "chat:block-1", "type": "chat", "chatId": "chat-1", "next": "message:block-1:m-1" }
```

Activates a chat, using its phone owner and appearance. The generator emits a chat node at the start of each script block, including a later visit to the same conversation. Previously revealed messages remain in that conversation's history.

An optional `status` object overrides `time`, `battery`, `signalStrength`, or `wifiStrength` for that visit, using the types and limits above. Other fields are rejected. Each chat node replaces that chat's previous visit overrides; omitted fields use the chat's settings. Seeking restores the latest visited status for each chat.

### Message

```json
{
  "id": "message:block-1:m-1",
  "type": "message",
  "chatId": "chat-1",
  "message": {
    "id": "m-1",
    "type": "text",
    "sender": "sarah",
    "content": "Ready?",
    "altText": ""
  },
  "next": "end"
}
```

`message.type` is `text`, `timestamp`, `image`, or `image-placeholder`. `content` holds the text, timestamp label, image source, or placeholder description. `altText` is an image description; use an empty string when it does not apply.

Timestamps have `sender: null`. Every other sender must belong to the referenced chat. Message IDs must be unique within a chat; different chats may reuse a message ID. Graph connections always reference the enclosing node's ID.

Incoming messages appear after a typing delay. A message from the active phone owner waits for **Send** or **Enter**. The text is scripted; the reader does not compose or change it. A message node also identifies its chat, so an importer can play it without a preceding chat node.

The player keeps chat navigation separate from the graph. Its back arrow lists reached chats and their revealed messages. An incoming message received outside the open conversation creates an unread notification; the next step waits until that chat is opened. Leading timestamps do not cause an automatic switch to a chat whose first message is incoming. Opening an older chat changes the view without replaying messages or changing the graph's position.

### End

```json
{ "id": "end", "type": "end" }
```

Ends playback. An end node has no `next` field. Chat and message nodes require `next`, containing either another node's ID or `null`; `null` also ends the path.

### Choice (version 2)

```json
{
  "id": "choice:invitation",
  "type": "choice",
  "chatId": "chat-1",
  "options": [
    { "id": "yes", "text": "Yes. Where?", "next": "reply:yes" },
    { "id": "no", "text": "Sorry, I can't.", "next": "reply:no" }
  ]
}
```

A choice has at least two distinct options and no `next` field. Option IDs must be unique within the choice; text is a nonempty reply label and `next` names an existing node. Playback waits at an unresolved choice. Selecting an option prepares its reply; **Send** posts the reply and follows the branch.

Each option must point directly to a text message in the same chat, sent by its phone owner, with content matching the option's text. The generator creates these reply messages and links them to their destination scenes. Scene names are authoring labels; the player follows node IDs. Version 1 files cannot contain choices.

## Minimal complete example

```json
{
  "format": "chat-story-player",
  "version": 1,
  "story": { "id": "movie-night", "title": "Movie night" },
  "characters": [
    { "id": "user", "name": "User", "avatar": null },
    { "id": "sarah", "name": "Sarah", "avatar": null }
  ],
  "chats": [
    {
      "id": "chat-1",
      "title": "Sarah",
      "participantIds": ["user", "sarah"],
      "ownerId": "user"
    }
  ],
  "startNodeId": "chat:block-1",
  "nodes": [
    { "id": "chat:block-1", "type": "chat", "chatId": "chat-1", "next": "message:block-1:m-1" },
    {
      "id": "message:block-1:m-1",
      "type": "message",
      "chatId": "chat-1",
      "message": { "id": "m-1", "type": "text", "sender": "sarah", "content": "Ready?", "altText": "" },
      "next": "message:block-1:m-2"
    },
    {
      "id": "message:block-1:m-2",
      "type": "message",
      "chatId": "chat-1",
      "message": { "id": "m-2", "type": "text", "sender": "user", "content": "Let's go!", "altText": "" },
      "next": "end"
    },
    { "id": "end", "type": "end" }
  ]
}
```

## Validation and media

References must resolve to existing characters, chats, and nodes. A reachable path must contain playable messages. Cycles are rejected across every edge, including unreachable nodes and choice alternatives. Unreachable nodes are validated but are not played. Linear generator exports form one chain; branching exports include every authored alternative and explicit joins.

The player accepts supported image data URLs, including SVG, or HTTP(S) image URLs. It renders them through image elements and never inserts their contents as HTML. Export resolves editor `local:` cache references and embeds browser blob images, so those temporary references do not appear in a player file. External URLs still require a connection and an available host.

Invalid imports show an error and keep the currently loaded story intact. Editor backups and player exports have different schemas: keep a story backup for editing, and use this format for playback.

## Timeline and seeking

Playback traces a route from `startNodeId` through explicit links and recorded choice selections, stopping at unresolved choices. The timeline displays the reachable graph, including forks and merges, while marking the chosen route. Targets use **node IDs**, with `null` representing the beginning; card indices are only a UI mapping.

The map uses cards at 70% zoom and above, dots from 25%, compact chat visits from 8%, and a choices overview below 8%. Compact visits show labeled segments, message counts, and endpoints. The overview contracts message runs into links between choices, joins, and endpoints, preserving separate alternative edges and the current-position marker. Scale and spacing continue shrinking down to 2%; intermediate ranks remain ordered for cursor anchoring. Clicking a segment zooms into it without seeking; cards, dots, and reached choices seek. See the [README](../README.md#play-a-story) for controls.

`PlaybackEngine.seekTo(nodeId)` validates the target before rebuilding session state through that moment. It restores only the selected route's messages, chat activity, section status, and decisions. Seeking back to a choice clears its selection and subsequent decisions, allowing another route. The controller cancels pending timers and clears later notifications and scroll positions. Seeking preserves a manual pause; seeking backward from a completed story continues playback.

Route resolution is shared by playback and seeking. `layoutTimelineGraph` accepts moments and outgoing connections keyed by node ID, separately from the playback route. It assigns topological levels, separates forks into lanes, and places merges below their parents. It rejects missing targets and loops. `groupTimelineVisits` groups only uninterrupted message chains in one chat: returns, choice nodes, forks, and merges remain separate. `projectTimeline` maps this logical model into the current detail level, keeping branch labels apart. Zoom anchoring interpolates between the same logical ranks across detail changes. Padding around the map allows cursor anchoring even when the story is smaller than the viewport. The renderer only mounts points and links near the visible viewport.

## Compatibility and extensions

The player continues to accept version 1 linear stories. Version 2 adds explicit choices without changing chat or message records. Mutually exclusive paths keep separate histories, including after they merge. Variables, conditions, loops, and persistent game saves remain future extensions.
