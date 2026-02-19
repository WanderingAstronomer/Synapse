# Cache: Discord Interaction Taxonomy Draft

> **Created:** 2026-02-18
> **Purpose:** Enumerate interaction classes for capture-first architecture and identify current/target coverage.

## Taxonomy Buckets

### A. Message Surface

- Plain text message
- Reply message
- Message edit
- Message delete
- URL-bearing message
- Code block-bearing message
- Mention-bearing message (users/roles/channels)
- Attachment-bearing message
- Inline image paste (often represented as attachment)
- Sticker usage
- Emoji-rich message
- Poll creation / poll vote / poll close (if API-exposed)
- Gift keyboard interactions (if API-exposed)

### B. Reaction Surface

- Reaction add
- Reaction remove
- Reaction target metadata (self vs other, thread/forum context)

### C. Thread/Forum Surface

- Thread create
- Forum post create
- Forum post reply
- Thread archive/unarchive (if exposed)
- Thread lock/unlock (if exposed)

### D. Voice Surface

- Voice join
- Voice leave
- Voice move
- Mute/deafen transitions
- AFK channel transitions
- Session duration and occupancy context

### E. Membership Surface

- Member join
- Member leave
- Member profile updates (if relevant and exposed)

### F. Governance/Moderation Surface (optional future)

- Message pin/unpin
- Channel create/update/delete
- Role changes
- Moderation actions

## Normalized Classification Dimensions

For each captured event, classify by:
- actor (who did it)
- subject (what object was acted on)
- target (who/what was affected)
- container (guild/category/channel/thread/forum)
- content_features (urls/code/attachments/mentions/etc)
- intent_hints (creation/reply/react/acknowledgment)
- timing context (local time bucket, session state)
- anti-gaming signals (velocity, repetition, reciprocal loops)

## Coverage Status Markers

Use this matrix notation while implementing:
- Captured: yes/no/partial
- Normalized: yes/no/partial
- Rule-addressable: yes/no/partial
- Notes: exposed by discord.py? additional fetch required? privacy constraints?

## Rule Firewall Relevance

This taxonomy is not just for analytics; it is the predicate vocabulary for rules.
Examples:
- scope.channel.type == forum
- content_features.has_code_block == true
- content_features.has_attachment == true OR content_features.has_url == true
- interaction.intent == reply
- thread.reply_count_24h > N

## Near-Term Priority Capture Expansions

1. Distinguish forum post create vs forum reply as first-class normalized intents.
2. Expand message feature extraction for mentions/stickers/poll fields where available.
3. Ensure attachment/paste image distinctions are consistently represented.
4. Build explicit “availability matrix” for interactions not exposed by library/gateway.
