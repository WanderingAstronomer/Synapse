# What Is Synapse?

Most Discord bots approach community management the same way: give members points for posting, display a leaderboard, and call it engagement. That works for simple cases. It stops working the moment your community has its own culture, its own definition of meaningful participation, or any need to distinguish between different kinds of activity.

Synapse is built around a different assumption. Your community is not generic, and the software supporting it should not be either.

---

## What Synapse Does

Synapse is a community operating system for Discord. It records every significant activity in your server, including messages, reactions, voice sessions, poll responses, and thread contributions. It then passes that activity through a rule engine you configure, decides what to reward, and stores the results in a persistent database.

The result is a server where participation is measured, engagement is rewarded according to rules that reflect your values, and every member can see exactly how the system evaluated their activity.

---

## The Rule Engine

The central feature of Synapse is its rule engine. Rather than a list of configuration values with sliders and checkboxes, Synapse lets administrators define structured rules that express intent. A rule can say: reward this type of activity, in this channel, at this rate, but apply diminishing returns after a threshold, and multiply the reward during a seasonal event window. Multiple conditions can combine. Outcomes can include XP, currency, achievement triggers, or role assignments.

This approach was inspired by how industrial-grade firewalls and routers handle traffic policy. A network firewall does not have a single "how strict should we be" dial. It has a ruleset: ordered, composable conditions matched against every packet, each producing a defined outcome. Synapse applies the same model to community activity. Each event entering the system is evaluated against your published ruleset in order, and the matching rules determine the outcome.

The rule builder is a structured form in the browser. Administrators do not write code or edit JSON. Before publishing any ruleset, a simulation mode replays your recent real activity against the draft rules and displays a side-by-side comparison of current rewards versus what the proposed rules would have produced. Changes go live only after you have reviewed the projected impact.

---

## Features

### Engagement Economy

Synapse tracks two currencies internally, referred to as XP and Gold in the database. Administrators can rename both to anything that fits their community. Members earn currency and XP through activity at rates determined by the active ruleset. Currency can be spent in the marketplace.

### Achievements

Achievements are built as composable units called crates. Each crate combines a behavior strategy, such as reaching a score threshold, maintaining a streak, or receiving a set number of peer reactions, with a visual identity including rarity tier, seasonal frame, and custom artwork. Administrators build these through a form-based editor. The achievement system is wired into the rule engine, so triggering an achievement is just another outcome type a rule can produce.

### Marketplace

The marketplace lets administrators configure items that members can purchase with their earned currency. Items are cosmetic only and can include Discord role assignments. Every purchase is handled atomically at the database level, which means concurrent purchases cannot result in double-spending or over-allocation. Expired items cannot be purchased.

### Member Dashboard

Each authenticated member has a profile showing their current stats, rank, achievements, and marketplace inventory. On any rewarded event, members can view a full trace that explains which rules matched, what calculations were applied, and what they received. There is no ambiguity about how rewards are determined.

### Admin Dashboard

Administrators have a central interface to manage rules, achievements, marketplace items, and media. A taxonomy browser shows every event type the bot has observed and allows building rules directly from any observed event type. An observability screen shows reward rates, anomaly flags, and system health.

### Public Leaderboard

A public leaderboard is accessible without authentication. It shows ranks and scores only. Usernames and avatars are not visible to unauthenticated visitors. When a member authenticates, they see their own position alongside the anonymized board. Members who leave the server are automatically anonymized.

---

## Use in Organizations

Synapse was designed with Discord communities in mind, but it is particularly well-suited to structured organizations that operate on Discord. This includes student clubs, networks of clubs, and leadership bodies that need defensible documentation of community activity.

### Demonstrating Active Membership

Many funding bodies, student government offices, and inter-club councils require organizations to demonstrate that their membership is active and engaged, not just registered. Raw Discord member counts are not useful for this purpose because they include inactive accounts, guests, and former members. Synapse produces a persistent, queryable record of actual participation: who contributed, how often, across which channels, and over what time period.

Because every event is stored with a timestamp and source, administrators can generate accurate statistics for any date range. A club applying for renewed recognition or requesting funding can report genuine participation numbers backed by a structured data record rather than a screenshot of a member count.

### Measuring Operational Capacity

For organizations that use Discord as their primary operating environment, Synapse provides a concrete measure of how much work the community is actually doing. This includes discussions in designated channels, event attendance through voice participation, and collaborative activity in threads. These metrics reflect operational capacity in a way that passive observation cannot.

Inter-club bodies and umbrella organizations can use this data to compare activity levels across member clubs, identify which groups need support, and allocate resources based on demonstrated engagement rather than self-reported estimates.

### Leadership and Accountability

The event lake, which is the append-only record of all server activity, gives leadership a way to look back at any period and understand what happened. Rules can be configured to reward contribution to specific channels, so club officers who are active in designated decision-making spaces accumulate a traceable record of their participation. This is useful for internal recognition and for formal accountability requirements at institutions that track officer involvement.

Because Synapse is self-hosted, the organization owns all of its data. There is no third-party platform to request records from, no privacy policy change that removes access to historical data, and no subscription fee that can lapse and take the history with it.

---

## Design Choices Worth Knowing

**The rule engine does not produce side effects.** The code that evaluates rules does not write to the database, does not call Discord, and does not send notifications. It receives structured input and returns a result. All writes, announcements, and role changes happen in a separate service layer. This separation makes the engine safe to run in simulation mode against real data, because doing so cannot accidentally affect a live server.

**The event record is append-only.** Activity is never deleted or overwritten. If your rules change over time, you can replay historical events against the new ruleset to understand what would have been different. This is the same principle behind audit logs in financial systems: the record is the source of truth, and derived values can always be recalculated from it.

**Shadow mode before cutover.** Major system changes can run alongside existing behavior before replacing it. Both pipelines receive the same inputs, and any differences are logged. A change does not go live until the outputs have matched within an acceptable margin for a defined period. This reduces the risk of a configuration change producing unexpected reward behavior at scale.

**Feature flags with fast rollback.** Each major subsystem ships behind a feature flag. Flags can be toggled without a redeploy and take effect within about sixty seconds. The system enforces a safe ordering for enabling flags so that dependent systems cannot be activated before their prerequisites are stable.

**Privacy by default on the public leaderboard.** Anyone on the internet can view the public leaderboard. It shows ranks and scores and nothing else. Usernames and avatars are not visible to unauthenticated visitors. Former members are anonymized automatically when they leave the server.

---

## What Synapse Is Not

Synapse is not a moderation tool. It does not issue warnings, bans, or timeouts.

It is not a subscription service. Synapse is self-hosted software. You run it on your own infrastructure and you own all of the data it collects.

It is not designed to manufacture engagement through compulsive mechanics. The intent is to measure and reflect the participation that your community produces naturally, and to reward the kinds of contribution you have decided matter. What counts as valuable activity is something you define through your rules. The system does not make that decision for you.

---

## Summary

Synapse records activity in your Discord server, evaluates it against a configurable rule engine, and produces a persistent record of who participated, how often, and what they earned. Members have a transparent view of their own stats and reward history. Administrators have tools to configure, simulate, and observe the system. Organizations have a reliable source of participation data that can support funding applications, membership reporting, and operational accountability.
