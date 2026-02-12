# Discord Gateway Events & API Capabilities Audit: A Technical Compendium

## 1. Architectural Overview of the Discord Interface v10

The Discord Platform API, currently standardized on version 10 (v10), represents a sophisticated distributed system interface designed to facilitate high-concurrency interaction between third-party applications (bots) and Discord\'s internal microservices infrastructure. The architecture bifurcates into two distinct but complementary layers: a stateful, persistent WebSocket connection known as the **Gateway**, and a transactional, stateless interface known as the **HTTP/REST API**.^1^ This dual-layer approach allows for the segregation of real-time event streaming from resource manipulation, optimizing bandwidth and processing latency for millions of concurrent connections.

At the core of v10 is a philosophical shift toward granular access control and privacy-by-design. Unlike earlier iterations (v6/v7) which operated on a \"firehose\" principle---broadcasting all server events to all connected clients---v10 enforces a **Principle of Least Privilege** through the implementation of Gateway Intents.^2^ This architectural constraint requires developers to explicitly define the scope of data ingress during the initial handshake, reducing unnecessary infrastructure load and protecting sensitive user data behind strict verification gates.

The system\'s resilience is governed by complex rate-limiting algorithms, encompassing global, per-route, and resource-specific buckets, alongside strict payload serialization rules (JSON/ETF).^3^ For systems architects and developers utilizing wrappers like **discord.py**, understanding the nuances of these layers---specifically the disparity between cached state and raw socket events---is critical for building scalable, compliant applications.^4^

## 2. The Gateway Protocol: Connection Lifecycle and Mechanics

### 2.1 The WebSocket Handshake and OpCode State Machine

The Gateway is the primary conduit for receiving real-time data. Connections are established via secure WebSockets (wss://gateway.discord.gg/) and governed by a rigid OpCode-based state machine.^3^ The lifecycle of a connection is deterministic:

1.  **Connection Open:** The client establishes a TCP connection and performs a TLS handshake.

2.  **Hello (OpCode 10):** Immediately upon connection, the Gateway transmits an OpCode 10 payload. This critical frame contains the heartbeat_interval (in milliseconds), dictating the frequency at which the client must acknowledge the session\'s liveness.^5^

3.  **Identification (OpCode 2):** To upgrade the connection to an authenticated session, the client sends an Identify payload. This payload serves multiple functions: it authenticates the bot via its token, declares the **Intents Bitfield** (defining subscribed events), sets presence data, and specifies client properties (OS, browser, device).^1^

4.  **Ready (OpCode 0):** Upon successful authentication and intent validation, the Gateway dispatches a READY event. This is typically the largest single payload in the session lifecycle, containing the bot\'s user object, session ID, and a list of guilds the bot is a member of (initially marked as unavailable to facilitate lazy loading).^5^

### 2.2 Payload Serialization and Transport Limits

Gateway payloads act as the envelope for all data exchange.

-   **Format:** Payloads must be serialized in plain-text JSON or binary ETF (Erlang Term Format). While ETF offers performance benefits for high-throughput systems, JSON remains the standard for most community libraries, including discord.py.^3^

-   **Size Constraints:** Clients are strictly limited to sending payloads no larger than **4096 bytes**. Exceeding this limit triggers a connection termination with close code 4002 (Decode Error) or 4008 (Rate Limited), depending on the nature of the violation.^3^

-   **Compression:** To mitigate bandwidth consumption, particularly during the READY sequence and GUILD_CREATE streams, v10 supports Zlib-stream compression. This allows the Gateway to send compressed chunks that the client inflates locally, significantly reducing ingress traffic.^6^

### 2.3 Heartbeating and Zombie Connections

The heartbeat_interval provided in the Hello payload is not merely a suggestion; it is a strict requirement. The client must transmit Heartbeat (OpCode 1) payloads at this interval (with randomized jitter) to maintain the session.^5^ Failure to heartbeat results in the Gateway severing the connection (Zombie Connection). The Gateway acknowledges these heartbeats with OpCode 11 (Heartbeat ACK). Sophisticated libraries like discord.py monitor the latency between Sending OpCode 1 and receiving OpCode 11 to calculate the \"Gateway Latency,\" a vital metric for assessing connection health.^7^

## 3. The Intents System: Bitfields and Access Control

Intents are the mechanism by which developers subscribe to \"buckets\" of Gateway events. Technically, an intent is a flag in a bitfield sent during the Identify handshake. If the bit corresponding to a specific intent is not set, the Gateway will simply not transmit the associated Dispatch events, effectively silencing that data stream.^2^

### 3.1 Standard Intents

Standard intents cover the vast majority of non-sensitive functional data. These can be enabled by any developer without special approval.

-   **GUILDS (1 \<\< 0):** The foundational intent. It governs the structural lifecycle of servers, triggering events like GUILD_CREATE, GUILD_UPDATE, GUILD_DELETE, CHANNEL_CREATE, CHANNEL_UPDATE, THREAD_CREATE, and STAGE_INSTANCE_CREATE.^8^

-   **GUILD_BANS (1 \<\< 2):** Subscribes to GUILD_BAN_ADD and GUILD_BAN_REMOVE.

-   **GUILD_VOICE_STATES (1 \<\< 7):** Critical for voice bots, this triggers VOICE_STATE_UPDATE whenever a user joins, leaves, or moves between voice channels.^8^

-   **GUILD_MESSAGES (1 \<\< 9):** Enables the reception of MESSAGE_CREATE, MESSAGE_UPDATE, and MESSAGE_DELETE events in guild channels. *Crucially, enabling this intent does NOT grant access to the message content itself (text body), only the message object metadata, unless the Privileged Message Content Intent is also approved*.^9^

-   **GUILD_MESSAGE_REACTIONS (1 \<\< 10):** Triggers events for reaction additions and removals.

-   **DIRECT_MESSAGES (1 \<\< 12):** Subscribes to message events within Direct Message (DM) channels.

### 3.2 Privileged Intents: The Security Barrier

Three specific intents are classified as \"Privileged\" because they expose data that allows for passive surveillance of user populations (e.g., tracking online status, scraping member lists, reading private chats). Access to these intents is gated.^10^

#### 3.2.1 GUILD_MEMBERS (1 \<\< 1)

-   **Function:** Controls access to the member list. Without this, the GUILD_CREATE payload will only include the bot itself and users currently in voice channels. The member list is effectively invisible.

-   **Events Enabled:** GUILD_MEMBER_ADD (joins), GUILD_MEMBER_UPDATE (role/nick changes), GUILD_MEMBER_REMOVE (leaves/kicks).^12^

-   **Implications:** Essential for moderation bots (tracking joins), role management bots, and logging bots. Without it, caching members is impossible.

#### 3.2.2 GUILD_PRESENCES (1 \<\< 8)

-   **Function:** Controls access to user states.

-   **Events Enabled:** PRESENCE_UPDATE. This event fires whenever a user goes online/offline, changes status (idle/dnd), or updates their activity (playing a game, Spotify, custom status).

-   **Cost:** This is the most bandwidth-heavy intent. In large servers, presence updates can flood the websocket with thousands of events per second. Discord advises disabling this unless absolutely necessary.^2^

#### 3.2.3 MESSAGE_CONTENT (1 \<\< 15)

-   **Function:** Unlike other intents that control *which* events are sent, this intent controls *what data is inside* the event.

-   **Redaction:** Without this intent, the content, embeds, attachments, and components fields in MESSAGE_CREATE payloads will be empty strings or arrays.

-   **Exceptions:** Bots always receive content for:

    -   Messages the bot sends.

    -   DMs sent to the bot.

    -   Messages explicitly mentioning the bot.^9^

### 3.3 Verification and Scaling Limitations (75+ vs. 100+ Guilds)

The transition from a development bot to a production application involves a strict verification hierarchy enforced by Discord.^9^

-   **The 75-Server Threshold:** Once a bot joins 75 guilds, the \"App Verification\" tab in the Developer Portal unlocks. Developers are strongly urged to apply immediately at this stage. The review process involves submitting government-issued ID (via Stripe Identity) and detailing the bot\'s functionality.^14^

-   **The 100-Server Hard Cap:**

    -   **Invite Lock:** If a bot reaches 100 servers without verification, it enters a locked state where it **cannot be invited to any new servers**.

    -   **Privileged Intent Lock:** For unverified bots over 100 servers, privileged intents are revoked. Even if toggled \"on\" in the portal, the Gateway will close the connection with code 4014 (Disallowed Intents) if the bot attempts to identify with them.

    -   **Whitelisting:** Upon verification, the developer must justify each privileged intent. \"Generic logging\" is frequently denied for Message Content; the use case must be unique and compelling (e.g., AI analysis, auto-moderation based on text patterns).^15^

## 4. Comprehensive Gateway Events Inventory (v10)

This section provides an exhaustive audit of the Dispatch Events (OpCode 0) transmitted by the v10 Gateway. The inventory maps each event to its required intent and details the schema of the payload d (data) field.^8^

### 4.1 Guild Lifecycle Events

These events track the existence and metadata of the server itself.

+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+
| **Event Name**        | **Required Intent**   | **Payload Data Structure & Key Fields**                                                                             |
+=======================+=======================+=====================================================================================================================+
| **GUILD_CREATE**      | GUILDS                | Sent when the bot lazily loads a guild, joins a new guild, or a guild recovers from outage.                         |
|                       |                       |                                                                                                                     |
|                       |                       | **Fields:** Full Guild object including id, name, roles (array), emojis (array), channels (array), threads (array). |
|                       |                       |                                                                                                                     |
|                       |                       | *Note: members and presences arrays are restricted based on Privileged Intents.* ^17^                               |
+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+
| **GUILD_UPDATE**      | GUILDS                | Sent when guild details change.                                                                                     |
|                       |                       |                                                                                                                     |
|                       |                       | **Fields:** id, name, icon, owner_id, banner, splash, discovery_splash.                                             |
+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+
| **GUILD_DELETE**      | GUILDS                | Sent when the bot is removed, leaves, or the guild becomes unavailable.                                             |
|                       |                       |                                                                                                                     |
|                       |                       | **Fields:** id, unavailable (boolean). If unavailable is true, it indicates a Discord outage, not a removal. ^17^   |
+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+
| **GUILD_ROLE_CREATE** | GUILDS                | A role is created.                                                                                                  |
|                       |                       |                                                                                                                     |
|                       |                       | **Fields:** guild_id, role (Role object).                                                                           |
+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+
| **GUILD_ROLE_UPDATE** | GUILDS                | A role is modified.                                                                                                 |
|                       |                       |                                                                                                                     |
|                       |                       | **Fields:** guild_id, role (Role object).                                                                           |
+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+
| **GUILD_ROLE_DELETE** | GUILDS                | A role is deleted.                                                                                                  |
|                       |                       |                                                                                                                     |
|                       |                       | **Fields:** guild_id, role_id.                                                                                      |
+-----------------------+-----------------------+---------------------------------------------------------------------------------------------------------------------+

### 4.2 Channel & Thread Events

These events track the structure of communication pathways within a guild.

+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **Event Name**            | **Required Intent**   | **Payload Data Structure & Key Fields**                                                               |
+===========================+=======================+=======================================================================================================+
| **CHANNEL_CREATE**        | GUILDS                | A new channel is created.                                                                             |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** Full Channel object (id, type, name, parent_id, permission_overwrites).                   |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **CHANNEL_UPDATE**        | GUILDS                | Channel metadata updates (topic, slowmode, permissions).                                              |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** Channel object.                                                                           |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **CHANNEL_DELETE**        | GUILDS                | A channel is deleted.                                                                                 |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** Channel object.                                                                           |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **CHANNEL_PINS_UPDATE**   | GUILDS / DM           | A message is pinned/unpinned.                                                                         |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** guild_id, channel_id, last_pin_timestamp.                                                 |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **THREAD_CREATE**         | GUILDS                | A thread is created or the bot is added to a private thread.                                          |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** Channel object (thread type).                                                             |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **THREAD_UPDATE**         | GUILDS                | Thread metadata changes (archive status, lock status).                                                |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** Channel object.                                                                           |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **THREAD_DELETE**         | GUILDS                | A thread is deleted.                                                                                  |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** id, guild_id, parent_id, type.                                                            |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **THREAD_LIST_SYNC**      | GUILDS                | Sent when the bot gains access to a channel and needs to sync existing threads.                       |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** guild_id, channel_ids (parents), threads (array), members (array of thread members). ^18^ |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **THREAD_MEMBER_UPDATE**  | GUILDS                | The bot\'s own thread membership is updated.                                                          |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** id (thread id), user_id, join_timestamp, flags.                                           |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+
| **THREAD_MEMBERS_UPDATE** | GUILD_MEMBERS\*       | Users are added/removed from a thread.                                                                |
|                           |                       |                                                                                                       |
|                           |                       | **Fields:** id, guild_id, member_count, added_members (array), removed_member_ids (array).            |
|                           |                       |                                                                                                       |
|                           |                       | *Without GUILD_MEMBERS, this is only sent if the bot is affected.* ^18^                               |
+---------------------------+-----------------------+-------------------------------------------------------------------------------------------------------+

### 4.3 Member & User Events (Privileged)

Strictly gated by GUILD_MEMBERS.

+-------------------------+-----------------------+----------------------------------------------------------------------------------+
| **Event Name**          | **Required Intent**   | **Payload Data Structure & Key Fields**                                          |
+=========================+=======================+==================================================================================+
| **GUILD_MEMBER_ADD**    | GUILD_MEMBERS         | A user joins the guild.                                                          |
|                         |                       |                                                                                  |
|                         |                       | **Fields:** guild_id, user object, roles, joined_at, avatar, nick. ^19^          |
+-------------------------+-----------------------+----------------------------------------------------------------------------------+
| **GUILD_MEMBER_REMOVE** | GUILD_MEMBERS         | A user leaves, is kicked, or is banned.                                          |
|                         |                       |                                                                                  |
|                         |                       | **Fields:** guild_id, user object.                                               |
+-------------------------+-----------------------+----------------------------------------------------------------------------------+
| **GUILD_MEMBER_UPDATE** | GUILD_MEMBERS\*       | A user\'s guild profile changes (roles, nick).                                   |
|                         |                       |                                                                                  |
|                         |                       | **Fields:** guild_id, roles, user, nick, avatar, joined_at.                      |
|                         |                       |                                                                                  |
|                         |                       | *Note: Triggers without intent for the bot\'s own profile.*                      |
+-------------------------+-----------------------+----------------------------------------------------------------------------------+
| **GUILD_MEMBERS_CHUNK** | *None*                | The response to a Request Guild Members (OpCode 8) command.                      |
|                         |                       |                                                                                  |
|                         |                       | **Fields:** guild_id, members (array), chunk_index, chunk_count, not_found. ^19^ |
+-------------------------+-----------------------+----------------------------------------------------------------------------------+
| **USER_UPDATE**         | *None*                | The bot\'s own user object changes (username, avatar).                           |
|                         |                       |                                                                                  |
|                         |                       | **Fields:** User object.                                                         |
+-------------------------+-----------------------+----------------------------------------------------------------------------------+

### 4.4 Message & Interaction Events

High-volume events governing chat.

+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **Event Name**              | **Required Intent**     | **Payload Data Structure & Key Fields**                                              |
+=============================+=========================+======================================================================================+
| **MESSAGE_CREATE**          | GUILD_MESSAGES          | A message is sent.                                                                   |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** id, channel_id, guild_id, author, content*, embeds*, attachments\*.      |
|                             |                         |                                                                                      |
|                             |                         | *Fields marked with \* are empty without MESSAGE_CONTENT intent.* ^9^                |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **MESSAGE_UPDATE**          | GUILD_MESSAGES          | A message is edited.                                                                 |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** id, channel_id, partial Message object.                                  |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **MESSAGE_DELETE**          | GUILD_MESSAGES          | A message is deleted.                                                                |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** id, channel_id, guild_id. *Does not contain content.*                    |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **MESSAGE_DELETE_BULK**     | GUILD_MESSAGES          | Multiple messages deleted.                                                           |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** ids (array of snowflakes), channel_id, guild_id.                         |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **MESSAGE_REACTION_ADD**    | GUILD_MESSAGE_REACTIONS | A reaction is added.                                                                 |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** user_id, channel_id, message_id, emoji (partial).                        |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **MESSAGE_REACTION_REMOVE** | GUILD_MESSAGE_REACTIONS | A reaction is removed.                                                               |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** user_id, channel_id, message_id, emoji.                                  |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **INTERACTION_CREATE**      | *None*                  | A slash command or component is used.                                                |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** id, type, data (command info), guild_id, channel_id, member, token. ^18^ |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+
| **TYPING_START**            | GUILD_MESSAGE_TYPING    | A user starts typing.                                                                |
|                             |                         |                                                                                      |
|                             |                         | **Fields:** channel_id, guild_id, user_id, timestamp. ^3^                            |
+-----------------------------+-------------------------+--------------------------------------------------------------------------------------+

### 4.5 Moderation, Audit & Safety Events

+--------------------------------------+-------------------------------+---------------------------------------------------------------------------------+
| **Event Name**                       | **Required Intent**           | **Payload Data Structure & Key Fields**                                         |
+======================================+===============================+=================================================================================+
| **GUILD_AUDIT_LOG_ENTRY_CREATE**     | GUILD_MODERATION              | An audit log entry is created.                                                  |
|                                      |                               |                                                                                 |
|                                      |                               | **Fields:** guild_id, action_type, user_id, target_id, changes (array), reason. |
|                                      |                               |                                                                                 |
|                                      |                               | *Requires VIEW_AUDIT_LOG permission.* ^20^                                      |
+--------------------------------------+-------------------------------+---------------------------------------------------------------------------------+
| **GUILD_BAN_ADD**                    | GUILD_MODERATION              | A user is banned.                                                               |
|                                      |                               |                                                                                 |
|                                      |                               | **Fields:** guild_id, user object.                                              |
+--------------------------------------+-------------------------------+---------------------------------------------------------------------------------+
| **GUILD_BAN_REMOVE**                 | GUILD_MODERATION              | A user is unbanned.                                                             |
|                                      |                               |                                                                                 |
|                                      |                               | **Fields:** guild_id, user object.                                              |
+--------------------------------------+-------------------------------+---------------------------------------------------------------------------------+
| **AUTO_MODERATION_RULE_CREATE**      | AUTO_MODERATION_CONFIGURATION | A rule is created.                                                              |
|                                      |                               |                                                                                 |
|                                      |                               | **Fields:** Auto Moderation Rule object.                                        |
+--------------------------------------+-------------------------------+---------------------------------------------------------------------------------+
| **AUTO_MODERATION_ACTION_EXECUTION** | AUTO_MODERATION_EXECUTION     | AutoMod blocks content.                                                         |
|                                      |                               |                                                                                 |
|                                      |                               | **Fields:** guild_id, action, rule_id, user_id, matched_keyword, content. ^22^  |
+--------------------------------------+-------------------------------+---------------------------------------------------------------------------------+

### 4.6 Presence & Voice Events

+------------------------+-----------------------+-----------------------------------------------------------------------------------------------------------------------------------------+
| **Event Name**         | **Required Intent**   | **Payload Data Structure & Key Fields**                                                                                                 |
+========================+=======================+=========================================================================================================================================+
| **PRESENCE_UPDATE**    | GUILD_PRESENCES       | User status/activity changes.                                                                                                           |
|                        |                       |                                                                                                                                         |
|                        |                       | **Fields:** user (partial), guild_id, status, activities (array), client_status. ^23^                                                   |
+------------------------+-----------------------+-----------------------------------------------------------------------------------------------------------------------------------------+
| **VOICE_STATE_UPDATE** | GUILD_VOICE_STATES    | User joins/leaves voice.                                                                                                                |
|                        |                       |                                                                                                                                         |
|                        |                       | **Fields:** guild_id, channel_id, user_id, session_id, deaf, mute, self_deaf, self_mute, self_stream (Go Live status), self_video. ^24^ |
+------------------------+-----------------------+-----------------------------------------------------------------------------------------------------------------------------------------+

### 4.7 2025/2026 Roadmap Events

Recent and upcoming additions to the v10 API.^5^

  ---------------------------------------------------------------------------------------------------------------------------------------------------
  **Event Name**                      **Required Intent**     **Description**
  ----------------------------------- ----------------------- ---------------------------------------------------------------------------------------
  **GUILD_SOUNDBOARD_SOUND_CREATE**   GUILDS                  A new custom sound is added to the guild soundboard. Payload: SoundboardSound object.

  **GUILD_SOUNDBOARD_SOUND_DELETE**   GUILDS                  A sound is removed.

  **MESSAGE_POLL_VOTE_ADD**           GUILD_MESSAGE_POLLS     A user votes in a poll.

  **MESSAGE_POLL_VOTE_REMOVE**        GUILD_MESSAGE_POLLS     A user removes a vote.

  **ENTITLEMENT_CREATE**              *None*                  A user purchases a premium app subscription. Payload: Entitlement object. ^26^
  ---------------------------------------------------------------------------------------------------------------------------------------------------

## 5. REST API: Supplementary Data and Rate Limits

While the Gateway streams changes, the REST API is the authority for historical state and transactional operations.

### 5.1 REST Resource Metadata Models

The data models returned by REST endpoints provide the \"source of truth\" often needed to backfill cache misses.

#### 5.1.1 The Channel Object (GET /channels/{id})

This resource represents all channel types (Text, Voice, Thread, Forum).

-   **Core Fields:** id, type, guild_id, position, permission_overwrites, name, topic, nsfw.

-   **Threads:** message_count, member_count, thread_metadata (archived, locked, auto_archive_duration).

-   **Forum Specifics:** available_tags (array), default_reaction_emoji, default_sort_order.^27^

#### 5.1.2 The Guild Object (GET /guilds/{id})

-   **Identity:** name, icon, splash, banner, description.

-   **Configuration:** verification_level, default_message_notifications, explicit_content_filter, mfa_level.

-   **Counts:** approximate_member_count, approximate_presence_count.

-   **Collections:** roles (full list), emojis (full list), features (array of strings like COMMUNITY, PARTNERED).^1^

#### 5.1.3 The User Object (GET /users/{id})

-   **Identity:** id, username, discriminator (if legacy), global_name (display name), avatar, banner, accent_color.

-   **Flags:** public_flags (bitfield for badges like HypeSquad, Active Developer), bot (boolean), system (boolean).

-   **Decorations:** avatar_decoration_data (new field for profile effects).^29^

#### 5.1.4 The Webhook Object (GET /webhooks/{id})

-   **Fields:** id, type, guild_id, channel_id, user (creator), name, avatar, token (secure token for incoming webhooks), application_id.^30^

### 5.2 The Rate Limit Architecture

Discord\'s rate limiting is a complex, multilayered system designed to prevent abuse while ensuring fairness.^31^

#### 5.2.1 The Token Bucket Algorithm

Rate limits are communicated via HTTP headers in the response.

-   X-RateLimit-Limit: The total request capacity of the bucket.

-   X-RateLimit-Remaining: The number of requests remaining.

-   **X-RateLimit-Reset-After**: The specific time (in seconds, with millisecond precision) until the bucket refills. This is the most critical header for implementing backoff logic.

-   X-RateLimit-Bucket: A unique hash string identifying the bucket.

#### 5.2.2 Scopes of Limiting

1.  **Per-Route (Shared Resource):** Limits are often grouped by the top-level resource. For example, POST /channels/{id}/messages limits are specific to that channel ID. Sending messages to Channel A does not consume the quota for Channel B.

2.  **Global Limit:** There is a hard cap of **50 requests per second** per bot token across the entire API. This is tracked via X-RateLimit-Global.^32^

3.  **Invalid Request Limit (The \"Cloudflare Ban\"):** This is a critical operational hazard. If a bot generates **10,000 invalid requests** (401, 403, 404) within 10 minutes, the bot\'s IP address is temporarily banned by Cloudflare at the network edge. This severs all connectivity, including the Gateway.^32^

## 6. discord.py Specifics: Caching Strategy and Raw Events

discord.py is a high-level wrapper that abstracts the Gateway interactions. However, its reliance on an internal cache creates specific challenges for developers needing comprehensive data visibility.

### 6.1 The Cache Dependency Problem

Standard discord.py events like on_message_delete(message) rely on the message object existing in the library\'s internal cache (typically a deque limited to 1000-5000 messages).

-   **The Scenario:** A bot restarts, clearing its RAM. A user then deletes a message sent 24 hours ago.

-   **The Failure:** The Gateway sends a MESSAGE_DELETE payload. discord.py checks its cache for the message_id. Finding nothing, it drops the event silently. The on_message_delete event never fires.

### 6.2 Raw Event Listeners

To circumvent cache dependency, discord.py exposes **Raw Events**. These are dispatched for *every* relevant Gateway payload, regardless of cache state.^33^

-   **on_raw_message_delete(payload)**:

    -   **Payload:** RawMessageDeleteEvent. Contains message_id, channel_id, guild_id.

    -   **Usage:** Allows the bot to acknowledge the deletion. To log the content, the bot must have previously stored the message text in an external database (e.g., PostgreSQL/MongoDB) indexed by message_id.

-   **on_raw_reaction_add(payload)**:

    -   **Payload:** RawReactionActionEvent.

    -   **Usage:** Essential for \"Reaction Role\" features on persistent messages (e.g., a rules acceptance message sent months ago).

-   **on_socket_raw_receive(msg)**:

    -   **Function:** This listener intercepts the raw, decompressed WebSocket frame before any parsing occurs.

    -   **Use Case:** It is the only way to debug undocumented fields or calculate exact ingress bandwidth usage.

    -   **Warning:** This function sits on the event loop\'s hot path. Any blocking code here (e.g., a synchronous database call) will delay the heartbeat, causing the Gateway to disconnect the bot.^7^

### 6.3 Intent Injection in discord.py

Intents must be explicitly defined during bot initialization to match the Developer Portal settings. A mismatch (e.g., enabling members in code but not in the portal) results in a crash.^35^

Python

import discord\
\
\# Standard Intents\
intents = discord.Intents.default()\
\
\# Privileged Intents (Must be enabled in Portal)\
intents.members = True\
intents.message_content = True\
intents.presences = False \# Disabled to save bandwidth\
\
bot = discord.Bot(intents=intents)

## 7. Algorithms and Derived Metrics

Since the API does not explicitly provide certain metrics (e.g., \"User X joined via Invite Y\"), developers must implement derived logic.

### 7.1 Invite Attribution Algorithm

To determine which invite a user used to join:

1.  **Snapshot:** On on_ready, fetch all invites for the guild via REST (guild.invites()) and cache them in a Map: {code: uses}.

2.  **Trigger:** Listen for the on_member_join event.

3.  **Fetch & Diff:** Immediately fetch the invites again.

4.  **Comparison:** Iterate through the new list. The invite where new_uses \> cached_uses is the attribution target.^36^

5.  **Update:** Update the cache with the new values.

    -   *Limitations:* This logic fails if multiple users join simultaneously (race condition) or if the invite was a temporary one-use link that expired (vanished) upon use.

### 7.2 Data Storage and Volume Estimation

For a standard 500-member community, data volume can be estimated to plan storage infrastructure.^37^

**Packet Size Metrics:**

-   **Ingress (Gateway):** A typical MESSAGE_CREATE event is \~480 bytes + content length.

-   **Egress (REST):** Sending a message involves HTTP overhead and encryption, averaging \~4.5 KB per request.^38^

**Volume Calculation (500 Members):**

Assuming a moderately active server generating 10 messages/minute:

-   **Daily Messages:** 10 \* 60 \* 24 = 14,400 messages.

-   **Daily Ingress:** 14,400 \* 600 bytes ≈ **8.6 MB** of JSON data.

-   **Storage (Database):** Storing id, author_id, content, timestamp requires \~1 KB per row.

-   **Monthly Storage:** 14,400 \* 30 \* 1 KB ≈ **432 MB** per month per server.

## 8. Limitations, Gotchas, and 2026 Outlook

### 8.1 Technical Limitations

-   **Ephemeral Messages:** Interaction responses (\"Only you can see this\") are ephemeral. They do not trigger MESSAGE_CREATE and are not retrievable via the API. They exist solely in the client\'s transient state.

-   **Audit Log Retention:** Discord retains audit logs for exactly **45 days**. There is no API capability to fetch logs older than this window.^21^

-   **Message History:** While messages are stored indefinitely, fetching them is slow. The GET /messages endpoint retrieves batches of 100. Backfilling a channel with 100,000 messages requires 1,000 sequential requests, heavily throttled by rate limits.

### 8.2 Future Outlook (2025/2026 Roadmap)

-   **Permission Splits (Feb 2026):** Discord is deprecating the monolithic MANAGE_MESSAGES permission for specific actions. Bots will need to request PIN_MESSAGES to pin and CREATE_EXPRESSIONS to manage emojis.^39^

-   **DAVE Protocol (2026):** Discord Audio/Video End-to-End Encryption (DAVE) is rolling out. This will fundamentally change how voice bots operate, as the audio stream will be encrypted client-side. Bots needing to record or transcribe audio will likely require new, verified implementations to access decryption keys.^25^

-   **Global Age Verification (March 2026):** Discord is enforcing age verification globally. This shifts the burden of \"age-gating\" entirely to the platform. Bots should rely on the nsfw channel flag rather than attempting to implement custom age-verification flows, as the underlying user age data remains private.^40^

This audit underscores that the Discord API v10 is a mature, security-focused environment. Success requires not just code, but a holistic adherence to verification protocols, efficient data handling, and forward-looking architectural compliance.

#### Works cited

1.  API Reference \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/reference]{.underline}](https://discord.com/developers/docs/reference)

2.  Privileged Intents Best Practices - Developers - Discord, accessed February 12, 2026, [[https://support-dev.discord.com/hc/en-us/articles/6177533521047-Privileged-Intents-Best-Practices]{.underline}](https://support-dev.discord.com/hc/en-us/articles/6177533521047-Privileged-Intents-Best-Practices)

3.  Gateway \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway]{.underline}](https://discord.com/developers/docs/events/gateway)

4.  API Reference - Discord.py, accessed February 12, 2026, [[https://discordpy.readthedocs.io/en/latest/api.html]{.underline}](https://discordpy.readthedocs.io/en/latest/api.html)

5.  Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events]{.underline}](https://discord.com/developers/docs/events/gateway-events)

6.  Migrating to v2.0 - Discord.py, accessed February 12, 2026, [[https://discordpy.readthedocs.io/en/v2.6.0/migrating.html]{.underline}](https://discordpy.readthedocs.io/en/v2.6.0/migrating.html)

7.  Client Objects - Pycord v2.6 Documentation, accessed February 12, 2026, [[https://docs.pycord.dev/en/v2.6.1/api/clients.html]{.underline}](https://docs.pycord.dev/en/v2.6.1/api/clients.html)

8.  Gateway \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/topics/gateway#list-of-intents]{.underline}](https://discord.com/developers/docs/topics/gateway#list-of-intents)

9.  Message Content Privileged Intent FAQ - Developers - Discord, accessed February 12, 2026, [[https://support-dev.discord.com/hc/en-us/articles/4404772028055-Message-Content-Privileged-Intent-FAQ]{.underline}](https://support-dev.discord.com/hc/en-us/articles/4404772028055-Message-Content-Privileged-Intent-FAQ)

10. What are Privileged Intents? - Developers, accessed February 12, 2026, [[https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents]{.underline}](https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents)

11. Gateway Intents - Bot Designer For Discord - Wiki, accessed February 12, 2026, [[https://wiki.botdesignerdiscord.com/guides/introduction/gatewayIntents.html]{.underline}](https://wiki.botdesignerdiscord.com/guides/introduction/gatewayIntents.html)

12. Gateway \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/topics/gateway#privileged-intents]{.underline}](https://discord.com/developers/docs/topics/gateway#privileged-intents)

13. How do I get Privileged Intents for my bot? - Developers, accessed February 12, 2026, [[https://support-dev.discord.com/hc/en-us/articles/6205754771351-How-do-I-get-Privileged-Intents-for-my-bot]{.underline}](https://support-dev.discord.com/hc/en-us/articles/6205754771351-How-do-I-get-Privileged-Intents-for-my-bot)

14. How to Get Verified Bot Developer Discord Badge (2025) - YouTube, accessed February 12, 2026, [[https://www.youtube.com/watch?v=2txFfDFh21c&vl=en]{.underline}](https://www.youtube.com/watch?v=2txFfDFh21c&vl=en)

15. Has anyone actually gotten Message Content Intent approved lately? Getting really frustrated here\... : r/Discord_Bots - Reddit, accessed February 12, 2026, [[https://www.reddit.com/r/Discord_Bots/comments/1mw624o/has_anyone_actually_gotten_message_content_intent/]{.underline}](https://www.reddit.com/r/Discord_Bots/comments/1mw624o/has_anyone_actually_gotten_message_content_intent/)

16. GatewayDispatchEvents \| API \| discord-api-types documentation, accessed February 12, 2026, [[https://discord-api-types.dev/api/discord-api-types-v10/enum/GatewayDispatchEvents]{.underline}](https://discord-api-types.dev/api/discord-api-types-v10/enum/GatewayDispatchEvents)

17. Gateway Events - Discord Userdoccers, accessed February 12, 2026, [[https://docs.discord.food/topics/gateway-events]{.underline}](https://docs.discord.food/topics/gateway-events)

18. Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events#interaction-create]{.underline}](https://discord.com/developers/docs/events/gateway-events#interaction-create)

19. Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events#guild-member-add]{.underline}](https://discord.com/developers/docs/events/gateway-events#guild-member-add)

20. Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events#guild-audit-log-entry-create]{.underline}](https://discord.com/developers/docs/events/gateway-events#guild-audit-log-entry-create)

21. Audit Logs Resource \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/resources/audit-log]{.underline}](https://discord.com/developers/docs/resources/audit-log)

22. Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events#auto-moderation-rule-create]{.underline}](https://discord.com/developers/docs/events/gateway-events#auto-moderation-rule-create)

23. Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events#voice-state-update]{.underline}](https://discord.com/developers/docs/events/gateway-events#voice-state-update)

24. Voice Resource \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/resources/voice#voice-state-object]{.underline}](https://discord.com/developers/docs/resources/voice#voice-state-object)

25. Change Log \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/change-log]{.underline}](https://discord.com/developers/docs/change-log)

26. Gateway Events \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/events/gateway-events#entitlement-create]{.underline}](https://discord.com/developers/docs/events/gateway-events#entitlement-create)

27. Channels Resource \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/resources/channel#channel-object]{.underline}](https://discord.com/developers/docs/resources/channel#channel-object)

28. Guild Resource \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/resources/guild]{.underline}](https://discord.com/developers/docs/resources/guild)

29. Users Resource \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/resources/user#user-object]{.underline}](https://discord.com/developers/docs/resources/user#user-object)

30. Webhook Resource \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/resources/webhook#webhook-object]{.underline}](https://discord.com/developers/docs/resources/webhook#webhook-object)

31. Rate Limits \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/topics/rate-limits]{.underline}](https://discord.com/developers/docs/topics/rate-limits)

32. My Bot is Being Rate Limited! - Developers - Discord, accessed February 12, 2026, [[https://support-dev.discord.com/hc/en-us/articles/6223003921559-My-Bot-is-Being-Rate-Limited]{.underline}](https://support-dev.discord.com/hc/en-us/articles/6223003921559-My-Bot-is-Being-Rate-Limited)

33. Event Reference - Pycord v2.6 Documentation, accessed February 12, 2026, [[https://docs.pycord.dev/en/stable/api/events.html]{.underline}](https://docs.pycord.dev/en/stable/api/events.html)

34. Event Reference - Pycord v2.6 Documentation, accessed February 12, 2026, [[https://docs.pycord.dev/en/v2.6.1/api/events.html]{.underline}](https://docs.pycord.dev/en/v2.6.1/api/events.html)

35. Discord bot setup issue with Python: Missing Privileged Intents error - Stack Overflow, accessed February 12, 2026, [[https://stackoverflow.com/questions/78431747/discord-bot-setup-issue-with-python-missing-privileged-intents-error]{.underline}](https://stackoverflow.com/questions/78431747/discord-bot-setup-issue-with-python-missing-privileged-intents-error)

36. discordjs-bot-guide/coding-guides/tracking-used-invites.md at master - GitHub, accessed February 12, 2026, [[https://github.com/AnIdiotsGuide/discordjs-bot-guide/blob/master/coding-guides/tracking-used-invites.md]{.underline}](https://github.com/AnIdiotsGuide/discordjs-bot-guide/blob/master/coding-guides/tracking-used-invites.md)

37. How much data does discord use in text chat only? : r/discordapp, accessed February 12, 2026, [[https://reddit.com/r/discordapp/comments/6ulu3b/how_much_data_does_discord_use_in_text_chat_only/]{.underline}](https://reddit.com/r/discordapp/comments/6ulu3b/how_much_data_does_discord_use_in_text_chat_only/)

38. How much data does discord use in text chat only? : r/discordapp - Reddit, accessed February 12, 2026, [[https://www.reddit.com/r/discordapp/comments/6ulu3b/how_much_data_does_discord_use_in_text_chat_only/]{.underline}](https://www.reddit.com/r/discordapp/comments/6ulu3b/how_much_data_does_discord_use_in_text_chat_only/)

39. Change Log \| Documentation \| Discord Developer Portal, accessed February 12, 2026, [[https://discord.com/developers/docs/change-log?topic=HTTP+API]{.underline}](https://discord.com/developers/docs/change-log?topic=HTTP+API)

40. Discord Unveils Global Age Verification Mandate For Users, accessed February 12, 2026, [[https://evrimagaci.org/gpt/discord-unveils-global-age-verification-mandate-for-users-528047]{.underline}](https://evrimagaci.org/gpt/discord-unveils-global-age-verification-mandate-for-users-528047)
